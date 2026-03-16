/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Copyright (C) 2022-2025, Verdant Consultants, LLC.
 */

// Interface to the ball-motion-detection module.
// The module is structured as a rpicam-apps-style post-processing stage,
// so there's a lot of uncessary code compared to what we would have if
// this was all completely designed from scatch.


#pragma once

#ifndef JETSON_BUILD  // JETSON_STUB

#include "core/rpicam_app.hpp"

#include "post_processing_stages/post_processing_stage.hpp"

#else  // JETSON_BUILD

#include <memory>
#include <boost/property_tree/ptree.hpp>
#include "v4l2_interface.h"

// Minimal base class replacing PostProcessingStage (which inherits RPiCamApp).
// Provides frame dimensions to Configure() and Process() in place of app_->GetStreamInfo().
// RPiCamApp* app_ is gone; frame_width_ and frame_height_ take its place.
class PostProcessingStage {
public:
	PostProcessingStage(int width, int height)
		: frame_width_(width), frame_height_(height) {}
	virtual ~PostProcessingStage() = default;
	virtual char const* Name() const = 0;
	virtual void Read(boost::property_tree::ptree const& params) = 0;
	virtual void Configure() = 0;
	virtual bool Process(JetsonCompletedRequestPtr& completed_request) = 0;
protected:
	int frame_width_;
	int frame_height_;
};

#endif  // JETSON_BUILD


#ifndef JETSON_BUILD  // JETSON_STUB
using Stream = libcamera::Stream;
#endif  // JETSON_BUILD

class MotionDetectStage : public PostProcessingStage
{
public:
#ifndef JETSON_BUILD  // JETSON_STUB
	MotionDetectStage(RPiCamApp* app) : PostProcessingStage(app) {}
#else
	MotionDetectStage(int width, int height) : PostProcessingStage(width, height) {}
#endif  // JETSON_BUILD

	char const* Name() const override;

	void Read(boost::property_tree::ptree const& params) override;

	void Configure() override;

#ifndef JETSON_BUILD  // JETSON_STUB
	bool Process(CompletedRequestPtr& completed_request) override;
#else
	bool Process(JetsonCompletedRequestPtr& completed_request) override;
#endif  // JETSON_BUILD


	// In the Config, dimensions are given as fractions of the image size.
	struct Config
	{
		bool use_incoming_configuration = false;
		float roi_x, roi_y;
		float roi_width, roi_height;
		int hskip, vskip;
		float difference_m;
		int difference_c;
		float region_threshold;
		float max_region_threshold;
		int frame_period;
		bool verbose;
		bool showroi;
	};

	// This is the current configuration of the MotionDetectStage
	Config config_;

	// This structure can be set externally before the video-processing
	// starts so that the motion detector does not have to get its configuration
	// from the motion_detect.json file that the rpicam-apps framework would
	// otherwise use.  It must be called before the video-processing loop
	// begins.
	static Config incoming_configuration;

private:
#ifndef JETSON_BUILD  // JETSON_STUB
	Stream* stream_;
#endif  // JETSON_BUILD
	// Here we convert the dimensions to pixel locations in the image, as if subsampled
	// by hskip and vskip.
	uint roi_x_, roi_y_;
	uint roi_width_, roi_height_;
	uint region_threshold_;
	uint max_region_threshold_;
	std::vector<uint8_t> previous_frame_;
	bool first_time_;
	bool motion_detected_;
	uint postMotionFramesToCapture_;
	std::mutex mutex_;

	// If true, the Processing will no longer spend time looking for differences between
	// frames.  This accommodates post-club-strike image processing.
	bool detectionPaused_;

	// If true, the processing will save the first image received to the 
	// base_image_logging_dir_ set from the command line.  After logging the
	// image, the flag will be set back to false.
	// Will be set to true in the Configure method depending on the artifact 
	// logging level
	bool need_to_log_first_image_ = false;
};
