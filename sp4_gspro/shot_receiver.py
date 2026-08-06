#!/usr/bin/env python3
"""
Shot Receiver Service — Unix Socket → GSPro/OpenShotGolf + SQLite
Project: Jetson LM (SP4)
Purpose: Persistent service that receives shot data from the C++ vision pipeline
         (pitrac_lm) over a local Unix domain socket, forwards it to the golf
         simulator over TCP, and logs everything to SQLite.

Architecture:
    pitrac_lm (C++) → Unix Socket → THIS SERVICE → TCP → OpenShotGolf/GSPro
                                         ↓
                                     SQLite DB
                                         ↓
                                     dashboard.py

Usage:
    python3 shot_receiver.py --ip 192.168.178.20                        # start service
    python3 shot_receiver.py --ip 192.168.178.20 --port 921             # real GSPro
    python3 shot_receiver.py --ip 192.168.178.20 --player "Max"         # named player
    python3 shot_receiver.py --ip 192.168.178.20 --no-forward           # DB only, no TCP

Protocol (Unix Socket):
    C++ sends a JSON object per shot, terminated by a newline (\\n).
    This service responds with a JSON status object, also newline-terminated.

    Shot message from C++:
    {"club": "7I", "ball": {"Speed": 132.0, "SpinAxis": -3.5, ...}, "club_data": {...}}

    Response to C++:
    {"status": "ok", "shot_id": 42, "gspro_code": 200}
    {"status": "error", "message": "..."}

Socket path: /tmp/jetson_lm.sock (configurable with --socket)
"""

import argparse
import json
import os
import signal
import socket
import sys
import time
from typing import Optional

from shot_db import ShotDB
from ball_physics import compute_flight

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_SOCKET_PATH = "/tmp/jetson_lm.sock"
DEFAULT_TARGET_PORT = 49152
DEVICE_ID = "Jetson LM 1.0"
API_VERSION = "1"
TCP_TIMEOUT = 5
TCP_BUFFER = 4096

# ---------------------------------------------------------------------------
# GSPro TCP connection
# ---------------------------------------------------------------------------

