/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Copyright (C) 2022-2025, Verdant Consultants, LLC.
 */

#ifdef __unix__  // Ignore in Windows environment

#include <chrono>
#include <signal.h>
#include <sys/stat.h>

#ifndef JETSON_BUILD  // JETSON_STUB
#include "core/rpicam_encoder.hpp"
#include "encoder/encoder.hpp"
#include "output/output.hpp"
#endif  // JETSON_BUILD

#include <opencv2/core/cvdef.h>
#include <opencv2/highgui.hpp>

#include <boost/circular_buffer.hpp>
#include <boost/range/adaptor/reversed.hpp>

#include "motion_detect.h"

#include "logging_tools.h"
#include "gs_globals.h"

namespace gs = golf_sim;

#ifndef JETSON_BUILD  // JETSON_STUB
#include <sys/signalfd.h>
#include <poll.h>
#endif  // JETSON_BUILD

#include "ball_watcher.h"

#ifndef JETSON_BUILD  // JETSON_STUB
using namespace std::placeholders;
#endif  // JETSON_BUILD

namespace golf_sim {


#ifndef JETSON_BUILD  // JETSON_STUB
static int get_colourspace_flags(std::string const &codec)
{
	GS_LOG_TRACE_MSG(trace, "get_colourspace_flags - codec is: " + codec);

	if (codec == "mjpeg" || codec == "yuv420")
		return RPiCamEncoder::FLAG_VIDEO_JPEG_COLOURSPACE;
	else
		return RPiCamEncoder::FLAG_VIDEO_NONE;
}
#endif  // JETSON_BUILD

// The main event loop for the application.

#ifndef JETSON_BUILD  // JETSON_STUB

bool ball_watcher_event_loop(RPiCamEncoder &app, bool & motion_detected)
{

	VideoOptions const *options = app.GetOptions();
	std::unique_ptr<Output> output = std::unique_ptr<Output>(Output::Create(options));
	app.SetEncodeOutputReadyCallback(std::bind(&Output::OutputReady, output.get(), std::placeholders::_1, std::placeholders::_2, std::placeholders::_3, std::placeholders::_4));
	app.SetMetadataReadyCallback(std::bind(&Output::MetadataReady, output.get(), std::placeholders::_1));

	app.OpenCamera();

	app.ConfigureVideo(get_colourspace_flags(options->Get().codec));
	GS_LOG_TRACE_MSG(trace, "ball_watcher_event_loop - starting encoder.");
	app.StartEncoder();
	app.StartCamera();

	// Instead of using the dynamical link4ed-library approach used by lrpiocam apps,
	// we will just manually create a mottion_detect object

	MotionDetectStage motion_detect_stage(&app);

	// Setup the same elements of the stage that rpicam apps would otherwise do dynamically.

	boost::property_tree::ptree empty_params;
	motion_detect_stage.Read(empty_params);
	motion_detect_stage.Configure();


	auto start_time = std::chrono::high_resolution_clock::now();

	pollfd p[1] = { { STDIN_FILENO, POLLIN, 0 } };

	motion_detected = false;

	for (unsigned int count = 0; ; count++)
	{
		if (!gs::GolfSimGlobals::golf_sim_running_) {
			app.StopCamera(); // stop complains if encoder very slow to close
			app.StopEncoder();
			return false;
		}


		RPiCamEncoder::Msg msg = app.Wait();
		if (msg.type == RPiCamApp::MsgType::Timeout)
		{
			GS_LOG_MSG(error, "ERROR: Device timeout detected, attempting a restart!!!");
			app.StopCamera();
			app.StartCamera();
			continue;
		}

		if (msg.type == RPiCamEncoder::MsgType::Quit)
			return motion_detected;
		else if (msg.type != RPiCamEncoder::MsgType::RequestComplete)
			throw std::runtime_error("unrecognised message!");

		// We have a completed request for an image
		CompletedRequestPtr &completed_request = std::get<CompletedRequestPtr>(msg.payload);
        if (!app.EncodeBuffer(completed_request, app.VideoStream()))
        {
                // Keep advancing our "start time" if we're still waiting to start recording (e.g.
                // waiting for synchronisation with another camera).
                start_time = std::chrono::high_resolution_clock::now();
                count = 0; // reset the "frames encoded" counter too
        }

		// Immediately have the motion detection stage determine if there was movement.

		bool result = motion_detect_stage.Process(completed_request);

		bool mdResult = false;
		int getStatus = completed_request->post_process_metadata.Get("motion_detect.result", mdResult);
		if (getStatus == 0) {
			if (mdResult) {
				app.StopCamera(); // stop complains if encoder very slow to close
				app.StopEncoder();
				motion_detected = true;

				// TBD - for now, once we have motion, get out immediately
				return true;
			}
			else {
				// std::cout << "****** motion stopped ********* " << std::endl;
			}
		}
		else {
			// std::cout << "WARNING:  Could not find motion_detect.result." << std::endl;
		}
	}

	return true;
}

#else  // JETSON_BUILD

bool ball_watcher_event_loop(JetsonCaptureApp& app, bool& motion_detected)
{
	// Open the V4L2 capture device for this camera slot.
	if (!app.cap.open(app.device_path, cv::CAP_V4L2)) {
		GS_LOG_MSG(error, "ball_watcher_event_loop - failed to open capture device: " + app.device_path);
		return false;
	}

	if (app.width > 0 && app.height > 0) {
		app.cap.set(cv::CAP_PROP_FRAME_WIDTH,  app.width);
		app.cap.set(cv::CAP_PROP_FRAME_HEIGHT, app.height);
	}

	const float framerate = static_cast<float>(app.cap.get(cv::CAP_PROP_FPS));

	// JETSON_STUB: MotionDetectStage constructor signature will be updated when
	// motion_detect.h is ported — will take (int width, int height) on Jetson
	// rather than RPiCamApp*.
	MotionDetectStage motion_detect_stage(app.width, app.height);  // JETSON_STUB

	boost::property_tree::ptree empty_params;
	motion_detect_stage.Read(empty_params);
	motion_detect_stage.Configure();

	motion_detected = false;

	static const int kMaxConsecutiveReadFailures = 5;
	int consecutive_failures = 0;

	for (uint sequence = 0; ; sequence++)
	{
		if (!gs::GolfSimGlobals::golf_sim_running_) {
			app.cap.release();
			return false;
		}

		cv::Mat frame;
		if (!app.cap.read(frame) || frame.empty()) {
			GS_LOG_MSG(error, "ball_watcher_event_loop - cap.read() failed (consecutive: "
			                  + std::to_string(++consecutive_failures) + ")");
			if (consecutive_failures >= kMaxConsecutiveReadFailures) {
				GS_LOG_MSG(error, "ball_watcher_event_loop - too many consecutive read failures, aborting.");
				break;
			}
			continue;
		}
		consecutive_failures = 0;

		// Build the per-frame context that MotionDetectStage::Process() reads and writes.
		// JetsonCompletedRequest replaces CompletedRequestPtr (libcamera type).
		JetsonCompletedRequestPtr completed_request = std::make_shared<JetsonCompletedRequest>();
		completed_request->frame     = frame;
		completed_request->sequence  = sequence;
		completed_request->framerate = framerate;

		motion_detect_stage.Process(completed_request);

		auto it = completed_request->post_process_metadata.find("motion_detect.result");
		if (it != completed_request->post_process_metadata.end() && it->second) {
			app.cap.release();
			motion_detected = true;
			return true;
		}
	}

	app.cap.release();
	return false;
}

#endif  // JETSON_BUILD

}

#endif // __unix__
