#!/usr/bin/env python3
"""
Test Client — Simulates pitrac_lm sending shots over Unix domain socket.
Project: Jetson LM (SP4)
Purpose: Test the shot_receiver.py service without needing the C++ pipeline.
         Sends the same JSON format that pitrac_lm will send.

Usage:
    python3 test_client.py                    # interactive, 7-iron
    python3 test_client.py --club DR          # driver
    python3 test_client.py --once             # single shot
    python3 test_client.py --burst 10         # rapid-fire 10 shots

Run shot_receiver.py first in another terminal, then run this.
"""

import argparse
import json
import os
import random
import socket
import sys
import time

DEFAULT_SOCKET_PATH = "/tmp/jetson_lm.sock"

# Shot templates — same data as gspro_sender.py but in the C++ → Python format
TEMPLATES = {
    "7I": {
        "Speed": 132.0, "SpinAxis": -3.5, "TotalSpin": 3200.0,
        "BackSpin": 3100.0, "SideSpin": -350.0, "HLA": -1.2, "VLA": 18.5,
    },
    "DR": {
        "Speed": 155.0, "SpinAxis": 2.0, "TotalSpin": 2800.0,
        "BackSpin": 2750.0, "SideSpin": 200.0, "HLA": 0.5, "VLA": 12.0,
    },
    "PW": {
        "Speed": 105.0, "SpinAxis": -1.0, "TotalSpin": 6500.0,
        "BackSpin": 6480.0, "SideSpin": -150.0, "HLA": -0.5, "VLA": 26.0,
    },
    "5I": {
        "Speed": 140.0, "SpinAxis": -2.0, "TotalSpin": 4200.0,
        "BackSpin": 4100.0, "SideSpin": -300.0, "HLA": -0.8, "VLA": 15.0,
    },
    "SW": {
        "Speed": 85.0, "SpinAxis": -0.5, "TotalSpin": 8500.0,
        "BackSpin": 8480.0, "SideSpin": -100.0, "HLA": -0.3, "VLA": 32.0,
    },
}


def vary(ball_data: dict) -> dict:
    """Add ±8% random variation."""
    result = {}
    for k, v in ball_data.items():
        if isinstance(v, (int, float)):
            result[k] = round(v + v * random.uniform(-0.08, 0.08), 1)
        else:
            result[k] = v
    return result


def send_shot(sock: socket.socket, club: str, ball_data: dict) -> dict:
    """Send a shot message and receive the response."""
    msg = {
        "club": club,
        "ball": ball_data,
    }
    sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))

    # Read response (newline-delimited)
    buf = ""
    while "\n" not in buf:
        data = sock.recv(4096)
        if not data:
            return {"status": "error", "message": "Connection closed"}
        buf += data.decode("utf-8")

    line = buf.split("\n")[0]
    return json.loads(line)


def main():
    parser = argparse.ArgumentParser(
        description="Test client — simulates pitrac_lm sending shots"
    )
    parser.add_argument(
        "--socket", default=DEFAULT_SOCKET_PATH,
        help=f"Unix socket path (default: {DEFAULT_SOCKET_PATH})"
    )
    parser.add_argument(
        "--club", choices=list(TEMPLATES.keys()), default="7I",
        help="Club to simulate (default: 7I)"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Send one shot and exit"
    )
    parser.add_argument(
        "--burst", type=int, default=0,
        help="Send N shots rapidly with 0.5s delay between each"
    )
    args = parser.parse_args()

    if not os.path.exists(args.socket):
        print(f"[TestClient] Socket not found: {args.socket}")
        print("  -> Is shot_receiver.py running?")
        sys.exit(1)

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(args.socket)
    except ConnectionRefusedError:
        print("[TestClient] Connection refused — is shot_receiver.py running?")
        sys.exit(1)

    print(f"[TestClient] Connected to {args.socket}")
    print(f"[TestClient] Simulating pitrac_lm C++ pipeline")
    print()

    shot = 0

    try:
        # Burst mode
        if args.burst > 0:
            clubs = list(TEMPLATES.keys())
            for i in range(args.burst):
                club = random.choice(clubs)
                ball = vary(TEMPLATES[club])
                shot += 1
                print(f"[TestClient] Shot {i+1}/{args.burst} — {club}: {ball['Speed']} mph")
                resp = send_shot(sock, club, ball)
                print(f"  -> {resp}")
                time.sleep(0.5)
            return

        # Interactive / single mode
        while True:
            ball = vary(TEMPLATES[args.club])
            shot += 1

            print(
                f"[TestClient] Sending shot #{shot} — {args.club}: "
                f"{ball['Speed']} mph, VLA {ball['VLA']}°"
            )

            resp = send_shot(sock, args.club, ball)

            status = resp.get("status", "?")
            shot_id = resp.get("shot_id", "?")
            gspro_code = resp.get("gspro_code", "?")
            print(f"  -> status: {status}, shot_id: {shot_id}, gspro_code: {gspro_code}")

            if args.once:
                break

            print()
            try:
                inp = input("Enter=next shot, club code (DR/7I/PW/5I/SW)=switch, q=quit: ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if inp.lower() == "q":
                break
            if inp.upper() in TEMPLATES:
                args.club = inp.upper()
                print(f"  -> Switched to {args.club}")

    finally:
        sock.close()
        print(f"\n[TestClient] Done — {shot} shots sent")


if __name__ == "__main__":
    main()
