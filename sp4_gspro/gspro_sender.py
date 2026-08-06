#!/usr/bin/env python3
"""
GSPro Open Connect v1 — TCP Shot Sender with SQLite Logging
Project: Jetson LM (SP4)
Purpose: Send dummy (or real) shot data to GSPro or OpenShotGolf over TCP.
         Every shot is logged to a local SQLite database.

Usage:
    python3 gspro_sender.py --ip 192.168.1.100                          # interactive, default player
    python3 gspro_sender.py --ip 192.168.1.100 --player "Max"           # named player
    python3 gspro_sender.py --ip 192.168.1.100 --port 921               # real GSPro
    python3 gspro_sender.py --ip 192.168.1.100 --once                   # single shot
    python3 gspro_sender.py --ip 192.168.1.100 --club driver            # driver template
    python3 gspro_sender.py --ip 192.168.1.100 --no-db                  # skip database logging

Protocol reference: https://gsprogolf.com/GSProConnectV1.html
Compatible with:    GSPro (port 921), OpenShotGolf (port 49152)
"""

import argparse
import json
import socket
import sys
import random
import time
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEVICE_ID = "Jetson LM 1.0"
API_VERSION = "1"
DEFAULT_PORT = 49152  # OpenShotGolf default — use --port 921 for real GSPro
RECV_TIMEOUT = 5
RECV_BUFFER = 4096

# Club name mapping: template name -> short code stored in DB
CLUB_CODES = {
    "driver": "DR",
    "7-iron": "7I",
    "pitching-wedge": "PW",
}

# ---------------------------------------------------------------------------
# Shot data templates — realistic golf shots
# ---------------------------------------------------------------------------

SHOT_TEMPLATES = {
    "7-iron": {
        "Speed": 132.0,
        "SpinAxis": -3.5,
        "TotalSpin": 3200.0,
        "BackSpin": 3100.0,
        "SideSpin": -350.0,
        "HLA": -1.2,
        "VLA": 18.5,
    },
    "driver": {
        "Speed": 155.0,
        "SpinAxis": 2.0,
        "TotalSpin": 2800.0,
        "BackSpin": 2750.0,
        "SideSpin": 200.0,
        "HLA": 0.5,
        "VLA": 12.0,
    },
    "pitching-wedge": {
        "Speed": 105.0,
        "SpinAxis": -1.0,
        "TotalSpin": 6500.0,
        "BackSpin": 6480.0,
        "SideSpin": -150.0,
        "HLA": -0.5,
        "VLA": 26.0,
    },
}


def add_variation(ball_data: dict, variance_pct: float = 0.08) -> dict:
    """Add small random variation so each shot looks different."""
    varied = {}
    for key, val in ball_data.items():
        if isinstance(val, (int, float)):
            delta = val * random.uniform(-variance_pct, variance_pct)
            varied[key] = round(val + delta, 1)
        else:
            varied[key] = val
    return varied


def build_shot_payload(shot_number: int, ball_data: dict) -> dict:
    """Build the full JSON payload per GSPro Open Connect v1 spec."""
    return {
        "DeviceID": DEVICE_ID,
        "Units": "Yards",
        "ShotNumber": shot_number,
        "APIversion": API_VERSION,
        "BallData": ball_data,
        "ClubData": {
            "Speed": 0.0,
            "AngleOfAttack": 0.0,
            "FaceToTarget": 0.0,
            "Lie": 0.0,
            "Loft": 0.0,
            "Path": 0.0,
            "SpeedAtImpact": 0.0,
            "VerticalFaceImpact": 0.0,
            "HorizontalFaceImpact": 0.0,
            "ClosureRate": 0.0,
        },
        "ShotDataOptions": {
            "ContainsBallData": True,
            "ContainsClubData": False,
            "LaunchMonitorIsReady": True,
            "LaunchMonitorBallDetected": True,
            "IsHeartBeat": False,
        },
    }


def build_heartbeat() -> dict:
    """Build a heartbeat payload to test the connection without sending a shot."""
    return {
        "DeviceID": DEVICE_ID,
        "Units": "Yards",
        "ShotNumber": 0,
        "APIversion": API_VERSION,
        "BallData": {},
        "ShotDataOptions": {
            "ContainsBallData": False,
            "ContainsClubData": False,
            "LaunchMonitorIsReady": True,
            "LaunchMonitorBallDetected": False,
            "IsHeartBeat": True,
        },
    }


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

