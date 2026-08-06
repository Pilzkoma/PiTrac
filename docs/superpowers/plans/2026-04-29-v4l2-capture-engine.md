# V4L2 Capture Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 5 stub functions in `v4l2_interface.cpp` and the `cv::VideoCapture` field on `JetsonCaptureApp` with a real V4L2-ioctl + libjpeg-turbo capture engine that hits sustained 120 FPS on each OV9281 camera at 1280×800 MJPG.

**Architecture:** A new `V4L2Capture` class (declared in `v4l2_interface.h`, implemented in `v4l2_interface.cpp`) owns one V4L2 file descriptor + 4 mmap'd MJPG buffers + one libjpeg-turbo decoder handle. Its public method names mirror `cv::VideoCapture` (`open / isOpened / release / read / set / get`) so `JetsonCaptureApp::cap`'s type swaps from `cv::VideoCapture` to `V4L2Capture` without touching `ball_watcher.cpp`. `read()` is synchronous: `VIDIOC_DQBUF` → `tjDecompress2` (gray) → `cv::cvtColor` to BGR → `VIDIOC_QBUF`. Stream-on is lazy (deferred to first `read()`).

**Tech Stack:** C++20, V4L2 ioctls (`<linux/videodev2.h>`), libjpeg-turbo (`<turbojpeg.h>`, pkg-config `libturbojpeg`), OpenCV 4.5.4 (no CUDA), Meson + Ninja, Jetson Xavier NX (JetPack 5.1.6, Ubuntu 20.04, ARM64).

**Spec:** `docs/superpowers/specs/2026-04-29-v4l2-capture-engine-design.md`.

---

## Notes for the implementer

This codebase has **no C++ unit-test framework set up**, the target is **hardware-in-the-loop** (OV9281 USB cameras, OS-level V4L2), and the dev workflow is **edit on Windows → git push → on Jetson `git pull && meson setup build_jetson --wipe && ninja -C build_jetson`** with the human pasting build output back. Strict TDD (red → green → refactor on every step) is not the cadence here. Each task uses two verification gates instead:

1. **Compile gate** — every task ends with `ninja -C build_jetson` succeeding cleanly on the Jetson. The implementer asks the user to run the build and paste output. Treat any new warning as a failure.
2. **Functional gate** (Tasks 5, 6, 7, 8, 9) — run `pitrac_lm` in a real-camera mode that exercises the new code path. Verification is qualitative: log lines, FPS counts, image bytes written. Pass the verification command to the user, wait for their paste-back.

Each task ends with a **single commit**, message format: `SP1: <one-line summary>` (matches the recent commit history per `git log` on this repo: `SP1:`, `LOGBOOK:`).

**Files touched in the entire plan:**
- `Software/LMSourceCode/ImageProcessing/v4l2_interface.h` (modified across Tasks 2-9)
- `Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp` (modified across Tasks 2-9)
- `Software/LMSourceCode/ImageProcessing/meson.build` (modified Task 1 only)

No edits to `ball_watcher.cpp`, `motion_detect.{h,cpp}`, `gs_camera.cpp`, `lm_main.cpp`, or any other source.

---

## Pre-flight (one-time, on the Jetson)

Before running Task 1's verification, the user must install libjpeg-turbo development headers:

```bash
sudo apt update
sudo apt install libturbojpeg0-dev
pkg-config --modversion libturbojpeg   # should print e.g. 2.0.3
```

If pkg-config doesn't find `libturbojpeg`, the package on this Jetson exposes only the library file. That's fine — Task 1 falls back to `cxx.find_library('turbojpeg')`.

---

## Task 1: Add libturbojpeg dependency to meson

**Files:**
- Modify: `Software/LMSourceCode/ImageProcessing/meson.build` (around line 78, inside the existing `if not jetson_build` block — adding a parallel `if jetson_build` block)

- [ ] **Step 1: Add the dep**

Add the following block immediately after the existing `if not jetson_build` / `endif` pair on lines 76-79:

```meson
if jetson_build
    turbojpeg_dep = dependency('libturbojpeg', required : false)
    if not turbojpeg_dep.found()
        turbojpeg_dep = cxx.find_library('turbojpeg', required : true)
    endif
endif  # JETSON_STUB
```

- [ ] **Step 2: Add to module deps**

Find the existing block at lines ~110-112:

```meson
if not jetson_build  # JETSON_STUB
    pitrac_lm_module_deps += [libcamera_dep, lgpio_dep, rpicam_app_dep]
endif  # JETSON_STUB
```

Add an `else` arm so the Jetson build picks up turbojpeg:

```meson
if not jetson_build  # JETSON_STUB
    pitrac_lm_module_deps += [libcamera_dep, lgpio_dep, rpicam_app_dep]
else  # JETSON_STUB
    pitrac_lm_module_deps += [turbojpeg_dep]
endif  # JETSON_STUB
```

- [ ] **Step 3: Verify on Jetson**

```bash
cd ~/JetsonLM/Software/LMSourceCode/ImageProcessing
meson setup build_jetson --wipe -Djetson_build=true
```

Expected: configure completes, no errors, the dependency line shows turbojpeg resolved (either via pkg-config or `find_library`).

- [ ] **Step 4: Commit**

```bash
git add Software/LMSourceCode/ImageProcessing/meson.build
git commit -m "SP1: add libturbojpeg dependency for V4L2 capture engine"
```

---

## Task 2: V4L2Capture skeleton + JetsonCaptureApp type swap

Goal: lay down the class declaration with all method signatures, stub bodies that do nothing, and swap `JetsonCaptureApp::cap` from `cv::VideoCapture` to `V4L2Capture`. The build must stay green — proves the type swap does not break any caller.

**Files:**
- Modify: `Software/LMSourceCode/ImageProcessing/v4l2_interface.h`
- Modify: `Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp`

- [ ] **Step 1: Edit v4l2_interface.h**

(a) Drop the now-unneeded include. Find:

```cpp
#include <opencv2/core.hpp>
#include <opencv2/videoio.hpp>
```

