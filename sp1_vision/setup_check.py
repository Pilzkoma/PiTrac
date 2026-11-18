"""Setup check: where the ball should rest, and how to move the unit to get there.

Agreed with the owner 2026-11-18: the unit is set up once and then not
moved, and the ball has its own spot. This check is for setting up: one
flash, the stereo position of the ball on its spot, compared with the target
- the ball centre 50 cm in front of the REAR camera, the one the ball flies
away from, so the flight stays in view for as many frames as possible.

All positions are in camera 1's frame, metres, OpenCV axes (X right, Y down,
Z forward). A right-handed golfer faces the unit and hits to their left,
which is +x here (the 2026-11-18 putts move towards +u); camera 2 sits at
x = -80 mm, so it is the rear camera for right-handers.

"Distance" is the depth along the cameras' axis, not along the floor: with
the unit's +1.6 deg pitch the two differ by about 3 mm at the ball, well
inside the tolerance.
"""

import numpy as np

from sp1_vision import stereo_geometry

# The owner's reference (2026-11-18): 500 mm by tape from the rear camera's
# board (its sensor) to the ball centre. The stereo frame's origin is the
# camera's optical centre, about one focal length (calibrated 2.751 mm) in
# front of the sensor, so the target depth from there is 2.75 mm less.
TARGET_DISTANCE_M = 0.50
SENSOR_TO_OPTICAL_CENTRE_M = 0.00275
TOLERANCE_MM = 10.0
EDGE_MARGIN_PX = 40
_EPS_MM = 1e-6          # float noise at the tolerance boundary


def flight_sign(handedness):
    """+1 for a right-handed golfer (ball flies towards +x), -1 for a left-handed one."""
    if handedness == "RH":
        return 1
    if handedness == "LH":
        return -1
    raise ValueError("handedness must be 'RH' or 'LH', not {!r}".format(handedness))


def camera_centres(rig):
    return {1: np.zeros(3), 2: stereo_geometry.camera2_centre_in_camera1(rig)}


def rear_camera(rig, handedness):
    """The camera the ball flies away from."""
    s = flight_sign(handedness)
    centres = camera_centres(rig)
    return min(centres, key=lambda n: centres[n][0] * s)


def target_xyz_m(rig, handedness, ball_y_m):
    """The target ball centre: TARGET_DISTANCE_M from the rear camera's
    sensor, at the measured ball's height (height is not part of the check)."""
    c = camera_centres(rig)[rear_camera(rig, handedness)]
    return np.array([c[0], ball_y_m, c[2] + TARGET_DISTANCE_M - SENSOR_TO_OPTICAL_CENTRE_M])


class Offsets:
    """Ball minus target: along the flight direction and in depth, mm."""

    def __init__(self, along_mm, depth_mm):
        self.along_mm = float(along_mm)
        self.depth_mm = float(depth_mm)

    @property
    def ok(self):
        return (abs(self.along_mm) <= TOLERANCE_MM + _EPS_MM
                and abs(self.depth_mm) <= TOLERANCE_MM + _EPS_MM)


def offsets(ball_xyz_m, target_xyz_m, handedness):
    d = (np.asarray(ball_xyz_m, dtype=float) - np.asarray(target_xyz_m, dtype=float)) * 1000.0
    return Offsets(along_mm=d[0] * flight_sign(handedness), depth_mm=d[2])


def median_xyz(positions_m):
    """Component-wise median of several ball positions (one per flash).
    A single flash's depth jitters about +-5 mm (whole-pixel disparity, one
    pixel = 2.6 mm at 50 cm), and one bad pairing must not move the result."""
    return np.median(np.asarray(positions_m, dtype=float), axis=0)


def depth_spread_mm(positions_m):
    """Largest minus smallest depth of the flashes, mm."""
    z = np.asarray(positions_m, dtype=float)[:, 2]
    return float((z.max() - z.min()) * 1000.0)


def margin_ok(ball, image_size=(1280, 800)):
    """Both circles at least EDGE_MARGIN_PX inside their image."""
    w, h = image_size
    for (u, v), r in ((ball.uv1, ball.radius1_px), (ball.uv2, ball.radius2_px)):
        m = r + EDGE_MARGIN_PX
        if u < m or v < m or u > w - m or v > h - m:
            return False
    return True


def advice(off):
    """How to move the UNIT (the ball's spot is fixed), in German."""
    lines = []
    if abs(off.depth_mm) > TOLERANCE_MM + _EPS_MM:
        n = int(round(abs(off.depth_mm)))
        lines.append("Einheit {} mm {}".format(
            n, "näher zum Ball schieben" if off.depth_mm > 0 else "vom Ball weg schieben"))
    if abs(off.along_mm) > TOLERANCE_MM + _EPS_MM:
        n = int(round(abs(off.along_mm)))
        lines.append("Einheit {} mm {}".format(
            n, "in Schlagrichtung schieben" if off.along_mm > 0
            else "gegen die Schlagrichtung schieben"))
    return lines or ["Passt - innerhalb ±{:.0f} mm".format(TOLERANCE_MM)]
