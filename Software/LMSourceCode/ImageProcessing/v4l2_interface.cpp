
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

#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <linux/videodev2.h>
#include <turbojpeg.h>

#include <cerrno>
#include <cstring>

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
        return false;
    }
    width_  = static_cast<int>(fmt.fmt.pix.width);
    height_ = static_cast<int>(fmt.fmt.pix.height);

    // 2. VIDIOC_S_PARM (frame rate)
    v4l2_streamparm parm{};
    parm.type                                   = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    parm.parm.capture.timeperframe.numerator    = 1;
    parm.parm.capture.timeperframe.denominator  = static_cast<__u32>(fps_);
    if (::ioctl(fd_, VIDIOC_S_PARM, &parm) < 0) {
        GS_LOG_MSG(warning, std::string("V4L2Capture::ensure_streaming - VIDIOC_S_PARM failed: ")
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
        GS_LOG_MSG(error, std::string("V4L2Capture::ensure_streaming - VIDIOC_REQBUFS failed: ")
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
        GS_LOG_MSG(error, std::string("V4L2Capture::ensure_streaming - VIDIOC_STREAMON failed: ")
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
    bool WatchForHitAndTrigger(const GolfBall& ball, cv::Mat& return_image,
                               bool& motion_detected) {
        // JETSON_STUB: two-camera IPC flow not yet validated on Jetson
        motion_detected = false;
        return false;
    }

    // -----------------------------------------------------------------------
    // PulseStrobe stubs
    // pulse_strobe.cpp is entirely guarded by #ifndef JETSON_BUILD; these
    // stubs satisfy the linker until the libgpiod/SPI Group 2 work is done.
    // -----------------------------------------------------------------------

    bool PulseStrobe::InitGPIOSystem(GsSignalCallback) {
        // JETSON_STUB: GPIO init via libgpiod not yet implemented
        return false;
    }

    bool PulseStrobe::DeinitGPIOSystem() {
        // JETSON_STUB
        return false;
    }

    bool PulseStrobe::SendCameraPrimingPulses(bool /*use_high_speed*/) {
        // JETSON_STUB
        return false;
    }

    bool PulseStrobe::SendExternalTrigger() {
        // JETSON_STUB
        return false;
    }

    const std::vector<float> PulseStrobe::GetPulseIntervals() {
        // JETSON_STUB
        return {};
    }


    // -----------------------------------------------------------------------
    // Free-function stubs
    // Defined in libcamera_interface.cpp on RPi; stubbed here for Jetson
    // until Group 2 camera work is complete.
    // -----------------------------------------------------------------------

    bool TakeRawPicture(const GolfSimCamera& /*camera*/, cv::Mat& /*img*/) {
        // JETSON_STUB
        return false;
    }

    bool CheckForBall(GolfBall& /*ball*/, cv::Mat& /*return_image*/) {
        // JETSON_STUB
        return false;
    }

    bool WaitForCam2Trigger(cv::Mat& /*return_image*/) {
        // JETSON_STUB
        return false;
    }

    bool PerformCameraSystemStartup() {
        // JETSON_STUB
        return false;
    }

}  // namespace golf_sim

#endif // __unix__

#endif // JETSON_BUILD
