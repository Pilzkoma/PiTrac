
/*****************************************************************//**
 * \file   v4l2_interface.cpp
 * \brief  Jetson replacement for libcamera_interface.cpp.
 *         Contains stub implementations of functions that are
 *         no-ops or deferred on the initial Jetson build.
 *         Group 2 runtime implementations will be added here once
 *         cameras arrive and the first meson configure is clean.
 *
 * \author JetsonLM port
 * \date   2026-03-16
 *********************************************************************/

/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Copyright (C) 2022-2025, Verdant Consultants, LLC.
 */

#ifdef JETSON_BUILD  // JETSON_STUB: Jetson-only — excluded on RPi build

#ifdef __unix__  // Ignore in Windows environment

#include "v4l2_interface.h"
#include "motion_detect.h"
#include "gs_config.h"
#include "logging_tools.h"
#include "pulse_strobe.h"
#include "golf_ball.h"
#include "gs_camera.h"
#include "camera_hardware.h"
#include "gs_options.h"
#include "ball_watcher.h"

#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/videodev2.h>
#include <turbojpeg.h>

#include <cerrno>
#include <cstring>
#include <chrono>

#include <opencv2/calib3d.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/videoio.hpp>


// ---------------------------------------------------------------------------
// V4L2Capture skeleton — full bodies land in subsequent commits.
// Skeleton bodies make the class linkable so the build stays green.
// Lives in the global namespace, matching the JetsonCaptureApp struct
// declared in v4l2_interface.h.
// ---------------------------------------------------------------------------

V4L2Capture::V4L2Capture() {
    fourcc_ = V4L2_PIX_FMT_MJPEG;
}

V4L2Capture::~V4L2Capture() {
    release();
}

bool V4L2Capture::open(const std::string& path, int /*api_pref*/) {
    GS_LOG_TRACE_MSG(trace, "V4L2Capture::open(" + path + ") - was_open="
                            + std::string(isOpened() ? "true" : "false"));
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
                          + std::string(std::strerror(errno)));
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
    GS_LOG_TRACE_MSG(trace, "V4L2Capture::open(" + path + ") - success, fd=" + std::to_string(fd_));
    return true;
}

bool V4L2Capture::isOpened() const {
    return fd_ >= 0;
}

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

