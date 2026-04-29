# Jetson Porting Tasks

Porting PiTrac from Raspberry Pi (libcamera / lgpio) to NVIDIA Jetson Xavier NX (V4L2 / OpenCV / libgpiod).

Each task corresponds to one RPi-specific component identified in the porting plan.
Work through Group 1 first — nothing compiles until all of those are done.

---

## Group 1 — Must replace to compile

These cause immediate build failure on Jetson before a single source file is compiled.

- [x] **`meson.build:69`** — Remove `dependency('libcamera', required: true)`; replace with a no-op `declare_dependency()` under a `JETSON_BUILD` guard.
- [x] **`meson.build:73`** — Remove `dependency('lgpio', required: true)`; replace with `dependency('libgpiod', required: true)`.
- [x] **`meson.build:84–87`** — Remove the `summary()` block that references `libcamera_dep` (will crash if the dep is a stub).
- [x] **`meson.build:90,95,242–244`** — Remove `libcamera_dep` and `lgpio_dep` from `rpicam_app_dep` and `pitrac_lm_module_deps`.
- [x] **`meson.build:99–104`** — Remove all rpicam-apps `subdir()` calls (`core`, `encoder`, `image`, `output`, `preview`, `post_processing_stages`); these pull in the entire libcamera source tree.
- [x] **`meson.build:124,231`** — Remove `rpicam_app_src` from the sources list; there is no rpicam-apps object tree to link on Jetson.
- [x] **`meson.build:71`** — Lower the `opencv4` version floor from `>= 4.9.0` to `>= 4.5.0` to match the version shipped with JetPack 5.1.6.
- [x] **`libcamera_interface.h`** — Wrap entire file in `#ifndef JETSON_BUILD`; create new `v4l2_interface.h` with identical public function signatures wrapped in `#ifdef JETSON_BUILD`.
- [x] **`v4l2_interface.h` (new file)** — Replace `LibcameraJpegApp*` array member with `cv::VideoCapture*` per camera slot; replace all RPiCam includes with OpenCV and V4L2 headers.
- [x] **`still_image_libcamera_app.hpp`** — Wrap entire file in `#ifndef JETSON_BUILD`; `LibcameraJpegApp` subclasses `RPiCamApp` which does not exist on Jetson.
- [x] **`ball_watcher.h`** — Wrap `#include "core/rpicam_encoder.hpp"` and `#include "encoder/encoder.hpp"` in `#ifndef JETSON_BUILD`; change `ball_watcher_event_loop` signature to accept a `JetsonCaptureApp` struct instead of `RPiCamEncoder&` under `#ifdef JETSON_BUILD`.
- [x] **`ball_watcher.cpp`** — Rewrite `ball_watcher_event_loop` body for Jetson: replace `RPiCamEncoder` open/configure/start/wait/stop pipeline with a `cv::VideoCapture` read loop; retain the `MotionDetectStage::Process` call and `RecentFrames` buffer logic unchanged.
- [x] **`motion_detect.h`** — Wrap `#include "core/rpicam_app.hpp"` and `#include "post_processing_stages/post_processing_stage.hpp"` in `#ifndef JETSON_BUILD`; under `#ifdef JETSON_BUILD` either provide a minimal stub `PostProcessingStage` base class or remove the inheritance from `MotionDetectStage`.
- [x] **`post_processing_stages/motion_detect_stage.cpp`** — Replace `#include <libcamera/stream.h>` and `#include "core/rpicam_app.hpp"`; replace `BufferReadSync` / `libcamera::Span<uint8_t>` buffer access with a direct `uint8_t*` pointer obtained from a `cv::Mat` passed into `Process()`; replace `completed_request->post_process_metadata` with a simple struct field or `std::unordered_map<std::string, bool>`; pixel-comparison loop is hardware-independent and must not change.

---

## Group 2 — Must replace to run

These compile once Group 1 stubs are in place, but will not function correctly at runtime without real Jetson implementations.