and replace with:

```cpp
#include <opencv2/core.hpp>
```

(b) Insert the `V4L2Capture` class declaration immediately before the `JetsonCaptureApp` struct (around line 32):

```cpp
// ---------------------------------------------------------------------------
// V4L2Capture — synchronous V4L2 + libjpeg-turbo capture engine.
// Public method names mirror cv::VideoCapture so JetsonCaptureApp::cap
// can swap types without forcing edits to ball_watcher.cpp.  Defaults
// match the OV9281 high-FPS UVC mode (1280x800 MJPG @ 120 FPS, 4 mmap
// buffers).  Stream-on is lazy: open() only opens the fd; the first
// read() does VIDIOC_S_FMT / REQBUFS / mmap / STREAMON.
//
// THIS IS NOT A cv::VideoCapture.  Calling code that depends on
// cv::VideoCapture-specific semantics (e.g. backend internals) will
// not work — only the six methods declared below are supported.
// ---------------------------------------------------------------------------

class V4L2Capture {
public:
    V4L2Capture();
    ~V4L2Capture();

    V4L2Capture(const V4L2Capture&)            = delete;
    V4L2Capture& operator=(const V4L2Capture&) = delete;

    bool   open(const std::string& path, int /*api_pref*/ = 0);
    bool   isOpened() const;
    void   release();
    bool   read(cv::Mat& out);              // returns CV_8UC3 BGR
    bool   set(int prop_id, double value);
    double get(int prop_id) const;

private:
    bool ensure_streaming();                 // lazy stream-on
    bool decode_into(const uint8_t* jpeg, size_t bytes, cv::Mat& out);

    int      fd_       = -1;
    int      width_    = 1280;
    int      height_   = 800;
    int      fps_      = 120;
    uint32_t fourcc_   = 0;                  // initialised to V4L2_PIX_FMT_MJPEG in ctor
    bool     streaming_ = false;

    struct MmapBuf { void* start = nullptr; size_t length = 0; };
    std::vector<MmapBuf> bufs_;

    void*   tj_handle_ = nullptr;            // tjhandle from tjInitDecompress
    cv::Mat gray_scratch_;                   // CV_8UC1, height_ × width_

    std::vector<std::pair<uint32_t, int32_t>> pending_ctrls_;
};
```

(c) Replace the `JetsonCaptureApp::cap` field. Find:

```cpp
struct JetsonCaptureApp {
    cv::VideoCapture cap;          // the V4L2 capture device
```

Replace with:

```cpp
struct JetsonCaptureApp {
    V4L2Capture cap;               // the V4L2 capture engine (was cv::VideoCapture)
```

- [ ] **Step 2: Edit v4l2_interface.cpp — add includes and skeleton impl**

(a) After the existing `#include` block at the top (after `#include "gs_camera.h"`), add:

```cpp
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/videodev2.h>
#include <turbojpeg.h>

#include <opencv2/imgproc.hpp>
```

(b) Just below the includes, before the `namespace golf_sim {` line, add the V4L2Capture skeleton implementation:

```cpp
// ---------------------------------------------------------------------------
// V4L2Capture skeleton — full bodies land in subsequent tasks.
// Skeleton bodies make the class linkable so the build stays green.
// ---------------------------------------------------------------------------

V4L2Capture::V4L2Capture() {
    fourcc_ = V4L2_PIX_FMT_MJPEG;
}

V4L2Capture::~V4L2Capture() {
    release();
}

bool V4L2Capture::open(const std::string& /*path*/, int /*api_pref*/) {
    return false;   // implemented in Task 3
}

bool V4L2Capture::isOpened() const {
    return fd_ >= 0;
}

void V4L2Capture::release() {
    // implemented in Task 3
}

bool V4L2Capture::read(cv::Mat& /*out*/) {
    return false;   // implemented in Task 5
}

bool V4L2Capture::set(int /*prop_id*/, double /*value*/) {
    return false;   // implemented in Task 4
}

double V4L2Capture::get(int /*prop_id*/) const {
    return 0.0;     // implemented in Task 4
}

bool V4L2Capture::ensure_streaming() {
    return false;   // implemented in Task 5
}

bool V4L2Capture::decode_into(const uint8_t* /*jpeg*/, size_t /*bytes*/, cv::Mat& /*out*/) {
    return false;   // implemented in Task 5
}
```