bool V4L2Capture::read(cv::Mat& out) {
    if (!isOpened()) return false;
    if (!streaming_ && !ensure_streaming()) return false;

    v4l2_buffer buf{};
    buf.type   = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_MMAP;
    if (::ioctl(fd_, VIDIOC_DQBUF, &buf) < 0) {
        GS_LOG_MSG(error, std::string("V4L2Capture::read - VIDIOC_DQBUF failed: ")
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

    // Per-instance FPS log.  Logs every frame for the first 5 (so we see
    // even very short loops), then every 10 frames thereafter, so we get
    // both short-burst and long-loop measurements.
    ++frame_count_;
    auto now = std::chrono::steady_clock::now();
    if (frame_count_ == 1) {
        fps_log_start_ = now;
    }
    const bool log_this = (frame_count_ <= 5) || (frame_count_ % 10 == 0);
    if (log_this) {
        const double elapsed_s = std::chrono::duration<double>(now - fps_log_start_).count();
        const double avg_fps   = (elapsed_s > 0.0)
                                 ? (static_cast<double>(frame_count_) / elapsed_s)
                                 : 0.0;
        GS_LOG_TRACE_MSG(trace, "V4L2Capture - frame=" + std::to_string(frame_count_)
                                + " decoded=" + std::string(decoded ? "1" : "0")
                                + " elapsed=" + std::to_string(elapsed_s) + "s avg_fps="
                                + std::to_string(avg_fps));
    }

    return decoded;
}

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

bool V4L2Capture::ensure_streaming() {
    if (streaming_) return true;
    if (!isOpened()) return false;

    // Every failure path below calls release() before returning false so
    // /dev/videoX is not left open with partially-allocated state — that
    // used to require an external `rmmod uvcvideo && modprobe uvcvideo`
    // to recover (Issue #17).  release() is idempotent and tolerates any
    // partial state.

    // 1. VIDIOC_S_FMT
    v4l2_format fmt{};
    fmt.type                = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    fmt.fmt.pix.width       = static_cast<__u32>(width_);
    fmt.fmt.pix.height      = static_cast<__u32>(height_);
    fmt.fmt.pix.pixelformat = fourcc_;
    fmt.fmt.pix.field       = V4L2_FIELD_NONE;
    if (::ioctl(fd_, VIDIOC_S_FMT, &fmt) < 0) {
        GS_LOG_MSG(error, std::string("V4L2Capture::ensure_streaming - VIDIOC_S_FMT failed: ")
                          + std::strerror(errno));
        release();
        return false;
    }
    width_  = static_cast<int>(fmt.fmt.pix.width);
    height_ = static_cast<int>(fmt.fmt.pix.height);

    // 2. VIDIOC_S_PARM (frame rate) — non-fatal, warn only
    v4l2_streamparm parm{};
    parm.type                                   = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    parm.parm.capture.timeperframe.numerator    = 1;
    parm.parm.capture.timeperframe.denominator  = static_cast<__u32>(fps_);
    if (::ioctl(fd_, VIDIOC_S_PARM, &parm) < 0) {
        GS_LOG_MSG(warning, std::string("V4L2Capture::ensure_streaming - VIDIOC_S_PARM failed: ")
                            + std::strerror(errno) + " (continuing with driver default FPS)");
    }

    // 3. Apply queued controls (exposure, gain, …) — non-fatal, warn only
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
        GS_LOG_MSG(error, std::string("V4L2Capture::ensure_streaming - VIDIOC_REQBUFS failed: ")
                          + std::strerror(errno));
        release();
        return false;
    }
    if (req.count < 2) {
        GS_LOG_MSG(error, "V4L2Capture::ensure_streaming - driver granted "
                          + std::to_string(req.count) + " buffers, need >= 2");
        release();
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
            release();
            return false;
        }
        void* p = ::mmap(nullptr, buf.length, PROT_READ | PROT_WRITE,
                         MAP_SHARED, fd_, buf.m.offset);
        if (p == MAP_FAILED) {
            GS_LOG_MSG(error, "V4L2Capture::ensure_streaming - mmap[" + std::to_string(i)
                              + "] failed: " + std::strerror(errno));
            release();
            return false;
        }
        bufs_[i].start  = p;
        bufs_[i].length = buf.length;
    }

    // 6. Allocate decode scratch + decoder handle BEFORE STREAMON, so any
    // failure here doesn't leave the kernel in streaming state.
    gray_scratch_.create(height_, width_, CV_8UC1);
    if (!tj_handle_) {
        tj_handle_ = tjInitDecompress();
        if (!tj_handle_) {
            GS_LOG_MSG(error, "V4L2Capture::ensure_streaming - tjInitDecompress failed");
            release();
            return false;
        }
    }

    // 7. VIDIOC_QBUF for every buffer
    for (__u32 i = 0; i < req.count; ++i) {
        v4l2_buffer buf{};
        buf.type   = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buf.memory = V4L2_MEMORY_MMAP;
        buf.index  = i;
        if (::ioctl(fd_, VIDIOC_QBUF, &buf) < 0) {
            GS_LOG_MSG(error, "V4L2Capture::ensure_streaming - VIDIOC_QBUF["
                              + std::to_string(i) + "] failed: " + std::strerror(errno));
            release();
            return false;
        }
    }

    // 8. VIDIOC_STREAMON — point of no return.  Only set streaming_=true
    // AFTER the ioctl succeeds, so release() on a STREAMON-failure path
    // doesn't issue an unnecessary STREAMOFF.
    v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (::ioctl(fd_, VIDIOC_STREAMON, &type) < 0) {
        GS_LOG_MSG(error, std::string("V4L2Capture::ensure_streaming - VIDIOC_STREAMON failed: ")
                          + std::strerror(errno));
        release();
        return false;
    }
    streaming_ = true;

    // Reset per-stream FPS counters so each ensure_streaming session
    // reports its own rate (rather than accumulated across reopens).
    frame_count_   = 0;
    fps_log_start_ = std::chrono::steady_clock::now();

    return true;
}

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


namespace golf_sim {

