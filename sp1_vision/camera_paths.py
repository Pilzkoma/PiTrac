#!/usr/bin/env python3
"""Bind logical cameras to device nodes by USB port path.

Both Arducam B0332 modules report the same USB identity: VID:PID 0c45:6366,
bcdDevice 1.00, iSerial "UC762" - which is Arducam's SKU code, not a per-unit
serial. /dev/v4l/by-id/ therefore holds a single colliding entry, and
/dev/videoN is assigned in enumeration order.

If the two cameras swap numbers across a reboot, the stereo baseline changes
sign and depth comes out mirrored, with nothing visibly wrong in either image.
The USB port path is the only stable discriminator. This has already bitten
once: the port comment in v4l2_interface.cpp recorded xhci-2.2.4 and xhci-2.3,
while the hardware now enumerates on 2.3 and 2.4.
"""

import os

BY_PATH_DIR = "/dev/v4l/by-path"

# Logical camera number -> USB port path, as enumerated on the Xavier NX
# carrier board.
#
# Which physical module sits on which port, confirmed 2026-08-06 two ways
# that agree:
#
#   camera 1  port 2.3   LEFT  module, standing in front of the unit
#   camera 2  port 2.4   RIGHT module, standing in front of the unit
#
#   * covering the right-hand lens darkened the right-hand stream, which the
#     page serves from camera 2;
#   * a patch from the centre of camera 2 was found 76 px further left in
#     camera 1 (correlation 0.95), which puts camera 1 to the right along the
#     cameras' own axis.
#
# Those two read as contradictory until you fix the frame of reference, and
# that confusion is exactly how a stereo baseline ends up sign-flipped. Facing
# the unit you are looking back down the optical axes, so your left and right
# are mirrored from the cameras'. Camera 1 is on your left and on the cameras'
# right. Both statements describe the same module.
#
# The comments here and in v4l2_interface.cpp must agree; nothing enforces it.
CAMERA_PORT_PATHS = {
    1: "platform-3610000.xhci-usb-0:2.3:1.0-video-index0",
    2: "platform-3610000.xhci-usb-0:2.4:1.0-video-index0",
}


class CameraBindingError(RuntimeError):
    """A camera could not be bound to a device node."""


def device_for_camera(camera_number, by_path_dir=BY_PATH_DIR):
    """Return the real device node for a logical camera.

    Raises CameraBindingError if the port is absent. Failing here is the
    point: falling back to whatever /dev/video0 happens to be would produce
    mirrored depth, which is worse than not starting.
    """
    if camera_number not in CAMERA_PORT_PATHS:
        raise CameraBindingError(
            "unknown camera number {!r}; known cameras are {}".format(
                camera_number, sorted(CAMERA_PORT_PATHS)
            )
        )

    link = os.path.join(by_path_dir, CAMERA_PORT_PATHS[camera_number])
    if not os.path.exists(link):
        raise CameraBindingError(
            "camera {} expected at USB port {!r} but that path does not exist. "
            "Check the USB cable is in its usual socket; the two modules are "
            "indistinguishable by serial, so the socket is the identity.".format(
                camera_number, link
            )
        )
    return os.path.realpath(link)


def all_devices(by_path_dir=BY_PATH_DIR):
    """Return {camera_number: device node} for both cameras."""
    return {n: device_for_camera(n, by_path_dir) for n in sorted(CAMERA_PORT_PATHS)}
