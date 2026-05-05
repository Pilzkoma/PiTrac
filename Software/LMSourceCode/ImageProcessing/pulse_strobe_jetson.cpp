/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Copyright (C) 2022-2025, Verdant Consultants, LLC.
 *
 * Jetson replacement for pulse_strobe.cpp.  The original file is fully
 * #ifndef JETSON_BUILD-guarded and excluded from the Jetson build; this file
 * provides the 5 PulseStrobe symbols that other Jetson-side code calls
 * (InitGPIOSystem, DeinitGPIOSystem, SendCameraPrimingPulses,
 * SendExternalTrigger, GetPulseIntervals) plus all static member definitions.
 *
 * Architecture: instead of the RPi-side SPI bit-bang strobe generator, the
 * Jetson hands pulse-train timing off to a Teensy 4.0 over USB serial.
 * SendExternalTrigger sends a single 10us GPIO pulse on the configured fire
 * pin; the Teensy's ISR catches the rising edge and runs the pre-loaded
 * pulse train with hardware-timer precision.  See
 * Hardware/teensy_strobe/teensy_strobe.ino for the firmware.
 *
 * Soft fallback: any HW failure (Teensy not at /dev/ttyACM0, libgpiod chip
 * absent, fire pin claim refused) is downgraded to a warning.  Init still
 * returns true and SendExternalTrigger no-ops.  This lets the FSM advance
 * during development when the strobe rig is not yet wired.
 */

#ifdef JETSON_BUILD  // JETSON_STUB: Jetson-only — RPi build uses pulse_strobe.cpp

#ifdef __unix__  // Ignore in Windows environment

#include "pulse_strobe.h"
#include "logging_tools.h"
#include "gs_config.h"
#include "gs_options.h"
#include "gs_camera.h"
#include "gs_clubs.h"

#include <fcntl.h>
#include <unistd.h>
#include <termios.h>

#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <chrono>
#include <thread>
#include <sstream>
#include <vector>


namespace golf_sim {

    // -----------------------------------------------------------------------
    // PulseStrobe static member definitions — mirror pulse_strobe.cpp:33-77
    // exactly so other translation units see the same symbols.  Defaults
    // match the RPi side; runtime values come from golf_sim_config.json.
    // -----------------------------------------------------------------------

    std::vector<float>  PulseStrobe::pulse_intervals_fast_ms_;
    int                 PulseStrobe::number_bits_for_fast_on_pulse_ = 0;

    std::vector<float>  PulseStrobe::pulse_intervals_slow_ms_;
    int                 PulseStrobe::number_bits_for_slow_on_pulse_ = 0;

    std::vector<float>  PulseStrobe::pulse_intervals_tail_repeat_ms_;

    bool PulseStrobe::kUsingActiveHighTriggerCamera = true;

    char* PulseStrobe::camera_slow_pulse_sequence_   = nullptr;
    char* PulseStrobe::camera_fast_pulse_sequence_   = nullptr;
    char* PulseStrobe::no_pulse_camera_sequence_     = nullptr;
    char* PulseStrobe::tail_repeat_pulse_sequence_   = nullptr;

    unsigned long PulseStrobe::camera_fast_pulse_sequence_length_ = 0;
    unsigned long PulseStrobe::camera_slow_pulse_sequence_length_ = 0;
    unsigned long PulseStrobe::tail_repeat_sequence_length_       = 0;

    int  PulseStrobe::spiHandle_              = -1;
    int  PulseStrobe::lggpio_chip_handle_     = -1;
    bool PulseStrobe::spiOpen_                = false;
    bool PulseStrobe::kRecordAllImages        = true;
    bool PulseStrobe::gpio_system_initialized_ = false;
    int  PulseStrobe::kPuttingStrobeDelayMs   = 0;

    long PulseStrobe::kCam2SetupPeriodMilliseconds                 = 2000;
    int  PulseStrobe::kNumberPrimingPulses                         = 12;
    int  PulseStrobe::kPrimingPulseFPS                             = 15;
    long PulseStrobe::kPauseBeforeReadyForTriggerMicroSeconds      = 100;
    int  PulseStrobe::kPauseToSetUpInnoMakerExternalTriggerMilliseconds = 1000;
    int  PulseStrobe::kPauseBeforeReadyForFinalPrimingPulseMs      = 100;
    int  PulseStrobe::kLastPulsePutterRepeats                      = 5;
    unsigned long PulseStrobe::last_pulse_off_time                 = 0;