    // -----------------------------------------------------------------------
    // LibCameraInterface static member definitions
    // Copied from libcamera_interface.cpp — values are identical on Jetson.
    // libcamera_app_[] type changed from LibcameraJpegApp* to JetsonCaptureApp*.
    // -----------------------------------------------------------------------

    uint LibCameraInterface::kMaxWatchingCropWidth  = 96;
    uint LibCameraInterface::kMaxWatchingCropHeight = 88;

    double LibCameraInterface::kCamera1Gain                    = 6.0;
    double LibCameraInterface::kCamera1Saturation              = 1.0;
    double LibCameraInterface::kCamera1HighFPSGain             = 15.0;
    double LibCameraInterface::kCamera1Contrast                = 1.0;
    double LibCameraInterface::kCamera2Gain                    = 6.0;
    double LibCameraInterface::kCamera2Saturation              = 1.0;
    double LibCameraInterface::kCamera2ComparisonGain          = 0.8;
    double LibCameraInterface::kCamera2StrobedEnvironmentGain  = 0.8;
    double LibCameraInterface::kCamera2Contrast                = 1.0;
    double LibCameraInterface::kCamera2CalibrateOrLocationGain = 1.0;
    double LibCameraInterface::kCamera2PuttingGain             = 4.0;
    double LibCameraInterface::kCamera2PuttingContrast         = 1.0;

    std::string LibCameraInterface::kCameraMotionDetectSettings = "./assets/motion_detect.json";

    long LibCameraInterface::kCamera1StillShutterTimeuS = 15000;
    long LibCameraInterface::kCamera2StillShutterTimeuS = 15000;

    // Default values based on empirical measurements using a 6mm lens
    int LibCameraInterface::kCroppedImagePixelOffsetLeft = -5;
    int LibCameraInterface::kCroppedImagePixelOffsetUp   = -13;

    LibCameraInterface::CropConfiguration LibCameraInterface::camera_crop_configuration_ = LibCameraInterface::kCropUnknown;
    cv::Vec2i LibCameraInterface::current_watch_resolution_;
    cv::Vec2i LibCameraInterface::current_watch_offset_;

    LibCameraInterface::CameraConfiguration LibCameraInterface::libcamera_configuration_[] = {
        LibCameraInterface::CameraConfiguration::kNotConfigured,
        LibCameraInterface::CameraConfiguration::kNotConfigured
    };

    // JetsonCaptureApp* replaces LibcameraJpegApp* from the RPi build
    JetsonCaptureApp* LibCameraInterface::libcamera_app_[] = { nullptr, nullptr };

    bool camera_location_found_       = false;
    int  previously_found_media_number_  = -1;
    int  previously_found_device_number_ = -1;


    // -----------------------------------------------------------------------
    // SetLibCameraLoggingOff
    // On RPi this suppressed libcamera log output.  No libcamera logging
    // exists on Jetson — nothing to suppress.
    // -----------------------------------------------------------------------
    void LibCameraInterface::SetLibCameraLoggingOff() {
        // JETSON_STUB: no libcamera logging to suppress on Jetson
    }


    // -----------------------------------------------------------------------
    // undistort_camera_image
    // Body copied verbatim from libcamera_interface.cpp:950 — pure OpenCV
    // (initUndistortRectifyMap + remap), no libcamera/rpicam-apps dependency.
    // Returns the input image unchanged when use_undistortion_matrix_ is false,
    // so it's safe to call before camera calibration loads a real matrix.
    // -----------------------------------------------------------------------
    cv::Mat LibCameraInterface::undistort_camera_image(const cv::Mat& img, const GolfSimCamera& camera) {

        if (!camera.camera_hardware_.use_undistortion_matrix_) {
            GS_LOG_MSG(trace, "undistort_camera_image ignoring camera with no undistortion matrix. Returning original image.");
            return img;
        }

        cv::Mat cameracalibrationMatrix_ = camera.camera_hardware_.calibrationMatrix_;
        cv::Mat cameraDistortionVector_  = camera.camera_hardware_.cameraDistortionVector_;

        cv::Mat unDistortedBall1Img;
        cv::Mat m_undistMap1, m_undistMap2;

        if (camera.camera_hardware_.camera_is_mono()) {
            cv::initUndistortRectifyMap(cameracalibrationMatrix_, cameraDistortionVector_, cv::Mat(),
                                        cameracalibrationMatrix_, cv::Size(img.cols, img.rows),
                                        CV_8UC1, m_undistMap1, m_undistMap2);
        }
        else {
            cv::initUndistortRectifyMap(cameracalibrationMatrix_, cameraDistortionVector_, cv::Mat(),
                                        cameracalibrationMatrix_, cv::Size(img.cols, img.rows),
                                        CV_32FC1, m_undistMap1, m_undistMap2);
        }

        cv::remap(img, unDistortedBall1Img, m_undistMap1, m_undistMap2, cv::INTER_LINEAR);

        return unDistortedBall1Img;
    }


