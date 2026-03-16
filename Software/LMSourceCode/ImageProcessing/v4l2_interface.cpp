
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

namespace golf_sim {

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

}  // namespace golf_sim

#endif // __unix__

#endif // JETSON_BUILD
