# Jetson Porting Tasks

Porting PiTrac from Raspberry Pi (libcamera / lgpio) to NVIDIA Jetson Xavier NX (V4L2 / OpenCV / libgpiod).

Each task corresponds to one RPi-specific component identified in the porting plan.
Work through Group 1 first — nothing compiles until all of those are done.

---

## Group 1 — Must replace to compile

These cause immediate build failure on Jetson before a single source file is compiled.

- [ ] **`meson.build:69`** — Remove `dependency('libcamera', required: true)`; replace with a no-op `declare_dependency()` under a `JETSON_BUILD` guard.
- [ ] **`meson.build:73`** — Remove `dependency('lgpio', required: true)`; replace with `dependency('libgpiod', required: true)`.
- [ ] **`meson.build:84–87`** — Remove the `summary()` block that references `libcamera_dep` (will crash if the dep is a stub).
- [ ] **`meson.build:90,95,242–244`** — Remove `libcamera_dep` and `lgpio_dep` from `rpicam_app_dep` and `pitrac_lm_module_deps`.
- [ ] **`meson.build:99–104`** — Remove all rpicam-apps `subdir()` calls (`core`, `encoder`, `image`, `output`, `preview`, `post_processing_stages`); these pull in the entire libcamera source tree.
- [ ] **`meson.build:124,231`** — Remove `rpicam_app_src` from the sources list; there is no rpicam-apps object tree to link on Jetson.
- [ ] **`meson.build:71`** — Lower the `opencv4` version floor from `>= 4.9.0` to `>= 4.5.0` to match the version shipped with JetPack 5.1.6.
- [ ] **`libcamera_interface.h`** — Wrap entire file in `#ifndef JETSON_BUILD`; create new `v4l2_interface.h` with identical public function signatures wrapped in `#ifdef JETSON_BUILD`.
- [ ] **`v4l2_interface.h` (new file)** — Replace `LibcameraJpegApp*` array member with `cv::VideoCapture*` per camera slot; replace all RPiCam includes with OpenCV and V4L2 headers.
- [ ] **`still_image_libcamera_app.hpp`** — Wrap entire file in `#ifndef JETSON_BUILD`; `LibcameraJpegApp` subclasses `RPiCamApp` which does not exist on Jetson.
- [ ] **`ball_watcher.h`** — Wrap `#include "core/rpicam_encoder.hpp"` and `#include "encoder/encoder.hpp"` in `#ifndef JETSON_BUILD`; change `ball_watcher_event_loop` signature to accept a `JetsonCaptureApp` struct instead of `RPiCamEncoder&` under `#ifdef JETSON_BUILD`.
- [ ] **`ball_watcher.cpp`** — Rewrite `ball_watcher_event_loop` body for Jetson: replace `RPiCamEncoder` open/configure/start/wait/stop pipeline with a `cv::VideoCapture` read loop; retain the `MotionDetectStage::Process` call and `RecentFrames` buffer logic unchanged.
- [ ] **`motion_detect.h`** — Wrap `#include "core/rpicam_app.hpp"` and `#include "post_processing_stages/post_processing_stage.hpp"` in `#ifndef JETSON_BUILD`; under `#ifdef JETSON_BUILD` either provide a minimal stub `PostProcessingStage` base class or remove the inheritance from `MotionDetectStage`.
- [ ] **`post_processing_stages/motion_detect_stage.cpp`** — Replace `#include <libcamera/stream.h>` and `#include "core/rpicam_app.hpp"`; replace `BufferReadSync` / `libcamera::Span<uint8_t>` buffer access with a direct `uint8_t*` pointer obtained from a `cv::Mat` passed into `Process()`; replace `completed_request->post_process_metadata` with a simple struct field or `std::unordered_map<std::string, bool>`; pixel-comparison loop is hardware-independent and must not change.

---

## Group 2 — Must replace to run

These compile once Group 1 stubs are in place, but will not function correctly at runtime without real Jetson implementations.

