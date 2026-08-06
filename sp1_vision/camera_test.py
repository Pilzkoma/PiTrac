#!/usr/bin/env python3
"""
SP1 Camera Detection & Test Tool
Project: Jetson LM
Purpose: Detect USB cameras, show capabilities, capture test frames.
         Run this when the OV9281 cameras arrive to verify they work.

Usage:
    python3 camera_test.py                  # detect all cameras
    python3 camera_test.py --capture        # detect + capture a frame from each
    python3 camera_test.py --device 0       # test specific /dev/video0
    python3 camera_test.py --monitor 0      # live preview from /dev/video0

Requirements: v4l-utils (apt install v4l-utils), OpenCV (pre-installed on JetPack)
"""

import argparse
import subprocess
import sys
import os
import glob
import time


def run_cmd(cmd):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", 1


def detect_video_devices():
    """Find all /dev/video* devices."""
    devices = sorted(glob.glob("/dev/video*"))
    return devices


def get_device_info(device):
    """Get V4L2 device info using v4l2-ctl."""
    info = {}

    # Device name and driver
    out, rc = run_cmd(f"v4l2-ctl -d {device} --info")
    if rc != 0:
        return None

    for line in out.split("\n"):
        line = line.strip()
        if "Card type" in line:
            info["name"] = line.split(":", 1)[1].strip()
        elif "Driver name" in line:
            info["driver"] = line.split(":", 1)[1].strip()
        elif "Bus info" in line:
            info["bus"] = line.split(":", 1)[1].strip()

    # Supported formats
    out, rc = run_cmd(f"v4l2-ctl -d {device} --list-formats-ext")
    info["formats"] = out if rc == 0 else "Unable to query"

    # Current format
    out, rc = run_cmd(f"v4l2-ctl -d {device} --get-fmt-video")
    info["current_format"] = out if rc == 0 else "Unable to query"

    return info


def check_usb_devices():
    """List USB devices to see if cameras are connected."""
    out, _ = run_cmd("lsusb")
    cameras = []
    for line in out.split("\n"):
        # OV9281 typically shows as "Arducam" or specific USB VID:PID
        lower = line.lower()
        if any(kw in lower for kw in ["arducam", "camera", "video", "ov9281", "2a64"]):
            cameras.append(line.strip())
    return out, cameras


def capture_frame(device_idx):
    """Capture a single frame using OpenCV."""
    try:
        import cv2
    except ImportError:
        print("[ERROR] OpenCV not found. It should be pre-installed on JetPack.")
        print("  Try: python3 -c 'import cv2; print(cv2.__version__)'")
        return False

    device = f"/dev/video{device_idx}"
    print(f"\n[Capture] Opening {device} ...")

    cap = cv2.VideoCapture(device_idx, cv2.CAP_V4L2)
    if not cap.isOpened():
        print(f"[Capture] ERROR: Cannot open {device}")
        return False

    # Try to set to highest resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 800)

    # Read actual resolution
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"[Capture] Resolution: {w}x{h}, FPS: {fps}")

    # Grab a few frames (first frames are often blank)
    print("[Capture] Warming up (grabbing 10 frames) ...")
    for _ in range(10):
        cap.read()

    ret, frame = cap.read()
    if not ret or frame is None:
        print("[Capture] ERROR: Failed to read frame")
        cap.release()
        return False

    # Save
    filename = f"test_capture_video{device_idx}_{w}x{h}.png"
    cv2.imwrite(filename, frame)
    print(f"[Capture] Saved: {filename}")
    print(f"[Capture] Frame shape: {frame.shape}, dtype: {frame.dtype}")
    print(f"[Capture] Min pixel: {frame.min()}, Max pixel: {frame.max()}, Mean: {frame.mean():.1f}")

    # Check if it's a monochrome sensor (OV9281 should be)
    if len(frame.shape) == 2 or (len(frame.shape) == 3 and frame.shape[2] == 1):
        print("[Capture] Monochrome sensor detected (expected for OV9281)")
    elif len(frame.shape) == 3:
        # Check if R=G=B (mono delivered as BGR)
        b, g, r = frame[:,:,0], frame[:,:,1], frame[:,:,2]
        if (b == g).all() and (g == r).all():
            print("[Capture] Monochrome data in BGR format (expected for OV9281 USB)")
        else:
            print("[Capture] Color sensor detected (unexpected for OV9281)")

    cap.release()
    return True