    // -----------------------------------------------------------------------
    // File-local Teensy + libgpiod state
    // -----------------------------------------------------------------------

    namespace {

    int           teensy_fd     = -1;
    std::string   fire_trigger_script;     // absolute path to fire_trigger.py
    bool          teensy_ready  = false;  // true only after handshake completes

    // Helpers (declarations)
    bool        open_teensy_serial(const std::string& path);
    std::string read_line(int timeout_ms);
    bool        send_line_and_expect_ok(const std::string& cmd, int timeout_ms = 500);
    std::string format_intervals(const std::vector<float>& intervals);
    bool        send_setup_to_teensy(const std::vector<float>& fast_intervals,
                                     const std::vector<float>& slow_intervals,
                                     int on_bits,
                                     long baud_rate);

    bool open_teensy_serial(const std::string& path) {
        teensy_fd = ::open(path.c_str(), O_RDWR | O_NOCTTY);
        if (teensy_fd < 0) {
            GS_LOG_MSG(warning, std::string("open_teensy_serial - ::open(") + path
                                + ") failed: " + std::strerror(errno));
            return false;
        }

        struct termios tty{};
        if (::tcgetattr(teensy_fd, &tty) != 0) {
            GS_LOG_MSG(error, std::string("open_teensy_serial - tcgetattr failed: ")
                              + std::strerror(errno));
            ::close(teensy_fd);
            teensy_fd = -1;
            return false;
        }

        ::cfsetospeed(&tty, B115200);
        ::cfsetispeed(&tty, B115200);
        tty.c_cflag = (tty.c_cflag & ~CSIZE) | CS8;
        tty.c_cflag &= ~PARENB;
        tty.c_cflag &= ~CSTOPB;
        tty.c_cflag &= ~CRTSCTS;
        tty.c_cflag |= CREAD | CLOCAL;
        tty.c_lflag  = 0;   // raw mode (no canonical, no echo)
        tty.c_iflag  = 0;
        tty.c_oflag  = 0;
        tty.c_cc[VMIN]  = 0;
        tty.c_cc[VTIME] = 0;

        if (::tcsetattr(teensy_fd, TCSANOW, &tty) != 0) {
            GS_LOG_MSG(error, std::string("open_teensy_serial - tcsetattr failed: ")
                              + std::strerror(errno));
            ::close(teensy_fd);
            teensy_fd = -1;
            return false;
        }

        // Drain Teensy's BOOT banner left in the kernel buffer.
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
        char drain[256];
        while (::read(teensy_fd, drain, sizeof(drain)) > 0) { /* discard */ }

        GS_LOG_TRACE_MSG(trace, "open_teensy_serial - opened " + path + " at 115200 8N1");
        return true;
    }

    std::string read_line(int timeout_ms) {
        std::string result;
        const auto deadline = std::chrono::steady_clock::now()
                              + std::chrono::milliseconds(timeout_ms);
        while (std::chrono::steady_clock::now() < deadline) {
            char c;
            const ssize_t n = ::read(teensy_fd, &c, 1);
            if (n == 1) {
                if (c == '\r') continue;
                if (c == '\n') return result;
                result += c;
            } else {
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
            }
        }
        return result;  // timeout — return whatever we collected (may be empty)
    }

    bool send_line_and_expect_ok(const std::string& cmd, int timeout_ms) {
        const std::string framed = cmd + "\n";
        const ssize_t written = ::write(teensy_fd, framed.data(), framed.size());
        if (written != (ssize_t)framed.size()) {
            GS_LOG_MSG(error, "send_line_and_expect_ok - write failed for: " + cmd);
            return false;
        }
        const std::string response = read_line(timeout_ms);
        if (response != "OK") {
            GS_LOG_MSG(error, "send_line_and_expect_ok - cmd '" + cmd
                              + "' got response '" + response + "' (expected OK)");
            return false;
        }
        return true;
    }