    // -----------------------------------------------------------------------
    // ConfigurePostProcessing
    // Identical to the RPi implementation: all body lines are
    // GolfSimConfiguration::SetConstant calls and
    // MotionDetectStage::incoming_configuration assignments.
    // Zero libcamera or rpicam-apps types — copied verbatim.
    // -----------------------------------------------------------------------
    bool ConfigurePostProcessing(const cv::Vec2i& roi_size, const cv::Vec2i& roi_offset) {

        float kDifferenceM = 0.;
        float kDifferenceC = 0.;
        float kRegionThreshold = 0.;
        float kMaxRegionThreshold = 0.;
        uint kFramePeriod = 0;
        uint kHSkip = 0;
        uint kVSkip = 0;

        GolfSimConfiguration::SetConstant("gs_config.motion_detect_stage.kDifferenceM", kDifferenceM);
        GolfSimConfiguration::SetConstant("gs_config.motion_detect_stage.kDifferenceC", kDifferenceC);
        GolfSimConfiguration::SetConstant("gs_config.motion_detect_stage.kRegionThreshold", kRegionThreshold);
        GolfSimConfiguration::SetConstant("gs_config.motion_detect_stage.kMaxRegionThreshold", kMaxRegionThreshold);
        GolfSimConfiguration::SetConstant("gs_config.motion_detect_stage.kFramePeriod", kFramePeriod);
        GolfSimConfiguration::SetConstant("gs_config.motion_detect_stage.kHSkip", kHSkip);
        GolfSimConfiguration::SetConstant("gs_config.motion_detect_stage.kVSkip", kVSkip);

        GolfSimConfiguration::SetConstant("gs_config.motion_detect_stage.kCroppedImagePixelOffsetLeft", LibCameraInterface::kCroppedImagePixelOffsetLeft);
        GolfSimConfiguration::SetConstant("gs_config.motion_detect_stage.kCroppedImagePixelOffsetUp", LibCameraInterface::kCroppedImagePixelOffsetUp);

        MotionDetectStage::incoming_configuration.use_incoming_configuration = true;

        MotionDetectStage::incoming_configuration.roi_x      = roi_offset[0];
        MotionDetectStage::incoming_configuration.roi_y      = roi_offset[1];
        MotionDetectStage::incoming_configuration.roi_width  = roi_size[0];
        MotionDetectStage::incoming_configuration.roi_height = roi_size[1];

        MotionDetectStage::incoming_configuration.difference_m        = kDifferenceM;
        MotionDetectStage::incoming_configuration.difference_c        = kDifferenceC;
        MotionDetectStage::incoming_configuration.region_threshold    = kRegionThreshold;
        MotionDetectStage::incoming_configuration.max_region_threshold = kMaxRegionThreshold;
        MotionDetectStage::incoming_configuration.frame_period        = kFramePeriod;
        MotionDetectStage::incoming_configuration.hskip               = kHSkip;
        MotionDetectStage::incoming_configuration.vskip               = kVSkip;
        MotionDetectStage::incoming_configuration.verbose             = 2;
        MotionDetectStage::incoming_configuration.showroi             = true;

        return true;
    }


