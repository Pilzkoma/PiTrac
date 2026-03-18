
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