    std::string format_intervals(const std::vector<float>& intervals) {
        std::ostringstream oss;
        for (size_t i = 0; i < intervals.size(); ++i) {
            if (i > 0) oss << ",";
            oss << intervals[i];
        }
        return oss.str();
    }

    bool send_setup_to_teensy(const std::vector<float>& fast_intervals,
                              const std::vector<float>& slow_intervals,
                              int on_bits,
                              long baud_rate) {
        // Caller (PulseStrobe::InitGPIOSystem) owns access to the class's
        // protected static members and passes them in.  Keeps this helper
        // out of the friend / member dance.
        if (fast_intervals.empty()) {
            GS_LOG_MSG(error, "send_setup_to_teensy - fast_intervals empty");
            return false;
        }
        if (slow_intervals.empty()) {
            GS_LOG_MSG(error, "send_setup_to_teensy - slow_intervals empty");
            return false;
        }
        if (on_bits < 1) {
            GS_LOG_MSG(error, "send_setup_to_teensy - on_bits < 1");
            return false;
        }

        if (!send_line_and_expect_ok("PULSES_FAST," + format_intervals(fast_intervals))) {
            return false;
        }
        if (!send_line_and_expect_ok("PULSES_SLOW," + format_intervals(slow_intervals))) {
            return false;
        }
        if (!send_line_and_expect_ok("ON_BITS," + std::to_string(on_bits))) {
            return false;
        }
        if (!send_line_and_expect_ok("BAUD," + std::to_string(baud_rate))) {
            return false;
        }
        if (!send_line_and_expect_ok("MODE,FAST")) {
            return false;
        }

        // Confirm Teensy reached READY state
        const std::string framed = "READY?\n";
        ::write(teensy_fd, framed.data(), framed.size());
        const std::string response = read_line(500);
        if (response != "READY") {
            GS_LOG_MSG(error, "send_setup_to_teensy - READY? returned '" + response + "'");
            return false;
        }

        GS_LOG_TRACE_MSG(trace, "send_setup_to_teensy - Teensy reached READY state");
        return true;
    }

    }  // anonymous namespace


