#!/usr/bin/env python3
"""Powering the Jetson off from the dashboard and from Golfinator.

The dashboard runs as `brain`, and `systemctl poweroff` needs root. The one
command is allowed without a password by a sudoers drop-in that
install_system_permissions.sh writes; nothing else is granted for power.

The poweroff is started detached and a second late, so the HTTP reply that
says it is happening still gets out before the network goes down.
"""

import socket
import subprocess

SYSTEMCTL = "/usr/bin/systemctl"
POWEROFF = [SYSTEMCTL, "poweroff"]

# Long enough for the reply to leave, short enough to feel immediate.
POWEROFF_DELAY_S = 1

# Every state-changing system request must carry this header. A browser only
# sends a custom header cross-origin after a CORS preflight that this server
# never approves, so a stray web page cannot power the Jetson off with a
# hidden form. Golfinator sends it too.
REQUEST_HEADER = "X-JetsonLM"


def can_power_off():
    """True when sudo lets this user run the poweroff without a password."""
    try:
        done = subprocess.run(["sudo", "-n", "-l"] + POWEROFF,
                              capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def power_off():
    """Start the poweroff in the background; returns (ok, error message)."""
    if not can_power_off():
        return False, ("keine Berechtigung: einmal "
                       "'sudo bash sp4_gspro/install_system_permissions.sh' "
                       "auf dem Jetson ausführen")
    cmd = "sleep {}; sudo -n {}".format(POWEROFF_DELAY_S, " ".join(POWEROFF))
    subprocess.Popen(["sh", "-c", cmd], start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    return True, None


def status():
    """What Golfinator and the header need to know about the box."""
    return {
        "device": "JetsonLM",
        "hostname": socket.gethostname(),
        "can_power_off": can_power_off(),
    }