def connect(ip: str, port: int) -> socket.socket:
    """Establish TCP connection to GSPro / OpenShotGolf."""
    print(f"[GSPro Sender] Connecting to {ip}:{port} ...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(RECV_TIMEOUT)
    try:
        sock.connect((ip, port))
    except ConnectionRefusedError:
        print("[GSPro Sender] ERROR: Connection refused.")
        print("  -> Is OpenShotGolf / GSPro running?")
        print(f"  -> Is the port correct? You used: {port}")
        print(f"  -> Is the IP correct? You used: {ip}")
        sys.exit(1)
    except socket.timeout:
        print("[GSPro Sender] ERROR: Connection timed out.")
        print(f"  -> Can the Jetson reach {ip}? Try: ping {ip}")
        print("  -> Are both machines on the same network?")
        print("  -> Is the Windows firewall allowing the port?")
        sys.exit(1)
    except OSError as e:
        print(f"[GSPro Sender] ERROR: {e}")
        sys.exit(1)
    print("[GSPro Sender] Connected!")
    return sock


def send_and_receive(sock: socket.socket, payload: dict) -> Optional[dict]:
    """Send JSON payload and receive response."""
    data = json.dumps(payload).encode("utf-8")
    sock.sendall(data)

    try:
        response_raw = sock.recv(RECV_BUFFER)
        if response_raw:
            response = json.loads(response_raw.decode("utf-8"))
            return response
    except socket.timeout:
        print("[GSPro Sender] Warning: No response (timeout). This may be OK for some targets.")
    except json.JSONDecodeError:
        print(f"[GSPro Sender] Warning: Non-JSON response: {response_raw}")
    return None


def print_response(response: Optional[dict]):
    """Pretty-print the response."""
    if response is None:
        return
    code = response.get("Code", "?")
    msg = response.get("Message", "")
    print(f"[GSPro Sender] Response: Code {code} — {msg}")
    if code == 201 and "Player" in response:
        player = response["Player"]
        print(f"  -> Player: {player.get('Handed', '?')}, Club: {player.get('Club', '?')}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Send dummy golf shots to GSPro / OpenShotGolf"
    )
    parser.add_argument(
        "--ip", required=True,
        help="IP address of the PC running OpenShotGolf or GSPro"
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help=f"Target port (default: {DEFAULT_PORT} for OpenShotGolf, use 921 for GSPro)"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Send a single shot and exit (for scripting / pipeline use)"
    )
    parser.add_argument(
        "--club", choices=list(SHOT_TEMPLATES.keys()), default="7-iron",
        help="Club template for dummy shot data (default: 7-iron)"
    )
    parser.add_argument(
        "--player", default="Default Player",
        help="Player name for session logging (default: 'Default Player')"
    )
    parser.add_argument(
        "--no-db", action="store_true",
        help="Disable database logging (send shots without recording)"
    )
    args = parser.parse_args()

    # --- Database setup ---
    db = None
    session_id = None

    if not args.no_db:
        try:
            from shot_db import ShotDB
            db = ShotDB()

            # Get or create player
            players = db.list_players()
            player = next((p for p in players if p["name"] == args.player), None)
            if player:
                player_id = player["id"]
            else:
                player_id = db.add_player(args.player, "RH")
                print(f"[ShotDB] Created player: {args.player} (ID {player_id})")

            # Get or create course based on target
            target_name = "GSPro" if args.port == 921 else "OpenShotGolf"
            course_name = f"{target_name} Driving Range"
            course = db.get_course_by_name(course_name)
            if course:
                course_id = course["id"]
            else:
                course_id = db.add_course(course_name, target_name, "range")

            # Start session
            session_id = db.start_session(
                player_id, course_id, target_name,
                args.ip, args.port
            )
            print(f"[ShotDB] Session #{session_id} started for {args.player}")

        except ImportError:
            print("[ShotDB] Warning: shot_db.py not found — running without database logging")
            db = None
        except Exception as e:
            print(f"[ShotDB] Warning: Database error — {e} — running without logging")
            db = None

    # --- Connect ---
    sock = connect(args.ip, args.port)

    try:
        # Send heartbeat first
        print("[GSPro Sender] Sending heartbeat ...")
        hb = build_heartbeat()
        resp = send_and_receive(sock, hb)
        print_response(resp)
        time.sleep(0.5)

        shot_number = 1

        while True:
            template = SHOT_TEMPLATES[args.club]
            ball_data = add_variation(template)
            club_code = CLUB_CODES.get(args.club, args.club.upper())

            print(
                f"[GSPro Sender] Sending shot #{shot_number} — {args.club}: "
                f"{ball_data['Speed']} mph, "
                f"VLA {ball_data['VLA']}°, "
                f"HLA {ball_data['HLA']}°"
            )

            payload = build_shot_payload(shot_number, ball_data)
            resp = send_and_receive(sock, payload)
            print_response(resp)

            response_code = resp.get("Code") if resp else None

            if response_code == 200:
                print("[GSPro Sender] SUCCESS — ball should be flying on screen!")
            elif resp and response_code and response_code >= 500:
                print("[GSPro Sender] ERROR — server returned a failure code.")

            # Log to database
            if db and session_id:
                shot_id = db.log_shot(
                    session_id=session_id,
                    shot_number=shot_number,
                    club=club_code,
                    ball_data=ball_data,
                    club_data=payload.get("ClubData", {}),
                    response_code=response_code
                )
                print(f"[ShotDB] Shot #{shot_number} logged (ID {shot_id})")

            if args.once:
                break

            print()
            try:
                user_input = input(
                    "Press Enter to send another shot, or 'q' to quit: "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if user_input == "q":
                break

            shot_number += 1

    finally:
        # End session and print summary
        if db and session_id:
            db.end_session(session_id)
            shots = db.get_session_shots(session_id)
            print(f"\n[ShotDB] Session #{session_id} ended — {len(shots)} shots logged")
            if shots:
                speeds = [s["ball_speed"] for s in shots if s["ball_speed"]]
                if speeds:
                    print(f"[ShotDB] Ball speed: avg {sum(speeds)/len(speeds):.1f}, "
                          f"min {min(speeds):.1f}, max {max(speeds):.1f} mph")
            db.close()

        print("[GSPro Sender] Disconnecting ...")
        sock.close()
        print("[GSPro Sender] Done.")


if __name__ == "__main__":
    main()