    // -----------------------------------------------------------------------
    // PulseStrobe::InitGPIOSystem (Jetson)
    // Loads strobing config from JSON, opens Teensy USB serial, claims the
    // fire-trigger GPIO line via libgpiod, and sends the setup handshake.
    // Soft fallback: HW failures log a warning but return true so the FSM
    // can still advance during dev (SendExternalTrigger then no-ops).
    // -----------------------------------------------------------------------
    bool PulseStrobe::InitGPIOSystem(GsSignalCallback /*callback_function*/) {
        GS_LOG_TRACE_MSG(trace, "PulseStrobe::InitGPIOSystem (Jetson)");

        if (gpio_system_initialized_) {
            GS_LOG_MSG(warning, "PulseStrobe::InitGPIOSystem called more than once - ignoring");
            return true;
        }

        // Mirror pulse_strobe.cpp:437-444 — load timing constants.
        GolfSimConfiguration::SetConstant("gs_config.strobing.kCam2SetupPeriodMilliseconds", kCam2SetupPeriodMilliseconds);
        GolfSimConfiguration::SetConstant("gs_config.strobing.kNumberPrimingPulses",        kNumberPrimingPulses);
        GolfSimConfiguration::SetConstant("gs_config.strobing.kPrimingPulseFPS",            kPrimingPulseFPS);
        GolfSimConfiguration::SetConstant("gs_config.strobing.kPauseBeforeReadyForTriggerMicroSeconds", kPauseBeforeReadyForTriggerMicroSeconds);
        GolfSimConfiguration::SetConstant("gs_config.strobing.kPauseToSetUpInnoMakerExternalTriggerMilliseconds", kPauseToSetUpInnoMakerExternalTriggerMilliseconds);
        GolfSimConfiguration::SetConstant("gs_config.strobing.kPauseBeforeReadyForFinalPrimingPulseMs",  kPauseBeforeReadyForFinalPrimingPulseMs);

        gpio_system_initialized_ = true;

        // Mirror pulse_strobe.cpp:448-459 — only camera1-side modes need the
        // full HW init.  Cam2-only / test modes just load constants and exit.
        if (GolfSimOptions::GetCommandLineOptions().system_mode_ != SystemMode::kCamera1 &&
            GolfSimOptions::GetCommandLineOptions().system_mode_ != SystemMode::kCamera1TestStandalone &&
            GolfSimOptions::GetCommandLineOptions().system_mode_ != SystemMode::kTest &&
            !GolfSimOptions::GetCommandLineOptions().camera_still_mode_ &&
            GolfSimOptions::GetCommandLineOptions().system_mode_ != SystemMode::kCamera1AutoCalibrate &&
            GolfSimOptions::GetCommandLineOptions().system_mode_ != SystemMode::kCamera2AutoCalibrate &&
            GolfSimOptions::GetCommandLineOptions().system_mode_ != SystemMode::kCamera1BallLocation &&
            GolfSimOptions::GetCommandLineOptions().system_mode_ != SystemMode::kCamera2BallLocation) {
            GS_LOG_MSG(trace, "PulseStrobe::InitGPIOSystem - non-cam1 mode, returning after constants load");
            return true;
        }

        // Mirror pulse_strobe.cpp:527-544 — load pulse vectors + on-bits + baud.
        GolfSimConfiguration::SetConstant("gs_config.strobing.kStrobePulseVectorDriver",         pulse_intervals_fast_ms_);
        GolfSimConfiguration::SetConstant("gs_config.strobing.kStrobePulseVectorPutter",         pulse_intervals_slow_ms_);
        GolfSimConfiguration::SetConstant("gs_config.strobing.kDynamicFollowOnPulseVectorPutter", pulse_intervals_tail_repeat_ms_);

        if (GolfSimOptions::GetCommandLineOptions().lm_comparison_mode_) {
            GolfSimConfiguration::SetConstant("gs_config.testing.kExternallyStrobedEnvNumber_bits_for_fast_on_pulse_", number_bits_for_fast_on_pulse_);
        } else {
            GolfSimConfiguration::SetConstant("gs_config.strobing.number_bits_for_fast_on_pulse_", number_bits_for_fast_on_pulse_);
        }
        GolfSimConfiguration::SetConstant("gs_config.strobing.number_bits_for_slow_on_pulse_", number_bits_for_slow_on_pulse_);

        long kBaudRateForFastPulses = 38400;
        long kBaudRateForSlowPulses = 38400;
        GolfSimConfiguration::SetConstant("gs_config.strobing.kBaudRateForFastPulses", kBaudRateForFastPulses);
        GolfSimConfiguration::SetConstant("gs_config.strobing.kBaudRateForSlowPulses", kBaudRateForSlowPulses);

        // Jetson-specific config (added 2026-05-02 for the Teensy strobe path).
        // Trigger goes via fire_trigger.py (Jetson.GPIO under the hood) — the
        // libgpiod chardev path was confirmed not to drive Pin 29 reliably
        // on this Seeed J202 carrier (2026-05-05 debugging arc, Issue #22).
        std::string teensy_device   = "/dev/ttyACM0";
        std::string fire_script     = "/home/brain/JetsonLM/Hardware/teensy_strobe/fire_trigger.py";
        GolfSimConfiguration::SetConstant("gs_config.strobing.kJetsonTeensySerialDevice", teensy_device);
        GolfSimConfiguration::SetConstant("gs_config.strobing.kJetsonFireTriggerScript",  fire_script);
        fire_trigger_script = fire_script;

        GS_LOG_TRACE_MSG(trace, "PulseStrobe::InitGPIOSystem - Teensy path config: device="
                                + teensy_device + " trigger_script=" + fire_trigger_script);

        // ---- HW open (soft fallback on every failure) -------------------

        if (!open_teensy_serial(teensy_device)) {
            GS_LOG_MSG(warning, "PulseStrobe::InitGPIOSystem - Teensy not reachable at " + teensy_device
                                + " - SendExternalTrigger will no-op. Continuing for development.");
            return true;
        }

        if (!send_setup_to_teensy(pulse_intervals_fast_ms_,
                                  pulse_intervals_slow_ms_,
                                  number_bits_for_fast_on_pulse_,
                                  kBaudRateForFastPulses)) {
            GS_LOG_MSG(warning, "PulseStrobe::InitGPIOSystem - Teensy handshake failed"
                                " - SendExternalTrigger will no-op");
            return true;
        }

        teensy_ready = true;
        GS_LOG_TRACE_MSG(trace, "PulseStrobe::InitGPIOSystem - Teensy READY."
                                " Strobe pipeline live (trigger via " + fire_trigger_script + ").");
        return true;
    }