def monitor_camera(device_idx):
    """Live preview using OpenCV — press 'q' to quit."""
    try:
        import cv2
    except ImportError:
        print("[ERROR] OpenCV not found.")
        return

    device = f"/dev/video{device_idx}"
    print(f"\n[Monitor] Opening {device} — press 'q' to quit ...")

    cap = cv2.VideoCapture(device_idx, cv2.CAP_V4L2)
    if not cap.isOpened():
        print(f"[Monitor] ERROR: Cannot open {device}")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 800)

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[Monitor] Resolution: {w}x{h}")

    frame_count = 0
    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[Monitor] Frame read failed")
            break

        frame_count += 1
        elapsed = time.time() - start_time
        if elapsed > 0:
            actual_fps = frame_count / elapsed
            cv2.putText(frame, f"FPS: {actual_fps:.1f}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        cv2.imshow(f"Jetson LM — Camera {device_idx}", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print(f"[Monitor] Done — {frame_count} frames in {elapsed:.1f}s ({actual_fps:.1f} FPS)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SP1 Camera Detection & Test")
    parser.add_argument("--capture", action="store_true", help="Capture test frame from each camera")
    parser.add_argument("--device", type=int, default=None, help="Test specific /dev/videoN device")
    parser.add_argument("--monitor", type=int, default=None, help="Live preview from /dev/videoN")
    args = parser.parse_args()

    # Live monitor mode
    if args.monitor is not None:
        monitor_camera(args.monitor)
        return

    print("=" * 60)
    print("  Jetson LM — SP1 Camera Detection & Test")
    print("=" * 60)

    # Check prerequisites
    print("\n[1/5] Checking prerequisites ...")
    v4l2_ctl, rc = run_cmd("which v4l2-ctl")
    if rc != 0:
        print("  WARNING: v4l2-ctl not found. Install with:")
        print("    sudo apt install v4l-utils")
    else:
        print(f"  v4l2-ctl: {v4l2_ctl}")

    try:
        import cv2
        print(f"  OpenCV: {cv2.__version__}")
        cuda_enabled = cv2.cuda.getCudaEnabledDeviceCount() > 0 if hasattr(cv2, 'cuda') else False
        print(f"  CUDA in OpenCV: {'Yes' if cuda_enabled else 'No'}")
    except ImportError:
        print("  WARNING: OpenCV not found")

    # USB devices
    print("\n[2/5] USB devices ...")
    usb_output, camera_matches = check_usb_devices()
    if camera_matches:
        print(f"  Found {len(camera_matches)} potential camera(s):")
        for cam in camera_matches:
            print(f"    {cam}")
    else:
        print("  No camera-like USB devices detected.")
        print("  Expected: Arducam OV9281 USB3")
        print("  Make sure cameras are plugged into USB3 ports (blue)")

    # Video devices
    print("\n[3/5] Video devices (/dev/video*) ...")
    devices = detect_video_devices()
    if not devices:
        print("  No video devices found.")
        print("  If cameras are plugged in, check:")
        print("    - USB cable and port (try different port)")
        print("    - dmesg | tail -20  (look for USB errors)")
        print("    - sudo modprobe uvcvideo  (load UVC driver)")
        return

    print(f"  Found {len(devices)} video device(s)")

    # Device details
    print("\n[4/5] Device details ...")
    valid_devices = []
    for dev in devices:
        info = get_device_info(dev)
        if info is None:
            print(f"\n  {dev}: Unable to query (may be metadata device)")
            continue

        print(f"\n  {dev}:")
        print(f"    Name:   {info.get('name', '?')}")
        print(f"    Driver: {info.get('driver', '?')}")
        print(f"    Bus:    {info.get('bus', '?')}")

        # Check if this is an OV9281
        name_lower = info.get('name', '').lower()
        if 'arducam' in name_lower or 'ov9281' in name_lower:
            print(f"    >>> OV9281 DETECTED! <<<")

        if info.get('formats'):
            print(f"    Formats:")
            for line in info['formats'].split('\n'):
                if line.strip():
                    print(f"      {line.strip()}")

        valid_devices.append(dev)

    # Capture test
    if args.capture or args.device is not None:
        print("\n[5/5] Test capture ...")
        if args.device is not None:
            capture_frame(args.device)
        else:
            for dev in valid_devices:
                idx = int(dev.replace("/dev/video", ""))
                capture_frame(idx)
    else:
        print("\n[5/5] Skipping capture (run with --capture to test)")

    # Summary
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    print(f"  Video devices: {len(devices)}")
    print(f"  Valid cameras: {len(valid_devices)}")
    if valid_devices:
        print(f"  Devices: {', '.join(valid_devices)}")
        print(f"\n  Next steps:")
        print(f"    python3 camera_test.py --capture           # grab test frames")
        print(f"    python3 camera_test.py --monitor 0         # live preview")
        print(f"    python3 camera_test.py --monitor 1         # second camera")
    else:
        print(f"\n  No cameras detected. When cameras arrive:")
        print(f"    1. Plug into USB3 port (blue)")
        print(f"    2. Run: dmesg | tail -20")
        print(f"    3. Run: python3 camera_test.py")
    print()


if __name__ == "__main__":
    main()
