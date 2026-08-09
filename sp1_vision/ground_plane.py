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

    Upward in the camera frame means -Y, since Y is down. SVD's vt[2] sign
    is deterministic for a given input, but which sign it picks is not
    under this function's control, and it is not always upward: for this
    module's own test fixture at pitch +-2 deg it comes out downward
    unless corrected here (verified by temporarily deleting this flip and
    watching that test fail). Left uncorrected, that would silently negate
    the reported pitch for real inputs that happen to land on the other
    side of LAPACK's sign choice.
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

    Camera frame: X right, Y down, Z forward. Both angles are right-handed
    about their own axis. Positive pitch is nose-up (rotation about +X).
    Positive roll is right-side-down (rotation about +Z: +X rotates toward
    +Y).

    Both formulas below are exact for this module's own composition -
    pitch about X applied first, then roll about the fixed Z, i.e. points
    are rotated by R = Rz(roll) @ Rx(pitch) in test_ground_plane's
    floor_points, and a world-fixed point in a camera rotated by R
    transforms by R^-1 = R.T. Working that through for the level-camera
    normal (0, -1, 0) gives, for pitch theta and roll phi together:

        n = (-sin phi, -cos theta * cos phi, sin theta * cos phi)

    n[0] carries no pitch term at all - Rz(-phi) sets it before Rx(-theta)
    ever touches Y or Z - so roll_deg = -arcsin(n[0]) is exact for any
    pitch, not just phi=0. n[1] and n[2] both carry the same cos(phi)
    factor, and it cancels in their ratio: n[2] / -n[1] = tan(theta)
    regardless of roll, so pitch_deg = arctan2(n[2], -n[1]) is exact too.
    Checked against the ends: pure pitch gives n=(0,-cos t,sin t), so
    arctan2(sin t, cos t) = t and roll 0; pure roll gives n=(-sin p,-cos
    p,0), so pitch arctan2(0, cos p) = 0 and roll -arcsin(-sin p) = p.
    Verified numerically against the fixture up to 45/30 deg pitch/roll,
    matching to 1e-9 deg.

    An earlier version of this function had arcsin(n[2]) for pitch and
    arctan2(n[0], -n[1]) for roll - each one is the one that is NOT exact,
    since it is the one missing the ratio that cancels the other angle's
    cosine. Recorded here because that mistake was easy to make (both
    forms look plausible and both pass every test at these small angles to
    within a couple hundredths of a degree) and easy to make again.

    Yaw is absent on purpose - see yaw_from_target_line.
    """
    n = plane.normal
    pitch_deg = float(np.degrees(np.arctan2(n[2], -n[1])))
    roll_deg = float(-np.degrees(np.arcsin(np.clip(n[0], -1.0, 1.0))))
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
