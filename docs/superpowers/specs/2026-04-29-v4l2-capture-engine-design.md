# V4L2 Capture Engine Design

**Date:** 2026-04-29
**Sub-project:** SP1 — Core Vision System
**Status:** Approved (pending implementation plan)

## Problem

PiTrac on the Jetson currently captures frames through `cv::VideoCapture`,
which caps at ~55-60 FPS per camera at 1280×800 MJPG due to OpenCV's
CPU-bound MJPG decode (LOGBOOK Issue #15, verified 2026-04-26). Both
OV9281 cameras have already been confirmed at sustained 120 FPS at the
kernel/USB level via `v4l2-ctl --stream-mmap`, including dual-camera
parallel capture — the bottleneck is the decode path inside
`cv::VideoCapture`, not the camera, USB, or driver.

Five functions in `Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp`
are currently `JETSON_STUB` placeholders: `TakeRawPicture`, `CheckForBall`,
`PerformCameraSystemStartup`, `WatchForHitAndTrigger`, and
`WaitForCam2Trigger`. The binary builds and runs, but every camera
operation returns a stub `false`.

This spec covers the design for the real V4L2 capture engine that replaces
those stubs and unblocks 120 FPS sustained capture for the ball-watcher
loop.

## Goal

A drop-in V4L2 capture engine that:

1. Hits sustained 120 FPS at 1280×800 MJPG on each OV9281, in parallel.
2. Returns `cv::Mat` frames with the same shape (`CV_8UC3` BGR) that
   `cv::VideoCapture::read()` returns today, so consumers compile
   unchanged.
3. Touches only `v4l2_interface.h`, `v4l2_interface.cpp`, and
   `meson.build`.
4. Implements 4 of the 5 currently-stubbed functions with real V4L2 logic;
   leaves `WaitForCam2Trigger` stubbed because the IR strobe SPI it depends
   on is also stubbed (no IR LED hardware yet).

## Architecture

### V4L2Capture — the engine

A new class declared in `v4l2_interface.h` and implemented in
`v4l2_interface.cpp`. Its public surface mirrors `cv::VideoCapture` exactly,
so `JetsonCaptureApp::cap` can swap type from `cv::VideoCapture` to
`V4L2Capture` without forcing edits to `ball_watcher.cpp` (the only file
that touches `app.cap`):

```cpp
class V4L2Capture {
public:
    bool   open(const std::string& path, int /*api_pref ignored*/);
    bool   isOpened() const;
    void   release();
    bool   read(cv::Mat& out);                  // BGR CV_8UC3, drop-in for cv::VideoCapture::read
    bool   set(int prop_id, double value);      // FRAME_WIDTH/HEIGHT/FOURCC/FPS/EXPOSURE/GAIN
    double get(int prop_id) const;              // same set
private:
    int      fd        = -1;
    int      width     = 1280;
    int      height    = 800;
    int      fps       = 120;
    uint32_t fourcc    = V4L2_PIX_FMT_MJPEG;
    bool     streaming = false;
    struct MmapBuf { void* start; size_t length; };
    std::vector<MmapBuf> bufs;          // 4 mmap'd buffers
    void*    tj_handle = nullptr;       // tjhandle for libjpeg-turbo
    cv::Mat  gray_scratch;              // CV_8UC1 reused across reads
    // queued V4L2 controls applied at first stream-on
    std::vector<std::pair<uint32_t, int32_t>> pending_ctrls;
};
```

`JetsonCaptureApp` keeps every other field (`device_path`, `camera_slot`,
`gain`, `contrast`, `saturation`, `shutter_time_us`, `flip_vertical`,
`width`, `height`). Only the `cap` field's type changes.

### Lifecycle and the V4L2 ioctl sequence

**`open(path, _)`** — bare minimum:
1. `::open(path, O_RDWR)` → store `fd`.
2. `VIDIOC_QUERYCAP` → verify `V4L2_CAP_VIDEO_CAPTURE`.
   No format set, no buffers, no streaming.

**First `read()` (lazy stream-on)** — applies whatever `set()` calls
queued, then starts streaming:
1. `VIDIOC_S_FMT` with current `fourcc / width / height`
2. `VIDIOC_S_PARM` with current `fps`
3. `VIDIOC_S_CTRL` for each entry in `pending_ctrls` (exposure, gain, …)
4. `VIDIOC_REQBUFS` count = 4, type = `V4L2_BUF_TYPE_VIDEO_CAPTURE`,
   memory = `V4L2_MEMORY_MMAP`
5. For each of 4 buffers: `VIDIOC_QUERYBUF`, `mmap()`
6. For each of 4 buffers: `VIDIOC_QBUF`
7. `VIDIOC_STREAMON`
8. Set `streaming = true`, fall through into the per-frame path.

**Per-frame path** (every `read()` call):
1. `VIDIOC_DQBUF` (blocking) → returns one filled buffer
2. `tjDecompress2(tj_handle, mmap_ptr, bytes_used, gray_scratch.data,
   width, 0, height, TJPF_GRAY, 0)` — direct gray decode
3. `cv::cvtColor(gray_scratch, out, COLOR_GRAY2BGR)` → CV_8UC3 BGR
4. `VIDIOC_QBUF` to re-queue the buffer

**`release()`**: `VIDIOC_STREAMOFF`, `munmap()` × 4, `tjDestroy(tj_handle)`,
`::close(fd)`. Reset all state so a subsequent `open()` works.

**Threading:** synchronous. `read()` blocks for one frame
(dequeue → decode → enqueue). No background thread.

Budget at 120 FPS: 8.3 ms/frame.
Expected: ioctl ~0.5 ms + libjpeg-turbo gray decode ~3-4 ms + cvtColor
~1 ms = ~5 ms per `read()`. Leaves ~3 ms for the consumer (motion-detect)
inside one frame interval.

If profiling later shows we need more headroom, an asynchronous variant
(producer thread + 3-slot ring buffer) can be added behind the same
public API. Explicit YAGNI for v1.

### `set()` / `get()` semantics

`set()` accepts only the properties listed below. Anything else returns
`false` without effect.

| Property | Behavior |
|---|---|
| `CAP_PROP_FRAME_WIDTH` | If not yet streaming: update `width`. If streaming: return false. |
| `CAP_PROP_FRAME_HEIGHT` | Same. |
| `CAP_PROP_FOURCC` | Same. Engine accepts only `V4L2_PIX_FMT_MJPEG`; other values return false. |
| `CAP_PROP_FPS` | Same. |
| `CAP_PROP_EXPOSURE` | If streaming: `VIDIOC_S_CTRL` immediately. Else: queue in `pending_ctrls`. |
| `CAP_PROP_GAIN` | Same as exposure. |

Format-affecting properties (`WIDTH/HEIGHT/FOURCC/FPS`) can only be set
between `open()` and the first `read()`. This matches how
`ball_watcher_event_loop` already calls them.

`get()` returns the cached value for format properties; for `CAP_PROP_FPS`
after open it queries `VIDIOC_G_PARM` to confirm the device accepted the
requested rate.

### Decode — libjpeg-turbo, gray-internal, BGR-out

Going with `libjpeg-turbo` (pkg-config `libturbojpeg`, apt
`libturbojpeg0-dev`). Decode the MJPG payload directly to single-channel
grayscale via `TJPF_GRAY`, then `cv::cvtColor(GRAY → BGR)` once.

Why gray-internal: the OV9281 is monochrome, so the JPEG payload is
single-channel. Asking libjpeg-turbo for BGR forces it to duplicate
internally during YCbCr→RGB. Doing it ourselves with `cvtColor` is
explicit and identical in cost.

Why BGR-out: matches `cv::VideoCapture::read()` (CV_8UC3 BGR) — no
behavior change for any consumer. If profiling later shows the
`cvtColor` matters (~1 ms/frame), the engine can flip to CV_8UC1 with
a one-line change and consumers that genuinely need BGR can do the
conversion at the call site.

Rejected — nvJPEG: per-frame CUDA dispatch overhead, the OpenCV in this
build is not CUDA-enabled (LOGBOOK Issue #13), and bring-up cost is
non-trivial. Future optimization, not v1.

Rejected — userptr / read() syscalls: mmap is the standard V4L2 path,
zero-copy from kernel, lowest CPU. Other modes add complexity for no
gain on UVC.

### How `JetsonCompletedRequest` gets filled

It already does, in `ball_watcher.cpp:206-209`. The engine knows nothing
about `JetsonCompletedRequest` — it just hands a `cv::Mat` back from
`read()`. `ball_watcher_event_loop` continues to wrap that into a
`JetsonCompletedRequest` exactly as today. No change to that file.

## Mapping the 5 stubs

| Stub | Status | How it works after this session |
|---|---|---|
| `PerformCameraSystemStartup` | Real | Probe `/dev/video0` and `/dev/video2` via `VIDIOC_QUERYCAP`, confirm OV9281 (Arducam UVC vendor string), allocate two `JetsonCaptureApp` instances (one per slot), store in `LibCameraInterface::libcamera_app_[0/1]`. Apply per-camera defaults (1280×800, MJPG, 120 FPS, exposure/gain from `kCameraN*` statics). Does NOT call `open()` yet — that happens lazily on first capture. |
| `TakeRawPicture(cam, mat)` | Real | If `app->cap` is not open, `open()` it; `read(mat)`; leave open for subsequent calls. The first call pays the lazy stream-on cost (~30-50 ms); repeated calls on the same `app` reuse the open device. Final cleanup happens at LM shutdown. |
| `CheckForBall(ball, mat)` | Real | `TakeRawPicture` into `mat`, then forward to the existing hardware-independent ball-detect entry point (the same path the RPi build's `CheckForBallEnhanced` uses inside `ball_image_proc`). |
| `WatchForHitAndTrigger(ball, mat, motion_detected)` | Real (motion-only) | Look up `JetsonCaptureApp* app = libcamera_app_[0]`, call existing `ball_watcher_event_loop(*app, motion_detected)`. The IPC-trigger half stays a no-op via the existing stub `PulseStrobe::SendExternalTrigger()`. |
| `WaitForCam2Trigger(mat)` | Stays stubbed | Without a working IR strobe + SPI, there is no synchronized exposure to capture. Returns false. Revisited when the IR LED + SPI strobe driver land. |

## meson.build changes

One addition under the existing `jetson_build` guard:

```meson
if jetson_build
    turbojpeg_dep = dependency('libturbojpeg', required : true)
    pitrac_lm_module_deps += [turbojpeg_dep]
endif
```

Apt prerequisite on the Jetson: `sudo apt install libturbojpeg0-dev`.

mmap is libc; V4L2 ioctls come from `<linux/videodev2.h>` (already
included via `v4l2_interface.h`). No other build-system changes.

## Files touched

| File | Change |
|---|---|
| `Software/LMSourceCode/ImageProcessing/v4l2_interface.h` | Add `V4L2Capture` class declaration. Change `JetsonCaptureApp::cap` type from `cv::VideoCapture` to `V4L2Capture`. Drop the `<opencv2/videoio.hpp>` include (no longer needed in the header). |
| `Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp` | Implement `V4L2Capture`. Replace 4 of 5 stub bodies (`PerformCameraSystemStartup`, `TakeRawPicture`, `CheckForBall`, `WatchForHitAndTrigger`). Keep `WaitForCam2Trigger`, `ConfigureLibCameraOptions`, `SetLibcameraTuningFileEnvVariable`, and the `PulseStrobe::*` stubs as-is. |
| `Software/LMSourceCode/ImageProcessing/meson.build` | Add `libturbojpeg` dep under `jetson_build`. |

No edits to `ball_watcher.cpp`, `motion_detect.{h,cpp}`,
`motion_detect_stage.cpp`, `gs_camera.cpp`, `gs_fsm.cpp`, `lm_main.cpp`,
or any other source file.

## Out of scope

- Background producer thread / ring buffer. Sync-only v1; revisit only
  if profiling shows a need.
- nvJPEG — deferred. Needs CUDA-aware OpenCV, currently absent
  (Issue #13).
- IR strobe GPIO/SPI — deferred. IR LED array not ordered.
  `PulseStrobe::*` stubs remain.
- `TakeLibcameraStill`, `ConfigureForLibcameraStill`,
  `DeConfigureForLibcameraStill`, `WatchForBallMovement`,
  `RetrieveCameraInfo`, `DiscoverCameraLocation`,
  `SendCameraCroppingCommand`, `GetCmdLineForMediaCtlCropping`,
  `LibCameraInterface::undistort_camera_image`,
  `LibCameraInterface::SendCamera2PreImage` — declared in
  `v4l2_interface.h`, currently undefined. The binary links because
  no Jetson-side caller references them. Leaving alone.
- Pixel formats other than MJPG. Engine is purpose-built for OV9281's
  high-FPS UVC mode.

## Risks and open items

1. **`tjDecompress2` performance on Xavier NX ARM cores not yet measured.**
   Estimate is 3-4 ms/frame for 1280×800 gray. If reality is closer to
   8 ms, the synchronous path will not hit 120 FPS sustained and we'll
   need to add the producer-thread variant. Mitigation: log per-frame
   decode time at a configurable log level, easy to flip on.

2. **First `read()` will exhibit higher latency than steady-state**
   (REQBUFS + STREAMON + first decode in series). For the motion-detect
   loop this is invisible (one extra frame interval). For one-shot
   `TakeRawPicture` calls, this adds ~30-50 ms to the first capture
   after `open()`. Acceptable.

3. **Auto-exposure caps frame rate** (LOGBOOK Issue #16). Production
   path uses the IR strobe as the effective shutter and runs cameras in
   manual exposure. Until the strobe is wired, the engine should default
   to manual exposure with a short `shutter_time_us` (matching the
   `kCameraN*StillShutterTimeuS` statics already in the code) so bench
   testing without strobe still hits 120 FPS.

4. **OV9281 vendor-string detection** in `PerformCameraSystemStartup`
   needs to confirm against the real `bus_info` / `card` strings the
   driver returns. We have these from prior `v4l2-ctl --info` runs on
   the Jetson; the implementation will use a substring match on
   "Arducam" or "OV9281" with a fallback to opening any device that
   reports `V4L2_CAP_VIDEO_CAPTURE`. Hardcoded `/dev/video0` and
   `/dev/video2` paths come from the LOGBOOK 2026-03-21 device-mapping
   decision and are stable on the Jetson side per
   `udev` rules — not a concern in practice.

## Acceptance criteria

1. `meson setup build_jetson --wipe && ninja -C build_jetson` succeeds
   on the Jetson with the new `libturbojpeg` dep installed.
2. `pitrac_lm` starts; `PerformCameraSystemStartup` opens both
   `/dev/video0` and `/dev/video2` without error.
3. A standalone smoke test (run the ball-watcher loop, no motion) shows
   sustained ≥115 FPS per camera at 1280×800 MJPG, measured over a
   60-second window.
4. `TakeRawPicture` returns a valid 1280×800 CV_8UC3 cv::Mat with
   non-empty pixel data from each camera slot.
5. `CheckForBall` invokes the existing hardware-independent ball-detect
   path and returns its result unchanged for at least one synthetic ball
   image placed in front of the camera.
6. `WatchForHitAndTrigger` returns with `motion_detected = true` when
   a hand is waved across the field of view; returns cleanly on
   shutdown signal.