V4L2Capture lives in the global namespace (matching how it's referenced from the `JetsonCaptureApp` struct, also in the global namespace). Place these definitions **outside** the `namespace golf_sim { … }` block — i.e. above line 31's `namespace golf_sim {`.

- [ ] **Step 3: Build green on Jetson**

```bash
cd ~/JetsonLM/Software/LMSourceCode/ImageProcessing
ninja -C build_jetson
```

Expected: clean build, `pitrac_lm` binary produced, no warnings introduced.

- [ ] **Step 4: Commit**

```bash
git add Software/LMSourceCode/ImageProcessing/v4l2_interface.h \
        Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp
git commit -m "SP1: V4L2Capture skeleton, swap JetsonCaptureApp::cap type"
```

---

## Task 3: V4L2Capture lifecycle — open / release

Goal: open the device, verify it's a V4L2 capture device, store the fd. `release()` unwinds anything that was set up. No streaming yet.

**Files:**
- Modify: `Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp`

- [ ] **Step 1: Implement open()**

Replace the skeleton `V4L2Capture::open` body with:

```cpp
bool V4L2Capture::open(const std::string& path, int /*api_pref*/) {
    if (isOpened()) {
        release();
    }

    int fd = ::open(path.c_str(), O_RDWR | O_CLOEXEC);
    if (fd < 0) {
        GS_LOG_MSG(error, "V4L2Capture::open - ::open(\"" + path + "\") failed: "
                          + std::strerror(errno));
        return false;
    }

    v4l2_capability caps{};
    if (::ioctl(fd, VIDIOC_QUERYCAP, &caps) < 0) {
        GS_LOG_MSG(error, "V4L2Capture::open - VIDIOC_QUERYCAP failed: "
                          + std::strerror(errno));
        ::close(fd);
        return false;
    }
    if (!(caps.capabilities & V4L2_CAP_VIDEO_CAPTURE)) {
        GS_LOG_MSG(error, "V4L2Capture::open - device does not advertise VIDEO_CAPTURE: "
                          + path);
        ::close(fd);
        return false;
    }

    fd_ = fd;
    return true;
}
```

- [ ] **Step 2: Implement release()**

Replace the skeleton `V4L2Capture::release` body with:

```cpp
void V4L2Capture::release() {
    if (streaming_) {
        v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        ::ioctl(fd_, VIDIOC_STREAMOFF, &type);
        streaming_ = false;
    }

    for (auto& b : bufs_) {
        if (b.start && b.length) {
            ::munmap(b.start, b.length);
        }
    }
    bufs_.clear();

    if (tj_handle_) {
        tjDestroy(static_cast<tjhandle>(tj_handle_));
        tj_handle_ = nullptr;
    }

    if (fd_ >= 0) {
        ::close(fd_);
        fd_ = -1;
    }

    pending_ctrls_.clear();
    gray_scratch_.release();
}
```

- [ ] **Step 3: Add a `<cstring>` include**

`std::strerror` needs `<cstring>`. Find the include block at the top of `v4l2_interface.cpp` and add:

```cpp
#include <cstring>
#include <cerrno>
```

(Place near the other system headers, e.g. just after `<fcntl.h>`.)

- [ ] **Step 4: Build green on Jetson**

```bash
ninja -C ~/JetsonLM/Software/LMSourceCode/ImageProcessing/build_jetson
```

Expected: clean build.

- [ ] **Step 5: Commit**

```bash
git add Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp
git commit -m "SP1: V4L2Capture::open and release"
```

---

## Task 4: V4L2Capture set / get

Goal: handle the property API. Format-affecting properties (`WIDTH/HEIGHT/FOURCC/FPS`) update internal state and are applied at the next `ensure_streaming()` call. Control properties (`EXPOSURE/GAIN`) get applied immediately if streaming, queued otherwise.

**Files:**
- Modify: `Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp`

- [ ] **Step 1: Implement set()**

Replace the skeleton `V4L2Capture::set` with:

```cpp
bool V4L2Capture::set(int prop_id, double value) {
    if (!isOpened()) return false;

    auto apply_or_queue_ctrl = [&](uint32_t v4l2_id, int32_t v) -> bool {
        if (streaming_) {
            v4l2_control c{};
            c.id    = v4l2_id;
            c.value = v;
            if (::ioctl(fd_, VIDIOC_S_CTRL, &c) < 0) {
                GS_LOG_MSG(error, std::string("V4L2Capture::set - VIDIOC_S_CTRL(0x")
                                  + std::to_string(v4l2_id) + ") failed: "
                                  + std::strerror(errno));
                return false;
            }
        } else {
            pending_ctrls_.emplace_back(v4l2_id, v);
        }
        return true;
    };

    switch (prop_id) {
    case cv::CAP_PROP_FRAME_WIDTH:
        if (streaming_) return false;
        width_ = static_cast<int>(value);
        return true;

    case cv::CAP_PROP_FRAME_HEIGHT:
        if (streaming_) return false;
        height_ = static_cast<int>(value);
        return true;

    case cv::CAP_PROP_FPS:
        if (streaming_) return false;
        fps_ = static_cast<int>(value);
        return true;

    case cv::CAP_PROP_FOURCC: {
        if (streaming_) return false;
        const uint32_t requested = static_cast<uint32_t>(value);
        if (requested != V4L2_PIX_FMT_MJPEG) {
            GS_LOG_MSG(error, "V4L2Capture::set - only MJPEG fourcc is supported");
            return false;
        }
        fourcc_ = requested;
        return true;
    }

    case cv::CAP_PROP_EXPOSURE:
        // OV9281 / UVC: V4L2_CID_EXPOSURE_ABSOLUTE is in 100µs units.
        // Caller passes microseconds; convert.
        return apply_or_queue_ctrl(V4L2_CID_EXPOSURE_ABSOLUTE,
                                   static_cast<int32_t>(value / 100.0));

    case cv::CAP_PROP_GAIN:
        return apply_or_queue_ctrl(V4L2_CID_GAIN, static_cast<int32_t>(value));

    default:
        return false;
    }
}
```

- [ ] **Step 2: Implement get()**

Replace the skeleton `V4L2Capture::get` with:

```cpp
double V4L2Capture::get(int prop_id) const {
    switch (prop_id) {
    case cv::CAP_PROP_FRAME_WIDTH:  return static_cast<double>(width_);
    case cv::CAP_PROP_FRAME_HEIGHT: return static_cast<double>(height_);
    case cv::CAP_PROP_FOURCC:       return static_cast<double>(fourcc_);
    case cv::CAP_PROP_FPS: {
        if (!isOpened()) return static_cast<double>(fps_);
        v4l2_streamparm parm{};
        parm.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        if (::ioctl(fd_, VIDIOC_G_PARM, &parm) < 0) {
            return static_cast<double>(fps_);
        }
        const auto& tpf = parm.parm.capture.timeperframe;
        if (tpf.numerator == 0) return static_cast<double>(fps_);
        return static_cast<double>(tpf.denominator) / static_cast<double>(tpf.numerator);
    }
    default:
        return 0.0;
    }
}
```

- [ ] **Step 3: Build green on Jetson**

```bash
ninja -C ~/JetsonLM/Software/LMSourceCode/ImageProcessing/build_jetson
```

Expected: clean build.

- [ ] **Step 4: Commit**

```bash
git add Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp
git commit -m "SP1: V4L2Capture::set and get"
```

---

## Task 5: V4L2Capture lazy stream-on + read with libjpeg-turbo decode

Goal: the meaty task. First `read()` does the full V4L2 setup; subsequent reads dequeue, decode, enqueue.

**Files:**
- Modify: `Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp`

- [ ] **Step 1: Implement ensure_streaming()**

Replace the skeleton `V4L2Capture::ensure_streaming` with:

```cpp
bool V4L2Capture::ensure_streaming() {
    if (streaming_) return true;
    if (!isOpened()) return false;

    // 1. VIDIOC_S_FMT
    v4l2_format fmt{};
    fmt.type                = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    fmt.fmt.pix.width       = static_cast<__u32>(width_);
    fmt.fmt.pix.height      = static_cast<__u32>(height_);
    fmt.fmt.pix.pixelformat = fourcc_;
    fmt.fmt.pix.field       = V4L2_FIELD_NONE;
    if (::ioctl(fd_, VIDIOC_S_FMT, &fmt) < 0) {
        GS_LOG_MSG(error, "V4L2Capture::ensure_streaming - VIDIOC_S_FMT failed: "
                          + std::strerror(errno));
        return false;
    }
    width_  = static_cast<int>(fmt.fmt.pix.width);
    height_ = static_cast<int>(fmt.fmt.pix.height);

    // 2. VIDIOC_S_PARM (frame rate)
    v4l2_streamparm parm{};
    parm.type                                 = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    parm.parm.capture.timeperframe.numerator   = 1;
    parm.parm.capture.timeperframe.denominator = static_cast<__u32>(fps_);
    if (::ioctl(fd_, VIDIOC_S_PARM, &parm) < 0) {
        GS_LOG_MSG(warning, "V4L2Capture::ensure_streaming - VIDIOC_S_PARM failed: "
                            + std::strerror(errno) + " (continuing with driver default FPS)");
    }

    // 3. Apply queued controls (exposure, gain, …)
    for (const auto& [id, val] : pending_ctrls_) {
        v4l2_control c{};
        c.id    = id;
        c.value = val;
        if (::ioctl(fd_, VIDIOC_S_CTRL, &c) < 0) {
            GS_LOG_MSG(warning, std::string("V4L2Capture::ensure_streaming - VIDIOC_S_CTRL(0x")
                                + std::to_string(id) + ") failed: "
                                + std::strerror(errno));
        }
    }
    pending_ctrls_.clear();

    // 4. VIDIOC_REQBUFS
    constexpr __u32 kBufCount = 4;
    v4l2_requestbuffers req{};
    req.count  = kBufCount;
    req.type   = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    req.memory = V4L2_MEMORY_MMAP;
    if (::ioctl(fd_, VIDIOC_REQBUFS, &req) < 0) {
        GS_LOG_MSG(error, "V4L2Capture::ensure_streaming - VIDIOC_REQBUFS failed: "
                          + std::strerror(errno));
        return false;
    }
    if (req.count < 2) {
        GS_LOG_MSG(error, "V4L2Capture::ensure_streaming - driver granted "
                          + std::to_string(req.count) + " buffers, need >= 2");
        return false;
    }

    // 5. VIDIOC_QUERYBUF + mmap each
    bufs_.assign(req.count, MmapBuf{});
    for (__u32 i = 0; i < req.count; ++i) {
        v4l2_buffer buf{};
        buf.type   = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buf.memory = V4L2_MEMORY_MMAP;
        buf.index  = i;
        if (::ioctl(fd_, VIDIOC_QUERYBUF, &buf) < 0) {
            GS_LOG_MSG(error, "V4L2Capture::ensure_streaming - VIDIOC_QUERYBUF["
                              + std::to_string(i) + "] failed: " + std::strerror(errno));
            return false;
        }
        void* p = ::mmap(nullptr, buf.length, PROT_READ | PROT_WRITE,
                         MAP_SHARED, fd_, buf.m.offset);
        if (p == MAP_FAILED) {
            GS_LOG_MSG(error, "V4L2Capture::ensure_streaming - mmap[" + std::to_string(i)
                              + "] failed: " + std::strerror(errno));
            return false;
        }
        bufs_[i].start  = p;
        bufs_[i].length = buf.length;
    }

    // 6. VIDIOC_QBUF for every buffer
    for (__u32 i = 0; i < req.count; ++i) {
        v4l2_buffer buf{};
        buf.type   = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buf.memory = V4L2_MEMORY_MMAP;
        buf.index  = i;
        if (::ioctl(fd_, VIDIOC_QBUF, &buf) < 0) {
            GS_LOG_MSG(error, "V4L2Capture::ensure_streaming - VIDIOC_QBUF["
                              + std::to_string(i) + "] failed: " + std::strerror(errno));
            return false;
        }
    }

    // 7. VIDIOC_STREAMON
    v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (::ioctl(fd_, VIDIOC_STREAMON, &type) < 0) {
        GS_LOG_MSG(error, "V4L2Capture::ensure_streaming - VIDIOC_STREAMON failed: "
                          + std::strerror(errno));
        return false;
    }

    // 8. Allocate decode scratch + decoder handle
    gray_scratch_.create(height_, width_, CV_8UC1);
    if (!tj_handle_) {
        tj_handle_ = tjInitDecompress();
        if (!tj_handle_) {
            GS_LOG_MSG(error, "V4L2Capture::ensure_streaming - tjInitDecompress failed");
            return false;
        }
    }

    streaming_ = true;
    return true;
}
```

- [ ] **Step 2: Implement decode_into()**

Replace the skeleton `V4L2Capture::decode_into` with:

```cpp
bool V4L2Capture::decode_into(const uint8_t* jpeg, size_t bytes, cv::Mat& out) {
    const int rc = tjDecompress2(static_cast<tjhandle>(tj_handle_),
                                  jpeg, static_cast<unsigned long>(bytes),
                                  gray_scratch_.data,
                                  width_, /*pitch=*/width_, height_,
                                  TJPF_GRAY, /*flags=*/0);
    if (rc != 0) {
        GS_LOG_MSG(error, std::string("V4L2Capture::decode_into - tjDecompress2 failed: ")
                          + tjGetErrorStr2(static_cast<tjhandle>(tj_handle_)));
        return false;
    }
    cv::cvtColor(gray_scratch_, out, cv::COLOR_GRAY2BGR);
    return true;
}
```

- [ ] **Step 3: Implement read()**

Replace the skeleton `V4L2Capture::read` with:

```cpp
bool V4L2Capture::read(cv::Mat& out) {
    if (!isOpened()) return false;
    if (!streaming_ && !ensure_streaming()) return false;

    v4l2_buffer buf{};
    buf.type   = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_MMAP;
    if (::ioctl(fd_, VIDIOC_DQBUF, &buf) < 0) {
        GS_LOG_MSG(error, "V4L2Capture::read - VIDIOC_DQBUF failed: "
                          + std::strerror(errno));
        return false;
    }

    const bool decoded = decode_into(static_cast<const uint8_t*>(bufs_[buf.index].start),
                                     buf.bytesused, out);

    // Re-queue regardless of decode success so the camera doesn't stall.
    if (::ioctl(fd_, VIDIOC_QBUF, &buf) < 0) {
        GS_LOG_MSG(error, "V4L2Capture::read - VIDIOC_QBUF[" + std::to_string(buf.index)
                          + "] failed: " + std::strerror(errno));
        return false;
    }

    return decoded;
}
```

- [ ] **Step 4: Build green on Jetson**

```bash
ninja -C ~/JetsonLM/Software/LMSourceCode/ImageProcessing/build_jetson
```

Expected: clean build, `pitrac_lm` binary produced.

No functional smoke yet — `PerformCameraSystemStartup` is still a stub, so nothing actually opens a camera at runtime. The functional verification of `V4L2Capture::read()` happens at Task 6 once `PerformCameraSystemStartup` populates the `JetsonCaptureApp` slots.

- [ ] **Step 5: Commit**

```bash
git add Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp
git commit -m "SP1: V4L2Capture lazy stream-on + read with libjpeg-turbo decode"
```

---

## Task 6: PerformCameraSystemStartup

Goal: probe `/dev/video0` and `/dev/video2` (the OV9281 device mapping confirmed in LOGBOOK 2026-03-21), allocate `JetsonCaptureApp` instances, populate `LibCameraInterface::libcamera_app_[0/1]`, apply per-camera defaults (exposure/gain/contrast/saturation from the existing `kCameraN*` static members).

**Files:**
- Modify: `Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp`

- [ ] **Step 1: Replace the stub**

Find the existing stub:

```cpp
bool PerformCameraSystemStartup() {
    // JETSON_STUB
    return false;
}
```

Replace with:

```cpp
namespace {

bool probe_v4l2_capture_device(const std::string& path) {
    int fd = ::open(path.c_str(), O_RDWR | O_CLOEXEC);
    if (fd < 0) {
        GS_LOG_MSG(error, "probe_v4l2_capture_device - cannot open " + path
                          + ": " + std::strerror(errno));
        return false;
    }
    v4l2_capability caps{};
    const int rc = ::ioctl(fd, VIDIOC_QUERYCAP, &caps);
    ::close(fd);
    if (rc < 0) {
        GS_LOG_MSG(error, "probe_v4l2_capture_device - QUERYCAP failed on " + path);
        return false;
    }
    if (!(caps.capabilities & V4L2_CAP_VIDEO_CAPTURE)) {
        GS_LOG_MSG(error, "probe_v4l2_capture_device - " + path + " is not a capture device");
        return false;
    }
    GS_LOG_TRACE_MSG(trace, std::string("Probed ") + path + " — driver=\""
                            + reinterpret_cast<const char*>(caps.driver) + "\" card=\""
                            + reinterpret_cast<const char*>(caps.card) + "\"");
    return true;
}

JetsonCaptureApp* build_app(int slot, const std::string& path) {
    auto* app = new JetsonCaptureApp;
    app->camera_slot     = slot;
    app->device_path     = path;
    app->width           = 1280;
    app->height          = 800;
    if (slot == 0) {
        app->gain            = LibCameraInterface::kCamera1Gain;
        app->contrast        = LibCameraInterface::kCamera1Contrast;
        app->saturation      = LibCameraInterface::kCamera1Saturation;
        app->shutter_time_us = LibCameraInterface::kCamera1StillShutterTimeuS;
    } else {
        app->gain            = LibCameraInterface::kCamera2Gain;
        app->contrast        = LibCameraInterface::kCamera2Contrast;
        app->saturation      = LibCameraInterface::kCamera2Saturation;
        app->shutter_time_us = LibCameraInterface::kCamera2StillShutterTimeuS;
    }
    app->flip_vertical = false;
    return app;
}

}  // namespace

bool PerformCameraSystemStartup() {
    // OV9281 device mapping confirmed in LOGBOOK 2026-03-21:
    //   /dev/video0  → camera 1 (USB bus xhci-2.2.4)
    //   /dev/video2  → camera 2 (USB bus xhci-2.3)
    // /dev/video1 and /dev/video3 are UVC metadata devices and are skipped.
    static const char* kSlot0Path = "/dev/video0";
    static const char* kSlot1Path = "/dev/video2";

    if (!probe_v4l2_capture_device(kSlot0Path)) return false;
    if (!probe_v4l2_capture_device(kSlot1Path)) return false;

    // Replace any previously allocated app pointers (idempotent re-init).
    delete LibCameraInterface::libcamera_app_[0];
    delete LibCameraInterface::libcamera_app_[1];
    LibCameraInterface::libcamera_app_[0] = build_app(0, kSlot0Path);
    LibCameraInterface::libcamera_app_[1] = build_app(1, kSlot1Path);

    LibCameraInterface::libcamera_configuration_[0] =
        LibCameraInterface::CameraConfiguration::kHighSpeedWatching;
    LibCameraInterface::libcamera_configuration_[1] =
        LibCameraInterface::CameraConfiguration::kExternallyStrobed;

    GS_LOG_TRACE_MSG(trace, "PerformCameraSystemStartup - Jetson camera apps allocated for "
                            + std::string(kSlot0Path) + " and " + std::string(kSlot1Path));
    return true;
}
```

- [ ] **Step 2: Build green on Jetson**

```bash
ninja -C ~/JetsonLM/Software/LMSourceCode/ImageProcessing/build_jetson
```

Expected: clean build.

- [ ] **Step 3: Functional smoke — Jetson, both cameras connected**

Run pitrac_lm in any system mode that calls `PerformCameraSystemStartup`. With logging at trace, you should see:

```
... Probed /dev/video0 — driver="uvcvideo" card="USB Camera: OV9281" ...
... Probed /dev/video2 — driver="uvcvideo" card="USB Camera: OV9281" ...
... PerformCameraSystemStartup - Jetson camera apps allocated for /dev/video0 and /dev/video2 ...
```

Use the existing camera-test mode (smallest exercise of the path):

```bash
cd ~/JetsonLM/Software/LMSourceCode/ImageProcessing/build_jetson
./pitrac_lm --system_mode=camera1_test_standalone --logging_level=trace 2>&1 | head -200
```

Expected: log lines above appear, no errors before the test mode reaches its main work. (It may then proceed to `TakeRawPicture` which is still a stub returning false — that's expected this task.)

- [ ] **Step 4: Commit**

```bash
git add Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp
git commit -m "SP1: PerformCameraSystemStartup — probe OV9281 cameras, allocate apps"
```

---

## Task 7: TakeRawPicture

Goal: real V4L2-backed still capture per camera. The Jetson version does not call `undistort_camera_image` (that helper is in `libcamera_interface.cpp` which is fully `#ifndef JETSON_BUILD`-guarded; porting it is out of scope for this session).

**Files:**
- Modify: `Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp`

- [ ] **Step 1: Replace the stub**

Find:

```cpp
bool TakeRawPicture(const GolfSimCamera& /*camera*/, cv::Mat& /*img*/) {
    // JETSON_STUB
    return false;
}
```

Replace with:

```cpp
bool TakeRawPicture(const GolfSimCamera& camera, cv::Mat& img) {
    const GsCameraNumber camera_number = camera.camera_hardware_.camera_number_;
    const int slot = (camera_number == GsCameraNumber::kGsCamera1) ? 0 : 1;

    JetsonCaptureApp* app = LibCameraInterface::libcamera_app_[slot];
    if (!app) {
        GS_LOG_MSG(error, "TakeRawPicture - camera slot " + std::to_string(slot)
                          + " not initialised; call PerformCameraSystemStartup first");
        return false;
    }

    if (!app->cap.isOpened()) {
        if (!app->cap.open(app->device_path)) {
            GS_LOG_MSG(error, "TakeRawPicture - failed to open " + app->device_path);
            return false;
        }
        // Apply per-camera config.  Order matters: format/FPS before EXPOSURE/GAIN
        // so that pending controls land on the streaming device.
        app->cap.set(cv::CAP_PROP_FRAME_WIDTH,  static_cast<double>(app->width));
        app->cap.set(cv::CAP_PROP_FRAME_HEIGHT, static_cast<double>(app->height));
        app->cap.set(cv::CAP_PROP_FOURCC,
                     static_cast<double>(V4L2_PIX_FMT_MJPEG));
        app->cap.set(cv::CAP_PROP_FPS, 120.0);
        app->cap.set(cv::CAP_PROP_EXPOSURE,
                     static_cast<double>(app->shutter_time_us));
        app->cap.set(cv::CAP_PROP_GAIN, app->gain);
    }

    if (!app->cap.read(img) || img.empty()) {
        GS_LOG_MSG(error, "TakeRawPicture - cap.read() failed for " + app->device_path);
        return false;
    }
    return true;
}
```

- [ ] **Step 2: Build green on Jetson**

```bash
ninja -C ~/JetsonLM/Software/LMSourceCode/ImageProcessing/build_jetson
```

- [ ] **Step 3: Functional smoke — Jetson, both cameras connected**

Run a system mode that calls `TakeRawPicture` once and writes the result to disk. `kCamera1TestStandalone` and `kCamera2TestStandalone` exercise the still-capture path.

```bash
cd ~/JetsonLM/Software/LMSourceCode/ImageProcessing/build_jetson
./pitrac_lm --system_mode=camera1_test_standalone --logging_level=trace 2>&1 | tail -50
./pitrac_lm --system_mode=camera2_test_standalone --logging_level=trace 2>&1 | tail -50
```

Expected for each: no `TakeRawPicture - cap.read() failed` line. Whatever output image the test mode writes (look for "saved to" / "wrote" in the log) is a valid 1280×800 BGR image — load it in any image viewer to confirm.

If either test mode reports `cap.read() failed`, paste the log here for diagnosis.

- [ ] **Step 4: Commit**

```bash
git add Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp
git commit -m "SP1: TakeRawPicture — real V4L2 still capture via JetsonCaptureApp"
```

---

## Task 8: CheckForBall

Goal: real ball detection on a single still capture. Inlines a copy of the legacy detection body (`CheckForBallLegacy` in the RPi build) because that source file is fully `#ifndef JETSON_BUILD`-guarded on Jetson. The legacy body uses only hardware-independent code (`GolfSimCamera::GetCalibratedBall`, `BallImageProc`), so copying it is safe. The YOLO/ONNX path (`CheckForBallEnhanced`) is left for a follow-up.

**Files:**
- Modify: `Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp`

- [ ] **Step 1: Add the include for CameraHardware**

Add to the include block at the top of `v4l2_interface.cpp`:

```cpp
#include "camera_hardware.h"
```

- [ ] **Step 2: Replace the stub**

Find:

```cpp
bool CheckForBall(GolfBall& /*ball*/, cv::Mat& /*return_image*/) {
    // JETSON_STUB
    return false;
}
```

Replace with (this is the legacy detection body adapted for Jetson — the `firstCannedImageFileName` line from the original is dropped because that fixture path is RPi-development-specific):

```cpp
bool CheckForBall(GolfBall& ball, cv::Mat& img) {
    GsCameraNumber camera_number =
        GolfSimOptions::GetCommandLineOptions().GetCameraNumber();

    const CameraHardware::CameraModel camera_model =
        (camera_number == GsCameraNumber::kGsCamera1)
            ? GolfSimCamera::kSystemSlot1CameraType
            : GolfSimCamera::kSystemSlot2CameraType;
    const CameraHardware::LensType camera_lens_type =
        (camera_number == GsCameraNumber::kGsCamera1)
            ? GolfSimCamera::kSystemSlot1LensType
            : GolfSimCamera::kSystemSlot2LensType;
    const CameraHardware::CameraOrientation camera_orientation =
        (camera_number == GsCameraNumber::kGsCamera1)
            ? GolfSimCamera::kSystemSlot1CameraOrientation
            : GolfSimCamera::kSystemSlot2CameraOrientation;

    GolfSimCamera camera;
    camera.camera_hardware_.init_camera_parameters(camera_number,
                                                    camera_model,
                                                    camera_lens_type,
                                                    camera_orientation);

    if (!TakeRawPicture(camera, img)) {
        GS_LOG_MSG(error, "CheckForBall - TakeRawPicture failed");
        return false;
    }

    cv::Vec2i search_area_center = camera.GetExpectedBallCenter();
    bool expectBall = false;
    return camera.GetCalibratedBall(camera, img, ball, search_area_center, expectBall);
}
```

- [ ] **Step 3: Build green on Jetson**

```bash
ninja -C ~/JetsonLM/Software/LMSourceCode/ImageProcessing/build_jetson
```

- [ ] **Step 4: Functional smoke — Jetson, ball placed in front of camera 1**

Place a golf ball roughly in the center of camera 1's field of view, then:

```bash
cd ~/JetsonLM/Software/LMSourceCode/ImageProcessing/build_jetson
./pitrac_lm --system_mode=camera1_ball_location --logging_level=trace 2>&1 | tail -100
```

Expected: log lines from `GetCalibratedBall` indicating ball detection (or its diagnostic output if no ball is found). No `CheckForBall - TakeRawPicture failed` line. If the binary has another mode flag for ball-location standalone testing, use that; the goal is exercising `CheckForBall(...)` once.

- [ ] **Step 5: Commit**

```bash
git add Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp
git commit -m "SP1: CheckForBall — legacy detection body via real V4L2 capture"
```

---

## Task 9: WatchForHitAndTrigger

Goal: hand off to the existing `ball_watcher_event_loop` against camera 1's `JetsonCaptureApp`. The IPC trigger to camera 2 stays a no-op (`PulseStrobe::SendExternalTrigger()` remains the existing stub). The motion-detection half drives the loop.

**Files:**
- Modify: `Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp`

- [ ] **Step 1: Add the ball_watcher.h include**

Add to the include block at the top of `v4l2_interface.cpp`:

```cpp
#include "ball_watcher.h"
```

- [ ] **Step 2: Replace the stub**

Find:

```cpp
bool WatchForHitAndTrigger(const GolfBall& ball, cv::Mat& return_image,
                           bool& motion_detected) {
    // JETSON_STUB: two-camera IPC flow not yet validated on Jetson
    motion_detected = false;
    return false;
}
```

Replace with:

```cpp
bool WatchForHitAndTrigger(const GolfBall& /*ball*/, cv::Mat& /*return_image*/,
                           bool& motion_detected) {
    // Jetson: motion-only.  PulseStrobe::SendExternalTrigger() inside the
    // motion-detect path is currently a stub; the IR strobe wiring is a
    // separate sub-project (Group 2 strobe SPI work).  Returning the
    // motion result is enough for the upstream FSM to advance.
    motion_detected = false;

    JetsonCaptureApp* app = LibCameraInterface::libcamera_app_[0];
    if (!app) {
        GS_LOG_MSG(error, "WatchForHitAndTrigger - camera 1 slot not initialised; "
                          "call PerformCameraSystemStartup first");
        return false;
    }

    return ball_watcher_event_loop(*app, motion_detected);
}
```

- [ ] **Step 3: Build green on Jetson**

```bash
ninja -C ~/JetsonLM/Software/LMSourceCode/ImageProcessing/build_jetson
```

- [ ] **Step 4: Functional smoke — Jetson, motion detection**

Run pitrac_lm in the standard camera1 mode (which calls `WatchForHitAndTrigger`):

```bash
cd ~/JetsonLM/Software/LMSourceCode/ImageProcessing/build_jetson
./pitrac_lm --system_mode=camera1 --logging_level=trace 2>&1 | tee /tmp/sp1_motion.log
```

While it's running, wave a hand across camera 1's field of view. Expected:

- During the static period, log shows the loop running at ~120 FPS (motion_detect_stage logs frame counter).
- When you wave, the loop exits with `motion_detected = true` and the program advances past the watch step.

To confirm sustained 120 FPS, grep for the frame counter in the log and compute. A simple proxy: the loop should accumulate >100 frames per second of wall time. Measure with:

```bash
grep -c 'motion_detect_stage' /tmp/sp1_motion.log
```

Compared against the wall-clock duration of the run, the ratio should be ≥115 fps over a window of at least 30 seconds.

- [ ] **Step 5: Commit**

```bash
git add Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp
git commit -m "SP1: WatchForHitAndTrigger — route to ball_watcher_event_loop (motion-only)"
```

---

## Task 10: End-to-end verification + LOGBOOK update

Goal: confirm the spec's acceptance criteria, update `LOGBOOK.md` with the new SP1 status.

This task does not edit code. It produces evidence and a logbook entry.

- [ ] **Step 1: Acceptance check 1 — clean build**

On the Jetson, from a fresh checkout:

```bash
cd ~/JetsonLM
git pull
cd Software/LMSourceCode/ImageProcessing
meson setup build_jetson --wipe -Djetson_build=true
ninja -C build_jetson
```

Expected: configure + build complete with no errors and no new warnings.

- [ ] **Step 2: Acceptance check 2 — startup opens both cameras**

```bash
./build_jetson/pitrac_lm --system_mode=camera1_test_standalone --logging_level=trace 2>&1 | grep -E "Probed|allocated"
```

Expected lines (text after the dashes will vary):

```
... Probed /dev/video0 — driver="..." card="..."
... Probed /dev/video2 — driver="..." card="..."
... PerformCameraSystemStartup - Jetson camera apps allocated ...
```

- [ ] **Step 3: Acceptance check 3 — sustained ≥115 FPS over 60s**

Run the watch loop for 60 seconds and measure:

```bash
timeout 60 ./build_jetson/pitrac_lm --system_mode=camera1 --logging_level=trace 2>&1 \
    | tee /tmp/sp1_60s.log
# Count frames processed and divide by 60
grep -c 'motion_detect_stage::Process' /tmp/sp1_60s.log
```

Expected: ≥6900 (= 115 fps × 60s).

If below ~100 fps, libjpeg-turbo decode time may be the bottleneck. Capture per-frame timing by enabling trace-level logging in `V4L2Capture::read()` — add `auto t0 = std::chrono::high_resolution_clock::now();` around `decode_into()` and log the delta. (This profiling instrumentation is **not** part of this task's commits; it stays local on the Jetson.) If decode > 5 ms/frame, the spec's "Risks" section #1 applies and we re-open the design for a producer thread.

- [ ] **Step 4: Acceptance check 4 — TakeRawPicture per camera**

Whatever image-output side-effect the camera test modes have on this build (typically writing a PNG or JPG to disk), confirm one valid 1280×800 image is produced from each camera:

```bash
./build_jetson/pitrac_lm --system_mode=camera1_test_standalone
./build_jetson/pitrac_lm --system_mode=camera2_test_standalone
# Inspect whichever output file paths the binary reports in its log
```

Expected: both produce a non-empty BGR image at 1280×800. If you can't find the output file, grep the trace log for `wrote` / `saved` / `jpg` / `png`.

- [ ] **Step 5: Acceptance check 5 — CheckForBall**

```bash
# Place a golf ball in front of camera 1
./build_jetson/pitrac_lm --system_mode=camera1_ball_location --logging_level=trace 2>&1 | tail -50
```

Expected: log shows `GetCalibratedBall` ran and reported either a found-ball circle or its no-match diagnostic. Either is a pass — the function exited the V4L2 capture path successfully and reached the detector.

- [ ] **Step 6: Acceptance check 6 — WatchForHitAndTrigger**

Already covered by Task 9 step 4; if you skipped it, run again now and verify `motion_detected = true` after a hand wave.

- [ ] **Step 7: Update LOGBOOK.md**

Add a new entry to `LOGBOOK.md` Sub-Project 1 Session Notes (around line 528, after the most recent 2026-04-26 entry):

```markdown
**2026-04-29**
> Implemented real V4L2 capture engine in v4l2_interface.cpp.  V4L2Capture
> class replaces cv::VideoCapture inside JetsonCaptureApp.  Uses ioctl +
> mmap (4 buffers) + libjpeg-turbo gray decode + cvtColor to BGR.
> 4 of 5 stub functions now real: PerformCameraSystemStartup, TakeRawPicture,
> CheckForBall, WatchForHitAndTrigger (motion-only).  WaitForCam2Trigger
> stays stubbed pending IR strobe + SPI work.
> Sustained <fps> FPS over 60s on camera 1 in WatchForHitAndTrigger.
> Acceptance criteria 1-6 from design spec all green.
> meson dep added: libturbojpeg (apt: libturbojpeg0-dev).
> Files touched (3): v4l2_interface.h, v4l2_interface.cpp, meson.build.
> Next: IR strobe + SPI, undistort_camera_image port, calibration runs.
```

(Replace `<fps>` with the measured value from Step 3.)

Add to the SP1 Tests table around line 416:

```markdown
|2026-04-29|Sustained 120 FPS @ 1280x800 MJPG via real C++ V4L2 capture engine|`timeout 60 ./pitrac_lm --system_mode=camera1` over 60s, count motion_detect_stage::Process log lines|✅ PASS|<measured_fps> fps. libjpeg-turbo gray decode ~<X> ms/frame.|
```

Update SP1 Master Overview row (line 17) to mark `% Complete` at `85%` (V4L2 engine done; remaining: IR strobe, undistort port, calibration, mounting).

Tick off the relevant checkbox in `PORTING_TASKS.md` Group 2 — the `libcamera_interface.cpp — TakeLibcameraStill` and adjacent items have been served by the V4L2Capture engine via `TakeRawPicture`. (`pulse_strobe.cpp` items remain unchecked.)

- [ ] **Step 8: Final commit**

```bash
git add LOGBOOK.md PORTING_TASKS.md
git commit -m "LOGBOOK: SP1 V4L2 capture engine landed, 120 FPS sustained on Jetson"
```

---

## Out of scope for this plan (intentional)

- Background producer thread + ring buffer. Synchronous read() only. Re-open the design if Task 10 Step 3 measures < 100 fps.
- nvJPEG decode. Needs CUDA-aware OpenCV, not present on this build (Issue #13).
- IR strobe GPIO/SPI (`pulse_strobe.cpp` Group 2 work). IR LED array not ordered.
- `WaitForCam2Trigger`. Without strobe, no synchronized exposure to capture. Stays stubbed.
- Porting `undistort_camera_image`, `TakeLibcameraStill`, `ConfigureForLibcameraStill`, `RetrieveCameraInfo`, `DiscoverCameraLocation`, `SendCameraCroppingCommand`. Currently undefined-but-unreferenced on the Jetson link; leaving alone until a caller actually needs them.
- Cropped/high-FPS sub-resolution mode (`ConfigCameraForCropping`, `ConfigureLibCameraOptions`, `SendCameraCroppingCommand`). The full-frame 1280×800 @ 120 FPS path is enough for v1; the cropped optimization path can land when ball-detection profiling shows it's needed.