- [ ] **`pulse_strobe.cpp` — lgpio GPIO**  — Replace `lgGpiochipOpen`, `lgGpioClaimOutput`, `lgGpioWrite` calls with `libgpiod` equivalents (`gpiod_chip_open`, `gpiod_line_request_output`, `gpiod_line_set_value`); identify the correct Jetson Xavier NX GPIO chip and pin that corresponds to BCM GPIO25 (shutter trigger output). *(Stubs in v4l2_interface.cpp now return true so the FSM advances; real impl gated on IR LED hardware.)*
- [ ] **`pulse_strobe.cpp` — lgpio SPI** — Replace `lgSpiOpen`, `lgSpiWrite`, `lgSpiClose` calls with standard Linux SPI via `open("/dev/spidevN.M")` + `ioctl(SPI_IOC_MESSAGE)`; `BuildPulseTrain` and all pulse-timing math are platform-independent and must not change. *(Stays stubbed; gated on IR LED hardware.)*
- [x] **`libcamera_interface.cpp` — `TakeLibcameraStill`** — ~~Reimplement using `cv::VideoCapture::open()` + `cap.read(frame)` + `cap.release()`~~ Resolved 2026-04-29 — V4L2Capture class in v4l2_interface.cpp replaces cv::VideoCapture; TakeRawPicture (in v4l2_interface.cpp) routes through the same V4L2Capture instance. TakeLibcameraStill itself is now an unreferenced legacy symbol on the Jetson link.
- [x] **`libcamera_interface.cpp` — `ConfigureForLibcameraStill`** — Resolved 2026-04-29 — V4L2Capture::open + V4L2Capture::set(CAP_PROP_FRAME_WIDTH / HEIGHT / FOURCC / FPS / EXPOSURE / GAIN) inside TakeRawPicture covers the same configuration responsibility.
- [x] **`libcamera_interface.cpp` — `DeConfigureForLibcameraStill`** — Resolved 2026-04-29 — V4L2Capture::release() handles the teardown (STREAMOFF, munmap, tjDestroy, close).
- [x] **`libcamera_interface.cpp` — `PerformCameraSystemStartup`** — Resolved 2026-04-29 — Real implementation in v4l2_interface.cpp probes /dev/video0 and /dev/video2 via VIDIOC_QUERYCAP, allocates JetsonCaptureApp per slot, sets per-camera defaults from kCameraN* statics, sets CameraHardware resolution override 1280×800. Trigger-script replacement still pending (OV9281 USB cameras don't currently use external trigger mode).
- [x] **`libcamera_interface.cpp` — `RetrieveCameraInfo`** — Resolved 2026-04-29 (functionally) — V4L2Capture::get(CAP_PROP_FRAME_WIDTH / HEIGHT / FPS) provides this. RetrieveCameraInfo itself is unreferenced on the Jetson link.
- [x] **`libcamera_interface.cpp` — `DiscoverCameraLocation`** — Resolved 2026-04-29 (hardcoded for OV9281 mapping) — `probe_v4l2_capture_device` in v4l2_interface.cpp performs the V4L2 QUERYCAP probe on /dev/video0 and /dev/video2 (mapping confirmed in LOGBOOK 2026-03-21). General /dev/videoN enumeration is overkill for the two-camera setup.
- [ ] **`libcamera_interface.cpp` — `SendCameraCroppingCommand`** — UVC OV9281 USB cameras have no media-controller pipeline, so `media-ctl` cropping doesn't apply. The full-frame 1280×800 path is sufficient for v1; cropped sub-resolution mode can land when ball-detection profiling shows it's needed.

---

## Group 3 — Can stub out for now

These are optional paths, diagnostic features, or config-gated modes that can be no-ops without breaking the core shot-detection flow.

- [x] **`libcamera_interface.cpp` — `SetLibCameraLoggingOff`** — Replace with an empty function body; no libcamera logging exists to suppress on Jetson. Mark with `// JETSON_STUB`.
- [x] **`libcamera_interface.cpp` — `ConfigurePostProcessing` (pipeline half)** — Keep the `MotionDetectStage::incoming_configuration` struct-assignment half unchanged; replace the rpicam-apps pipeline-registration calls with a no-op. Mark with `// JETSON_STUB`.
- [x] **`libcamera_interface.cpp` — `ConfigureLibCameraOptions`** — Replace with a no-op that returns true; on Jetson the equivalent camera settings (framerate, gain, shutter) are applied via `cv::VideoCapture::set()` when the capture device is opened. Mark with `// JETSON_STUB`.
- [x] **`libcamera_interface.cpp` — `SetLibcameraTuningFileEnvVariable`** — Replace with a no-op that returns true; the `LIBCAMERA_RPI_TUNING_FILE` env var has no meaning on Jetson. Mark with `// JETSON_STUB`.
- [x] **`libcamera_interface.cpp` — `WatchForHitAndTrigger`** — Stub to return false until the two-camera IPC flow is validated end-to-end on Jetson hardware. Mark with `// JETSON_STUB`.
- [x] **`libcamera_interface.cpp` / `motion_detect_stage.cpp` — club-strike image path** — `GolfSimClubData::kGatherClubData` already initialised `false` in `gs_club_data.cpp:19`; all usage sites in RPi path are now excluded by `#ifndef JETSON_BUILD` guards. No code change needed.
- [x] **`pulse_strobe.cpp` — pre-image subtraction path** — `GolfSimCamera::kUsePreImageSubtraction` already initialised `false` in `gs_camera.cpp:58` with source comment "ultimately not as helpful as hoped". No code change needed.
