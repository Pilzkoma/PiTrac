/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Copyright (C) 2022-2025, Verdant Consultants, LLC.
 */

#pragma once

#ifdef __unix__  // Ignore in Windows environment

#ifndef JETSON_BUILD  // JETSON_STUB
#include "core/rpicam_encoder.hpp"
#include "encoder/encoder.hpp"
#else
#include "v4l2_interface.h"
#endif  // JETSON_BUILD

namespace golf_sim {

	// The main event loop 
	// Returns true if function ran as expected, and without error
	// motion_detected will be set true only if motion was successfully detected.
#ifndef JETSON_BUILD  // JETSON_STUB
	bool ball_watcher_event_loop(RPiCamEncoder& app, bool& motion_detected);
#else
	bool ball_watcher_event_loop(JetsonCaptureApp& app, bool& motion_detected);
#endif  // JETSON_BUILD

}

#endif // __unix__
