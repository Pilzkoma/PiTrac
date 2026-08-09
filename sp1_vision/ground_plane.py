#!/usr/bin/env python3
"""The floor, fitted from triangulated ball centres, and what it implies.

Every resting golf ball has its centre exactly one radius above the floor -
21.335 mm. So a set of triangulated ball centres lies in a plane parallel to
the floor by construction, and fitting that plane measures how the device
sits relative to the ground. Nothing else in this project measures that: the
stereo extrinsics describe camera 1 against camera 2, not the pair against
the world.

A plane cannot give yaw. It is rotationally symmetric about its normal, so
the target-line pair is a separate measurement and cannot be recovered
afterwards from a floor-only series.
"""

import numpy as np

GOLF_BALL_RADIUS_M = 0.021335

# How square the point spread must be before a plane is considered
# determined. The second singular value carries the spread perpendicular to
# the dominant direction; when it collapses, the points are effectively a
# line and the plane can rotate freely about it while the residual stays
# small. Reporting only the residual is how an undetermined answer gets
# mistaken for a good one.
MIN_CONDITIONING = 0.15


class PlaneFitError(ValueError):
    """The points do not determine a plane, or a direction within it."""


class PlaneFit:
    """A fitted plane, with enough information to distrust it."""

    def __init__(self, normal, centroid, residuals_m, conditioning):
        self.normal = normal
        self.centroid = centroid
        self.residuals_m = residuals_m
        self.conditioning = conditioning

    @property
    def rms_m(self):
        return float(np.sqrt(np.mean(self.residuals_m ** 2)))


def fit_plane(points_m):
    """Least-squares plane through 3+ points, normal oriented upward.

    Upward in the camera frame means -Y, since Y is down. SVD returns a
    normal of arbitrary sign, and leaving it alone would negate the reported
    pitch on roughly half of all runs.
    """
    pts = np.asarray(points_m, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise PlaneFitError("expected an (N, 3) array, got {}".format(pts.shape))
    if pts.shape[0] < 3:
        raise PlaneFitError(
            "a plane needs at least 3 points, got {}".format(pts.shape[0]))

    centroid = pts.mean(axis=0)
    centred = pts - centroid
    _, singular, vt = np.linalg.svd(centred, full_matrices=False)

    conditioning = float(singular[1] / singular[0]) if singular[0] > 0 else 0.0
    if conditioning < MIN_CONDITIONING:
        raise PlaneFitError(
            "points are near-collinear (conditioning {:.3f} < {:.2f}); the "
            "plane fits well and determines nothing. Spread the ball "
            "positions across the image width, not just in depth.".format(
                conditioning, MIN_CONDITIONING))

    normal = vt[2]
    if normal[1] > 0:
        normal = -normal

    return PlaneFit(normal=normal, centroid=centroid,
                     residuals_m=centred @ normal, conditioning=conditioning)


def attitude_from_plane(plane):
    """Return (pitch_deg, roll_deg) of the camera against the floor.

    With the camera level the floor normal is exactly (0, -1, 0). Rolling by
    phi rotates it to (sin phi, -cos phi, 0), so roll_deg = arcsin(n[0])
    directly - positive roll follows the camera's Z axis, matching the sign
    convention used to build the test fixtures.

    Pitching by theta rotates the level normal to (0, -cos theta, -sin
    theta), not (0, -cos theta, +sin theta): in this frame Y points down and
    Z points forward, and rotating "up" about X carries -Y towards -Z, not
    +Z. That flips the sign against the naive expectation, so
    pitch_deg = -arcsin(n[2]), and it was checked numerically against the
    rotation in test_ground_plane.floor_points rather than assumed - a wrong
    sign here would silently pass the level-floor case (n[2] = 0 either way)
    and only show up once real pitch appeared.

    The two angles are independent to first order: n[2] carries no roll
    term at all, and n[0]'s dependence on pitch is a cos(theta) factor that
    is 1 to five nines at the angles this rig actually has.

    Yaw is absent on purpose - see yaw_from_target_line.
    """
    n = plane.normal
    pitch_deg = float(np.degrees(np.arcsin(np.clip(-n[2], -1.0, 1.0))))
    roll_deg = float(np.degrees(np.arcsin(np.clip(n[0], -1.0, 1.0))))
    return pitch_deg, roll_deg


def yaw_from_target_line(plane, near_m, far_m):
    """Angle between the target line and the camera's forward axis, degrees.

    Both points are projected into the floor plane first, so a height error
    in either one cannot tilt the answer. Positive yaw means the target line
    runs to the camera's right.
    """
    near = np.asarray(near_m, dtype=np.float64).ravel()
    far = np.asarray(far_m, dtype=np.float64).ravel()

    direction = far - near
    if np.linalg.norm(direction) < 1e-6:
        raise PlaneFitError(
            "the two target-line points coincide; they must be far enough "
            "apart that the angle between them is meaningful")

    # Remove any component along the normal - what remains lies in the floor.
    in_plane = direction - np.dot(direction, plane.normal) * plane.normal
    if np.linalg.norm(in_plane) < 1e-9:
        raise PlaneFitError(
            "the target line is perpendicular to the floor; check the two "
            "points are on the ground and distinct")

    return float(np.degrees(np.arctan2(in_plane[0], in_plane[2])))