    // -----------------------------------------------------------------------
    // ConfigureLibCameraOptions
    // On RPi this set VideoOptions (framerate, gain, shutter) on the
    // RPiCamEncoder before starting a high-FPS cropped video loop.
    // On Jetson these settings are applied via cv::VideoCapture::set()
    // when the capture device is opened in ball_watcher_event_loop.
    // -----------------------------------------------------------------------
    bool ConfigureLibCameraOptions(const GolfSimCamera& camera, JetsonCaptureApp& app,
                                   const cv::Vec2i& cropping_window_size,
                                   uint cropped_frame_rate_fps) {
        // JETSON_STUB: camera options applied via VideoCapture::set() on open
        return true;
    }


    // -----------------------------------------------------------------------
    // SetLibcameraTuningFileEnvVariable
    // On RPi this set LIBCAMERA_RPI_TUNING_FILE to select a mono sensor
    // tuning file.  That env var has no meaning on Jetson / V4L2.
    // -----------------------------------------------------------------------
    bool SetLibcameraTuningFileEnvVariable(const GolfSimCamera& camera) {
        // JETSON_STUB: LIBCAMERA_RPI_TUNING_FILE env var irrelevant on Jetson
        return true;
    }


    // -----------------------------------------------------------------------
    // WatchForHitAndTrigger
    // On RPi this ran the cropped-video + IPC trigger flow that notified
    // camera 2 to fire.  Stubbed until the two-camera IPC flow is validated
    // end-to-end on Jetson hardware.
    // -----------------------------------------------------------------------
    bool WatchForHitAndTrigger(const GolfBall& /*ball*/, cv::Mat& /*return_image*/,
                               bool& motion_detected) {
        // Jetson: motion-only.  PulseStrobe::SendExternalTrigger() inside
        // the motion-detect path is currently a stub (Group 2 strobe-SPI
        // work is separate from this engine).  Returning the motion
        // result is enough for the upstream FSM to advance.
        GS_LOG_TRACE_MSG(trace, "WatchForHitAndTrigger - entry");
        motion_detected = false;

        JetsonCaptureApp* app = LibCameraInterface::libcamera_app_[0];
        if (!app) {
            GS_LOG_MSG(error, "WatchForHitAndTrigger - camera 1 slot not initialised; "
                              "call PerformCameraSystemStartup first");
            return false;
        }

        // Populate MotionDetectStage::incoming_configuration from gs_config so the
        // stage's Read() picks it up instead of falling through to the hard-coded
        // 1x1-ROI / region_threshold=0 defaults that trip on the first comparison
        // frame.  Full-frame ROI is the v1 default (no cropping yet — Jetson
        // SendCameraCroppingCommand is still TODO in PORTING_TASKS Group 2).
        const cv::Vec2i roi_size  (app->width, app->height);
        const cv::Vec2i roi_offset(0, 0);
        if (!ConfigurePostProcessing(roi_size, roi_offset)) {
            GS_LOG_MSG(error, "WatchForHitAndTrigger - ConfigurePostProcessing failed");
            return false;
        }

        GS_LOG_TRACE_MSG(trace, "WatchForHitAndTrigger - calling ball_watcher_event_loop "
                                "(app=" + app->device_path
                                + ", w=" + std::to_string(app->width)
                                + ", h=" + std::to_string(app->height) + ")");
        const bool result = ball_watcher_event_loop(*app, motion_detected);
        GS_LOG_TRACE_MSG(trace, "WatchForHitAndTrigger - returned "
                                + std::string(result ? "true" : "false")
                                + " motion_detected="
                                + std::string(motion_detected ? "true" : "false"));
        return result;
    }

    // -----------------------------------------------------------------------
    // PulseStrobe symbols moved to pulse_strobe_jetson.cpp (2026-05-02)
    // — real libgpiod fire pin + USB serial setup to a Teensy 4.0 strobe
    //   controller.  pulse_strobe.cpp (RPi SPI bit-bang) stays guarded out.
    // -----------------------------------------------------------------------


    // -----------------------------------------------------------------------
    // Free-function stubs
    // Defined in libcamera_interface.cpp on RPi; stubbed here for Jetson
    // until Group 2 camera work is complete.
    // -----------------------------------------------------------------------

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
            // Apply per-camera config.  Order matters: format/FPS before
            // EXPOSURE/GAIN so that pending controls land on the
            // streaming device.
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