class GSProConnection:
    """Manages the TCP connection to GSPro / OpenShotGolf."""

    def __init__(self, ip: str, port: int):
        self.ip = ip
        self.port = port
        self.sock = None

    def connect(self) -> bool:
        """Connect to the simulator. Returns True on success."""
        if self.sock:
            self.close()
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(TCP_TIMEOUT)
            self.sock.connect((self.ip, self.port))
            print(f"[Receiver] Connected to simulator at {self.ip}:{self.port}")
            return True
        except Exception as e:
            print(f"[Receiver] Cannot connect to simulator: {e}")
            self.sock = None
            return False

    def send_shot(self, shot_number: int, ball_data: dict,
                  club_data: Optional[dict] = None) -> Optional[int]:
        """Send a shot to the simulator. Returns response code or None."""
        if not self.sock:
            if not self.connect():
                return None

        payload = {
            "DeviceID": DEVICE_ID,
            "Units": "Yards",
            "ShotNumber": shot_number,
            "APIversion": API_VERSION,
            "BallData": ball_data,
            "ClubData": club_data or {
                "Speed": 0.0, "AngleOfAttack": 0.0, "FaceToTarget": 0.0,
                "Lie": 0.0, "Loft": 0.0, "Path": 0.0, "SpeedAtImpact": 0.0,
                "VerticalFaceImpact": 0.0, "HorizontalFaceImpact": 0.0,
                "ClosureRate": 0.0,
            },
            "ShotDataOptions": {
                "ContainsBallData": True,
                "ContainsClubData": club_data is not None,
                "LaunchMonitorIsReady": True,
                "LaunchMonitorBallDetected": True,
                "IsHeartBeat": False,
            },
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            self.sock.sendall(data)

            response_raw = self.sock.recv(TCP_BUFFER)
            if response_raw:
                response = json.loads(response_raw.decode("utf-8"))
                return response.get("Code")
        except (socket.timeout, ConnectionResetError, BrokenPipeError) as e:
            print(f"[Receiver] Simulator connection lost: {e}")
            self.sock = None
            # Try reconnecting once
            if self.connect():
                try:
                    self.sock.sendall(data)
                    response_raw = self.sock.recv(TCP_BUFFER)
                    if response_raw:
                        response = json.loads(response_raw.decode("utf-8"))
                        return response.get("Code")
                except Exception:
                    pass
        except Exception as e:
            print(f"[Receiver] Send error: {e}")

        return None

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None


# ---------------------------------------------------------------------------
# Unix Socket Server
# ---------------------------------------------------------------------------

# Module-level shutdown flag — set by signal handler, checked by all loops
_shutting_down = False

def handle_client(client_sock, db: ShotDB, session_id: int,
                  gspro: Optional[GSProConnection], shot_counter: list):
    """Handle a single client connection (one pitrac_lm process)."""
    buf = ""
    client_sock.settimeout(1.0)  # 1s timeout so we can check shutdown flag

    print("[Receiver] C++ client connected")

    try:
        while not _shutting_down:
            try:
                data = client_sock.recv(4096)
            except socket.timeout:
                continue  # check _shutting_down flag
            if not data:
                break

            buf += data.decode("utf-8")

            # Process complete messages (newline-delimited)
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                try:
                    msg = json.loads(line)
                except json.JSONDecodeError as e:
                    response = {"status": "error", "message": f"Invalid JSON: {e}"}
                    client_sock.sendall((json.dumps(response) + "\n").encode("utf-8"))
                    continue

                # Process the shot
                shot_counter[0] += 1
                shot_num = shot_counter[0]

                club = msg.get("club")
                ball_data = msg.get("ball", {})
                club_data = msg.get("club_data", {})

                print(
                    f"[Receiver] Shot #{shot_num} — {club or '?'}: "
                    f"{ball_data.get('Speed', '?')} mph, "
                    f"VLA {ball_data.get('VLA', '?')}°"
                )

                # Forward to simulator
                gspro_code = None
                if gspro:
                    gspro_code = gspro.send_shot(shot_num, ball_data, club_data or None)
                    if gspro_code == 200:
                        print(f"[Receiver] Simulator accepted shot #{shot_num}")
                    elif gspro_code:
                        print(f"[Receiver] Simulator responded: {gspro_code}")
                    else:
                        print(f"[Receiver] No simulator response")

                # Calculate carry distance using physics engine
                flight = compute_flight(
                    ball_speed_mph=ball_data.get("Speed", 0),
                    vla_deg=ball_data.get("VLA", 0),
                    hla_deg=ball_data.get("HLA", 0),
                    total_spin_rpm=ball_data.get("TotalSpin", 3000),
                    spin_axis_deg=ball_data.get("SpinAxis", 0),
                )
                ball_data["CarryDistance"] = flight["carry_yards"]

                # Log to database
                shot_id = db.log_shot(
                    session_id=session_id,
                    shot_number=shot_num,
                    club=club,
                    ball_data=ball_data,
                    club_data=club_data,
                    response_code=gspro_code
                )
                print(f"[Receiver] Logged to DB (shot ID {shot_id}, carry {flight['carry_yards']}yd)")

                # Respond to C++ client
                response = {
                    "status": "ok",
                    "shot_id": shot_id,
                    "shot_number": shot_num,
                    "gspro_code": gspro_code,
                }
                client_sock.sendall((json.dumps(response) + "\n").encode("utf-8"))

    except (ConnectionResetError, BrokenPipeError):
        print("[Receiver] C++ client disconnected")
    except Exception as e:
        print(f"[Receiver] Client error: {e}")
    finally:
        client_sock.close()
        print(f"[Receiver] Client session done — {shot_counter[0]} shots processed")


def run_server(socket_path: str, db: ShotDB, session_id: int,
               gspro: Optional[GSProConnection]):
    """Main Unix socket server loop."""

    # Clean up stale socket file
    if os.path.exists(socket_path):
        os.remove(socket_path)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_path)
    server.listen(1)
    server.settimeout(1.0)  # check for shutdown every second

    # Make socket accessible by other users (pitrac_lm might run as different user)
    os.chmod(socket_path, 0o777)

    print(f"[Receiver] Listening on Unix socket: {socket_path}")
    print(f"[Receiver] Waiting for pitrac_lm to connect (Ctrl+C to stop)...")
    print()

    shot_counter = [0]  # mutable counter shared with handler

    try:
        while not _shutting_down:
            try:
                client_sock, _ = server.accept()
                handle_client(client_sock, db, session_id, gspro, shot_counter)
            except socket.timeout:
                continue
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        if os.path.exists(socket_path):
            os.remove(socket_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Shot Receiver — Unix Socket → GSPro/OpenShotGolf + SQLite"
    )
    parser.add_argument(
        "--ip", default=None,
        help="IP of PC running OpenShotGolf or GSPro (omit to log to DB only)"
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_TARGET_PORT,
        help=f"Simulator port (default: {DEFAULT_TARGET_PORT}, use 921 for GSPro)"
    )
    parser.add_argument(
        "--socket", default=DEFAULT_SOCKET_PATH,
        help=f"Unix socket path (default: {DEFAULT_SOCKET_PATH})"
    )
    parser.add_argument(
        "--player", default="Default Player",
        help="Player name for session logging"
    )
    parser.add_argument(
        "--no-forward", action="store_true",
        help="Don't forward to simulator — log to DB only"
    )
    parser.add_argument(
        "--db", default="jetson_lm.db",
        help="Path to SQLite database"
    )
    args = parser.parse_args()

    # Database setup
    db = ShotDB(args.db)

    # Get or create player
    players = db.list_players()
    player = next((p for p in players if p["name"] == args.player), None)
    if player:
        player_id = player["id"]
    else:
        player_id = db.add_player(args.player, "RH")
        print(f"[Receiver] Created player: {args.player} (ID {player_id})")

    # Get or create course
    target_name = "GSPro" if args.port == 921 else "OpenShotGolf"
    if args.no_forward or not args.ip:
        target_name = "Local"
    course_name = f"{target_name} Driving Range"
    course = db.get_course_by_name(course_name)
    if not course:
        course_id = db.add_course(course_name, target_name, "range")
    else:
        course_id = course["id"]

    # Start session
    session_id = db.start_session(
        player_id, course_id, target_name,
        args.ip or "localhost", args.port
    )
    print(f"[Receiver] Session #{session_id} started for {args.player}")

    # Simulator connection
    gspro = None
    if args.ip and not args.no_forward:
        gspro = GSProConnection(args.ip, args.port)
        gspro.connect()

    # Handle clean shutdown
    def shutdown(signum, frame):
        global _shutting_down
        if _shutting_down:
            return
        _shutting_down = True
        print(f"\n[Receiver] Shutting down...")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Run server
    try:
        run_server(args.socket, db, session_id, gspro)
    except SystemExit:
        pass
    finally:
        try:
            db.end_session(session_id)
            shots = db.get_session_shots(session_id)
            print(f"[Receiver] Session #{session_id} ended — {len(shots)} shots")
        except Exception:
            pass
        if gspro:
            gspro.close()
        try:
            db.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
