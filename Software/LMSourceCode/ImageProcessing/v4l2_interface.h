/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Copyright (C) 2022-2025, Verdant Consultants, LLC.
 */

// Jetson replacement for libcamera_interface.h.
// Included instead of libcamera_interface.h when JETSON_BUILD is defined.
// All public function signatures match libcamera_interface.h exactly, except
// where RPiCamEncoder& or LibcameraJpegApp* appear — those are replaced with
// JetsonCaptureApp& / JetsonCaptureApp* throughout.

#pragma once

#ifdef JETSON_BUILD  // JETSON_STUB

#ifdef __unix__  // Ignore in Windows environment

#include <string>

#include <opencv2/core.hpp>
#include <opencv2/videoio.hpp>

#include <linux/videodev2.h>

#include "golf_ball.h"
#include "gs_camera.h"
#include "gs_options.h"


// ---------------------------------------------------------------------------
// JetsonCaptureApp — replaces LibcameraJpegApp (which subclassed RPiCamApp).
// Holds one V4L2/OpenCV capture device plus all per-camera configuration
// parameters that ConfigureForLibcameraStill() would previously have written
// into a StillOptions bag.  Actual open/configure/read/release logic lives in
// v4l2_interface.cpp.
// ---------------------------------------------------------------------------

struct JetsonCaptureApp {
    cv::VideoCapture cap;          // the V4L2 capture device
    std::string      device_path;  // e.g. "/dev/video0" for this camera slot
    int              camera_slot  = 0;       // 0 = camera1, 1 = camera2
    double           gain         = 1.0;     // maps to CAP_PROP_GAIN
    double           contrast     = 1.0;     // maps to CAP_PROP_CONTRAST
    double           saturation   = 1.0;     // maps to CAP_PROP_SATURATION
    long             shutter_time_us = 10000; // maps to CAP_PROP_EXPOSURE
    bool             flip_vertical   = false; // true when camera is mounted upside-down
    int              width  = 0;             // sensor width  (pixels)
    int              height = 0;             // sensor height (pixels)
};


namespace golf_sim {

	// TBD - Put in a struct or class sometime

	class LibCameraInterface {
	public:

		// The Camera 1 operates in a cropped mode only when watching the teed-up ball for a
		// hit.  Otherwise, while watching for the ball to be teed up in the first place, the
		// camera operates at full resolution.
		enum CropConfiguration {
			kCropUnknown,
			kFullScreen,
			kCropped
		};

		enum CameraConfiguration {
			kNotConfigured,
			kStillPicture,
			kHighSpeedWatching,
			kExternallyStrobed
		};

		static cv::Mat undistort_camera_image(const cv::Mat& img, const GolfSimCamera& camera);
		static bool SendCamera2PreImage(const cv::Mat& raw_image);

		static uint kMaxWatchingCropWidth;
		static uint kMaxWatchingCropHeight;
		static double kCamera1Gain;  // 0.0 to TBD??
		static double kCamera1Saturation;
		static double kCamera1HighFPSGain;  // 15.0 to TBD??
		static double kCamera1Contrast; // 0.0 to 32.0
		static double kCamera2Gain;  // 0.0 to TBD??
		static double kCamera2Saturation;
		static double kCamera2ComparisonGain;  // 0.0 to TBD??
		static double kCamera2CalibrateOrLocationGain;
		static double kCamera2StrobedEnvironmentGain;
		static double kCamera2Contrast; // 0.0 to 32.0
		static double kCamera2PuttingGain;  // 0.0 to TBD??
		static double kCamera2PuttingContrast; // 0.0 to 32.0
		static std::string kCameraMotionDetectSettings;

		static long kCamera1StillShutterTimeuS;
		static long kCamera2StillShutterTimeuS;

		// Once the cropped rectangle is determined (usually around the center of the ball)
		// these offsets can further move that cropping area
		static int kCroppedImagePixelOffsetLeft;
		static int kCroppedImagePixelOffsetUp;

		static CropConfiguration camera_crop_configuration_;
		static cv::Vec2i current_watch_resolution_;
		static cv::Vec2i current_watch_offset_;

		// The first (0th) element in the array is for camera1, the second for camera2.
		// JetsonCaptureApp replaces LibcameraJpegApp from the RPi build.
		static CameraConfiguration libcamera_configuration_[];
		static JetsonCaptureApp* libcamera_app_[];

		// True (or set to a non-negative number) if we've already figured out the media and device number for the camera
		static bool camera_location_found_;
		static int previously_found_media_number_;
		static int previously_found_device_number_;
	};

	bool TakeRawPicture(const GolfSimCamera& camera, cv::Mat& img);

	// Takes a picture and then tries to find the ball
	bool CheckForBall(GolfBall& ball, cv::Mat& return_image);

	// Configures the camera and the rest of the system to sit in a tight loop, waiting for the
	// ball to move.  Blocks until movement or some other event that causes the loop to stop.
	// Returns whether or not motion was detected.
	// Lower-level methods in the loop will try to trigger the external shutter of camera 2
	// as soon as possible after motion has been detected.
	bool WatchForBallMovement(GolfSimCamera& camera, const GolfBall& ball, bool& motion_detected);

	// Do everything necessary to get the system ready to use a tightly-cropped camera video
	// mode (in order to allow high FPS).
	// RPiCamEncoder& replaced with JetsonCaptureApp&.
	bool ConfigCameraForCropping(GolfBall ball, GolfSimCamera& camera, JetsonCaptureApp& app);

	// Uses v4l2-ctl (or ioctl) to set up a cropping mode to allow high FPS.  Requires GS camera.
	bool SendCameraCroppingCommand(const GolfSimCamera& camera, cv::Vec2i& cropping_window_size, cv::Vec2i& cropping_window_offset);

	// Sets up the post-processing pipeline so that the motion-detection stage knows
	// how to analyse the cropped image.
	bool ConfigurePostProcessing(const cv::Vec2i& roi_size, const cv::Vec2i& roi_offset);

	// Sets up V4L2/OpenCV capture options necessary for a high-FPS video loop in a cropped
	// part of the camera sensor.
	// RPiCamEncoder& replaced with JetsonCaptureApp&.
	bool ConfigureLibCameraOptions(const GolfSimCamera& camera, JetsonCaptureApp& app, const cv::Vec2i& cropping_window_size, uint cropped_frame_rate_fps);

	std::string GetCmdLineForMediaCtlCropping(const GolfSimCamera& camera, cv::Vec2i croppedHW, cv::Vec2i cropOffsetXY);

	// Determine where the camera is (e.g. /dev/video0)
	bool DiscoverCameraLocation(const GsCameraNumber camera_number, int& media_number, int& device_number);

	bool RetrieveCameraInfo(const GsCameraNumber camera_number, cv::Vec2i& resolution, uint& frameRate, bool restartCamera = false);

	// Return type is JetsonCaptureApp* instead of LibcameraJpegApp*
	JetsonCaptureApp* ConfigureForLibcameraStill(const GolfSimCamera& camera);
	bool DeConfigureForLibcameraStill(const GsCameraNumber camera_number);

	bool TakeLibcameraStill(const GolfSimCamera& camera, cv::Mat& return_image);

	bool WatchForHitAndTrigger(const GolfBall& ball, cv::Mat& return_image, bool& motion_detected);

	bool WaitForCam2Trigger(cv::Mat& return_image);

	bool PerformCameraSystemStartup();

	static void SetLibCameraLoggingOff();

}

#endif // __unix__

#endif // JETSON_BUILD