        // Match RPi TakeRawPicture (libcamera_interface.cpp:1295) — downstream
        // ball-detect / stereo geometry expects rectified frames.  No-op when
        // the camera has no calibration matrix loaded.
        img = LibCameraInterface::undistort_camera_image(img, camera);

        return true;
    }

    // Body adapted from CheckForBallLegacy in libcamera_interface.cpp:1366.
    // The RPi-side libcamera_interface.cpp is fully #ifndef JETSON_BUILD-
    // guarded, so this is duplicated rather than reused.  Only hardware-
    // independent code is touched: GolfSimCamera, BallImageProc.
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

    bool WaitForCam2Trigger(cv::Mat& /*return_image*/) {
        // JETSON_STUB
        return false;
    }

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
        // Bind by USB port path, never by /dev/videoN.
        //
        // Both B0332 modules report iSerial "UC762" — Arducam's SKU code, not
        // a per-unit serial — along with identical VID:PID 0c45:6366 and
        // bcdDevice.  /dev/v4l/by-id/ therefore holds a single colliding
        // entry, and the device numbers are handed out in enumeration order.
        // If the two swap across a reboot, the stereo baseline changes sign
        // and depth comes out mirrored, with nothing visibly wrong in either
        // image.
        //
        // This is not hypothetical.  The comment that stood here recorded the
        // cameras on xhci-2.2.4 and xhci-2.3; by 2026-08-06 the hardware
        // enumerated them on 2.3 and 2.4.  The ports had already drifted.
        //
        // The port is the identity, so the socket a cable sits in must not
        // change.  These two strings are mirrored in
        // sp1_vision/camera_paths.py (CAMERA_PORT_PATHS) — grep for them
        // there before changing either, because nothing enforces that the two
        // agree.
        //
        // Which module is which, confirmed 2026-08-06 by covering a lens and
        // independently by parallax:
        //   slot 0 / camera 1  = port 2.3 = LEFT  module facing the unit
        //   slot 1 / camera 2  = port 2.4 = RIGHT module facing the unit
        // Facing the unit you look back down the optical axes, so your left
        // and right are mirrored from the cameras' own.  Camera 1 is on your
        // left and on the cameras' right; both describe the same module.  Get
        // this backwards and the stereo baseline changes sign.
        //
        // /dev/video1 and /dev/video3 are UVC metadata devices and are skipped;
        // the -video-index0 suffix selects the capture node.
        static const char* kSlot0Path =
            "/dev/v4l/by-path/platform-3610000.xhci-usb-0:2.3:1.0-video-index0";
        static const char* kSlot1Path =
            "/dev/v4l/by-path/platform-3610000.xhci-usb-0:2.4:1.0-video-index0";

        if (!probe_v4l2_capture_device(kSlot0Path)) return false;
        if (!probe_v4l2_capture_device(kSlot1Path)) return false;

        // Tell PiTrac's CameraHardware layer to expect OV9281's native
        // 1280x800 instead of the PiGS-default 1456x1088.  Without this,
        // the consumer-side resolution check at camera_hardware.cpp:205
        // rejects every frame our V4L2 engine returns.  This same override
        // mechanism is used elsewhere (gs_automated_testing.cpp:425,
        // lm_main.cpp:654) for non-default resolutions.
        CameraHardware::resolution_x_override_ = 1280;
        CameraHardware::resolution_y_override_ = 800;

        // OV9281: 1/4", 1280x800, 3.0 um square pixels -> 3.840 x 2.400 mm.
        // Confirmed by calibration on 2026-08-06: fy/fx came out at 0.995 on
        // both cameras, which only holds if the pixels really are square at
        // the assumed pitch. Without this the sensor stays at the IMX296's
        // 5.077 x 3.789 mm and the vertical world-coordinate maths is skewed.
        CameraHardware::sensor_width_override_mm_ = 3.840f;
        CameraHardware::sensor_height_override_mm_ = 2.400f;

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
                                + std::string(kSlot0Path) + " and " + std::string(kSlot1Path)
                                + "; CameraHardware resolution override = 1280x800");
        return true;
    }

}  // namespace golf_sim

#endif // __unix__

#endif // JETSON_BUILD