    // -----------------------------------------------------------------------
    // PulseStrobe::DeinitGPIOSystem (Jetson)
    // -----------------------------------------------------------------------
    bool PulseStrobe::DeinitGPIOSystem() {
        GS_LOG_TRACE_MSG(trace, "PulseStrobe::DeinitGPIOSystem (Jetson)");

        if (teensy_fd >= 0) {
            ::close(teensy_fd);
            teensy_fd = -1;
        }
        teensy_ready = false;
        gpio_system_initialized_ = false;
        return true;
    }


    // -----------------------------------------------------------------------
    // PulseStrobe::SendCameraPrimingPulses (Jetson)
    // OV9281 USB cameras have no XTR pin, so the priming-pulse sequence
    // (which the RPi side used to wake CSI cam2 over GPIO) has no analog.
    // No-op return true.
    // -----------------------------------------------------------------------
    bool PulseStrobe::SendCameraPrimingPulses(bool /*use_high_speed*/) {
        GS_LOG_TRACE_MSG(trace, "PulseStrobe::SendCameraPrimingPulses (Jetson) - no-op for OV9281 USB");
        return true;
    }


    // -----------------------------------------------------------------------
    // PulseStrobe::SendExternalTrigger (Jetson)
    // Spawns fire_trigger.py via std::system to drive Pin 29 HIGH for ~5ms
    // through Jetson.GPIO.  Direct libgpiod chardev (gpiod_line_set_value)
    // does not produce a rising edge that the Teensy ISR sees on this
    // Seeed J202 carrier (Issue #22).  Latency: ~100-200ms for fork/exec/
    // python startup, dominated by Python interpreter cold-start.  Soft
    // no-op if Teensy not ready.
    // -----------------------------------------------------------------------
    bool PulseStrobe::SendExternalTrigger() {
        if (!teensy_ready) {
            GS_LOG_MSG(warning, "PulseStrobe::SendExternalTrigger - Teensy not ready, skipping fire");
            return true;
        }

        const std::string cmd = "python3 " + fire_trigger_script + " 2>&1";
        const int rc = std::system(cmd.c_str());
        if (rc != 0) {
            GS_LOG_MSG(error, "PulseStrobe::SendExternalTrigger - " + cmd
                              + " returned " + std::to_string(rc));
            return false;
        }
        GS_LOG_TRACE_MSG(trace, "PulseStrobe::SendExternalTrigger - fire pulse sent (via Jetson.GPIO helper)");
        return true;
    }


    // -----------------------------------------------------------------------
    // PulseStrobe::GetPulseIntervals (Jetson)
    // Same logic as pulse_strobe.cpp:745.
    // -----------------------------------------------------------------------
    const std::vector<float> PulseStrobe::GetPulseIntervals() {
        std::vector<float> intervals;
        if (GolfSimClubs::GetCurrentClubType() == GolfSimClubs::GsClubType::kPutter) {
            intervals = pulse_intervals_slow_ms_;
        } else {
            intervals = pulse_intervals_fast_ms_;
        }
        if (intervals.empty()) {
            GS_LOG_TRACE_MSG(error, "GetPulseIntervals: pulse intervals vector empty. Check JSON or InitGPIOSystem call.");
            return intervals;
        }
        if (intervals[intervals.size() - 1] > 0.0001f) {
            GS_LOG_TRACE_MSG(warning, "Expected last pulse interval to be 0. Check .json file.");
        }
        return intervals;
    }

}  // namespace golf_sim

#endif  // __unix__
#endif  // JETSON_BUILD
