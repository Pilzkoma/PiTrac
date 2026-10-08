/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Copyright (C) 2022-2025, Verdant Consultants, LLC.
 */

#pragma once

#include <boost/asio.hpp>
#include <boost/thread/mutex.hpp>
#include <boost/thread/recursive_mutex.hpp>
#include <atomic>
#include <thread>


#include "logging_tools.h"
#include "golf_ball.h"
#include "gs_results.h"


// Base class for interfaces to 3rd-party golf simulators

namespace golf_sim {

    class GsSimInterface {

    public:
        enum GolfSimulatorType {
            kNone = 0,
            kGSPro = 1,
            kE6 = 2
        };

        GsSimInterface();
        virtual ~GsSimInterface();

        // Create and initialize and sim interfaces that are configured
        static bool InitializeSims();

        // De-initialize and destory and sim interfaces that are configured
        static void DeInitializeSims();

        // Returns true if at least one golf sim is connected to the system.
        static bool SimIsConnected();

        // To be called from the launch monitor
        static bool SendResultsToGolfSims(const GsResults& results);

        // If the interface is present (usually indicated in the config.json file),
        // this method returns true;
        static bool InterfaceIsPresent();

        // Allows the shot counter to be incremented from outside the simulator
        // interface for such purposes and ensuring the counter keeps going even
        // when a failure occurs.

        static void IncrementShotCounter();

        // Will be overridden by each derived class

        virtual bool Initialize();

        // De-initialize and destroy and sim interfaces that are configured
        virtual void DeInitialize();

        // True while this interface has a live connection to its simulator (the heartbeat timer reconnects otherwise).
        virtual bool IsConnected();


        // Base class behavior is to simply print out the JSON
        virtual bool SendResults(const GsResults& results);

        // Sends a string without any other side-effects
        // Returns the number of bytes written
        virtual int SendSimMessage(const std::string& message);

        // Deals with whether or not ALL of the connected simulators are armed
        // (ready to take a shot).  Some sims just return true.
        virtual void SetSimSystemArmed(const bool is_armed);
        virtual bool GetSimSystemArmed();

        // These static functions operate at the collection level for all interfaces
        static long GetShotCounter() { return shot_counter_; };

        // Find the GSPro or E6 or whatever interface (if available) by type
        static GsSimInterface *GetSimInterfaceByType(GolfSimulatorType sim_type);

        // Returns true only if each of the available interfaces is armed
        static bool GetAllSystemsArmed();

        // Heartbeat support for external simulators
        static void SendHeartbeat(bool ball_detected);
        static inline void ResetHeartbeatState() {}

        // Repeats the last heartbeat every kHeartbeatIntervalMs while a simulator interface is initialized, so the
        // simulator can tell "connected and waiting" from "gone" (Golfinator greys its status after 5 s of silence).
        static void StartHeartbeatTimer();
        static void StopHeartbeatTimer();
        static constexpr int kHeartbeatIntervalMs = 2000;

    protected:

        // Typical derived-class behavior will be to convert the results into a
        // sim-specific data packet, such as a JSON string
        virtual std::string GenerateResultsDataToSend(const GsResults& results);

        // Called when the LM receives data
        virtual bool ProcessReceivedData(const std::string received_data);

    protected:

        // Holds pointers to derived interfaces for each attached sim
        static std::vector<GsSimInterface*> interfaces_;

        static std::string launch_monitor_id_string_;
        
        // True if all the attached sims have been initialized
        static bool sims_initialized_;

        static long shot_counter_;

        // Sends the heartbeat message with the given state to every connected interface, without storing the state.
        static void SendHeartbeatState(bool ball_detected);

        // Set while the heartbeat timer (or the first connect in InitializeSims) runs a connect attempt: the attempt
        // itself stays quiet and the caller logs the outcome once, with the cause in last_connect_error_.
        bool quiet_connect_failures_ = false;
        std::string last_connect_error_;
        // True from the first failed connect of an outage until a connect succeeds again (then the next outage logs
        // its first failure again).
        bool reconnect_failed_before_ = false;

        // Last state sent in a heartbeat; the timer repeats it.
        static std::atomic<bool> last_heartbeat_ball_detected_;
        static std::atomic<bool> heartbeat_timer_running_;
        static std::thread heartbeat_thread_;

        // Shots and heartbeats come from two threads: one sender at a time. The heartbeat timer is the only one that
        // connects: it tears a lost connection down under this mutex, connects WITHOUT holding it (a connect may take
        // seconds) and publishes the finished connection by setting initialized_ last. Senders only use the socket
        // when initialized_ is set (checked under this mutex), and a teardown cannot run while a sender holds it.
        // Recursive because a connect sends a heartbeat itself.
        static boost::recursive_mutex send_mutex_;

        // True if THIS sim is connected and its socket is completely set up (published last by Initialize).
        std::atomic<bool> initialized_{ false };

        GolfSimulatorType simulator_type_;

        // Must be true before the simulator system is ready to accept shot data
        // Only relevant for derived, non-virtual classes for whom arming is an
        // actual thing.
        bool sim_system_is_armed_ = false;

        boost::mutex sim_arming_mutex_;
    };

}