- [ ] **`pulse_strobe.cpp` — lgpio GPIO**  — Replace `lgGpiochipOpen`, `lgGpioClaimOutput`, `lgGpioWrite` calls with `libgpiod` equivalents (`gpiod_chip_open`, `gpiod_line_request_output`, `gpiod_line_set_value`); identify the correct Jetson Xavier NX GPIO chip and pin that corresponds to BCM GPIO25 (shutter trigger output).
- [ ] **`pulse_strobe.cpp` — lgpio SPI** — Replace `lgSpiOpen`, `lgSpiWrite`, `lgSpiClose` calls with standard Linux SPI via `open("/dev/spidevN.M")` + `ioctl(SPI_IOC_MESSAGE)`; `BuildPulseTrain` and all pulse-timing math are platform-independent and must not change.
- [ ] **`libcamera_interface.cpp` — `TakeLibcameraStill`** — Reimplement using `cv::VideoCapture::open()` + `cap.read(frame)` + `cap.release()`; keep the same function name so all callers are unchanged.
- [ ] **`libcamera_interface.cpp` — `ConfigureForLibcameraStill`** — Replace `LibcameraJpegApp` construction and libcamera option-setting with `cv::VideoCapture` open and `cap.set(cv::CAP_PROP_*)` calls for resolution, exposure, and gain.
- [ ] **`libcamera_interface.cpp` — `DeConfigureForLibcameraStill`** — Replace libcamera teardown with `cap.release()`.
- [ ] **`libcamera_interface.cpp` — `PerformCameraSystemStartup` (trigger scripts)** — Replace `setCameraTriggerInternal.sh` and `setCameraTriggerExternal.sh` shell script calls with new Jetson-specific scripts (or inline `v4l2-ctl --set-ctrl` calls) that set OV9281 trigger mode via V4L2 controls; replace `imx296_trigger` calls (IMX296-specific, RPi-only) with the OV9281 equivalent.
- [ ] **`libcamera_interface.cpp` — `RetrieveCameraInfo`** — Replace libcamera resolution/framerate query with `ioctl(VIDIOC_G_FMT)` or `cv::VideoCapture::get(cv::CAP_PROP_FRAME_WIDTH / HEIGHT / FPS)`.
- [ ] **`libcamera_interface.cpp` — `DiscoverCameraLocation`** — Replace RPi media-controller topology walk with a V4L2 `VIDIOC_QUERYCAP` enumeration loop over `/dev/videoN` that matches on the Arducam OV9281 USB driver name or vendor/product ID.
- [ ] **`libcamera_interface.cpp` — `SendCameraCroppingCommand`** — Validate whether `media-ctl` (a standard Linux tool) works with the OV9281 USB camera on Jetson; if not (USB UVC cameras typically expose no media controller pipeline), replace with `cv::VideoCapture` sub-resolution setting or software crop; return true (no-op) until tested with real hardware.

---

## Group 3 — Can stub out for now

These are optional paths, diagnostic features, or config-gated modes that can be no-ops without breaking the core shot-detection flow.

- [ ] **`libcamera_interface.cpp` — `SetLibCameraLoggingOff`** — Replace with an empty function body; no libcamera logging exists to suppress on Jetson. Mark with `// JETSON_STUB`.
- [ ] **`libcamera_interface.cpp` — `ConfigurePostProcessing` (pipeline half)** — Keep the `MotionDetectStage::incoming_configuration` struct-assignment half unchanged; replace the rpicam-apps pipeline-registration calls with a no-op. Mark with `// JETSON_STUB`.
- [ ] **`libcamera_interface.cpp` — `ConfigureLibCameraOptions`** — Replace with a no-op that returns true; on Jetson the equivalent camera settings (framerate, gain, shutter) are applied via `cv::VideoCapture::set()` when the capture device is opened. Mark with `// JETSON_STUB`.
- [ ] **`libcamera_interface.cpp` — `SetLibcameraTuningFileEnvVariable`** — Replace with a no-op that returns true; the `LIBCAMERA_RPI_TUNING_FILE` env var has no meaning on Jetson. Mark with `// JETSON_STUB`.
- [ ] **`libcamera_interface.cpp` — `WatchForHitAndTrigger`** — Stub to return false until the two-camera IPC flow is validated end-to-end on Jetson hardware. Mark with `// JETSON_STUB`.
- [ ] **`libcamera_interface.cpp` / `motion_detect_stage.cpp` — club-strike image path** — Hardcode `GolfSimClubData::kGatherClubData = false` for the initial Jetson build to bypass the wider crop window and post-motion frame capture countdown; revisit after core motion-detect is working.
- [ ] **`pulse_strobe.cpp` — pre-image subtraction path** — Hardcode `GolfSimCamera::kUsePreImageSubtraction = false`; this feature is already noted in the source as deprecated and non-functional.
