/**
 * shot_sender.h — Send shot data to the Python receiver service via Unix socket.
 * Project: Jetson LM (SP4)
 *
 * Drop this file into the PiTrac source tree and call SendShot() after each
 * shot is computed. The Python shot_receiver.py service must be running.
 *
 * Usage in pitrac_lm C++ code:
 *
 *   #include "shot_sender.h"
 *
 *   // After computing ball data:
 *   JetsonLM::ShotSender sender;
 *   if (sender.Connect()) {
 *       JetsonLM::BallData ball;
 *       ball.speed = 132.0;
 *       ball.spin_axis = -3.5;
 *       ball.total_spin = 3200.0;
 *       ball.back_spin = 3100.0;
 *       ball.side_spin = -350.0;
 *       ball.hla = -1.2;
 *       ball.vla = 18.5;
 *
 *       std::string response;
 *       bool ok = sender.SendShot("7I", ball, response);
 *       // response contains: {"status":"ok","shot_id":42,"gspro_code":200}
 *   }
 *
 * Protocol: JSON over Unix domain socket, newline-delimited.
 * Socket path: /tmp/jetson_lm.sock (must match shot_receiver.py)
 *
 * Dependencies: standard C++ headers only (sys/socket.h, sys/un.h)
 */

#ifndef JETSON_LM_SHOT_SENDER_H
#define JETSON_LM_SHOT_SENDER_H

#include <string>
#include <sstream>
#include <cstring>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>

namespace JetsonLM {

static const char* DEFAULT_SOCKET_PATH = "/tmp/jetson_lm.sock";
static const int RECV_BUFFER_SIZE = 4096;

struct BallData {
    double speed = 0.0;         // mph
    double spin_axis = 0.0;     // degrees (negative = draw)
    double total_spin = 0.0;    // RPM
    double back_spin = 0.0;     // RPM
    double side_spin = 0.0;     // RPM (negative = draw)
    double hla = 0.0;           // horizontal launch angle (degrees)
    double vla = 0.0;           // vertical launch angle (degrees)
    double carry_distance = 0.0; // yards (optional, 0 = not computed)

    std::string ToJson() const {
        std::ostringstream ss;
        ss << "{"
           << "\"Speed\":" << speed << ","
           << "\"SpinAxis\":" << spin_axis << ","
           << "\"TotalSpin\":" << total_spin << ","
           << "\"BackSpin\":" << back_spin << ","
           << "\"SideSpin\":" << side_spin << ","
           << "\"HLA\":" << hla << ","
           << "\"VLA\":" << vla;
        if (carry_distance > 0.0) {
            ss << ",\"CarryDistance\":" << carry_distance;
        }
        ss << "}";
        return ss.str();
    }
};

struct ClubData {
    double speed = 0.0;
    double angle_of_attack = 0.0;
    double face_to_target = 0.0;
    double lie = 0.0;
    double loft = 0.0;
    double path = 0.0;
    double speed_at_impact = 0.0;
    double vertical_face_impact = 0.0;
    double horizontal_face_impact = 0.0;
    double closure_rate = 0.0;

    bool HasData() const {
        return speed > 0.0 || angle_of_attack != 0.0 || face_to_target != 0.0;
    }

    std::string ToJson() const {
        std::ostringstream ss;
        ss << "{"
           << "\"Speed\":" << speed << ","
           << "\"AngleOfAttack\":" << angle_of_attack << ","
           << "\"FaceToTarget\":" << face_to_target << ","
           << "\"Lie\":" << lie << ","
           << "\"Loft\":" << loft << ","
           << "\"Path\":" << path << ","
           << "\"SpeedAtImpact\":" << speed_at_impact << ","
           << "\"VerticalFaceImpact\":" << vertical_face_impact << ","
           << "\"HorizontalFaceImpact\":" << horizontal_face_impact << ","
           << "\"ClosureRate\":" << closure_rate
           << "}";
        return ss.str();
    }
};

class ShotSender {
public:
    ShotSender(const std::string& socket_path = DEFAULT_SOCKET_PATH)
        : socket_path_(socket_path), fd_(-1) {}

    ~ShotSender() {
        Disconnect();
    }

    /**
     * Connect to the Python shot_receiver service.
     * Returns true on success. Safe to call multiple times.
     */
    bool Connect() {
        if (fd_ >= 0) return true;  // already connected

        fd_ = socket(AF_UNIX, SOCK_STREAM, 0);
        if (fd_ < 0) {
            last_error_ = "Failed to create socket";
            return false;
        }

        struct sockaddr_un addr;
        memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, socket_path_.c_str(), sizeof(addr.sun_path) - 1);

        if (connect(fd_, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            last_error_ = "Cannot connect to " + socket_path_ + " — is shot_receiver.py running?";
            close(fd_);
            fd_ = -1;
            return false;
        }

        return true;
    }

    /**
     * Send a shot to the Python receiver.
     * @param club  Club code (e.g. "DR", "7I", "PW")
     * @param ball  Ball data from the vision pipeline
     * @param response  Receives the JSON response string from Python
     * @return true if shot was sent and response received
     */
    bool SendShot(const std::string& club, const BallData& ball,
                  std::string& response) {
        return SendShot(club, ball, ClubData(), response);
    }

    /**
     * Send a shot with both ball and club data.
     */
    bool SendShot(const std::string& club, const BallData& ball,
                  const ClubData& club_data, std::string& response) {
        if (fd_ < 0) {
            if (!Connect()) return false;
        }

        // Build JSON message
        std::ostringstream msg;
        msg << "{\"club\":\"" << club << "\","
            << "\"ball\":" << ball.ToJson();
        if (club_data.HasData()) {
            msg << ",\"club_data\":" << club_data.ToJson();
        }
        msg << "}\n";

        std::string payload = msg.str();

        // Send
        ssize_t sent = write(fd_, payload.c_str(), payload.size());
        if (sent < 0) {
            last_error_ = "Write failed — connection lost";
            Disconnect();
            return false;
        }

        // Receive response
        char buf[RECV_BUFFER_SIZE];
        ssize_t received = read(fd_, buf, sizeof(buf) - 1);
        if (received <= 0) {
            last_error_ = "No response from receiver";
            Disconnect();
            return false;
        }
        buf[received] = '\0';
        response = std::string(buf);

        // Trim trailing newline
        while (!response.empty() && (response.back() == '\n' || response.back() == '\r')) {
            response.pop_back();
        }

        return true;
    }

    void Disconnect() {
        if (fd_ >= 0) {
            close(fd_);
            fd_ = -1;
        }
    }

    bool IsConnected() const { return fd_ >= 0; }
    const std::string& LastError() const { return last_error_; }

private:
    std::string socket_path_;
    int fd_;
    std::string last_error_;
};

}  // namespace JetsonLM

#endif  // JETSON_LM_SHOT_SENDER_H
