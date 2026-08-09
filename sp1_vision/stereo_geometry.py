#!/usr/bin/env python3
"""The stereo rig, and the only place its frames and units are converted.

Two conversions in this project are silent when wrong. Millimetres read as
metres scales every depth by a thousand, which is obvious; a Y axis read
upward when the file means downward flips launch angle, which is not. Both
live here and nowhere else, so there is one place to check and one place to
test.

The intrinsics come from golf_sim_config.json and the extrinsics from
stereo_extrinsics.json, and they are only self-consistent as a pair:
CALIB_FIX_INTRINSIC makes the stereo step absorb whatever error the camera
matrices carry into R and T. Nothing in the extrinsics file records which
intrinsics it was solved against, so the checks below are the best available
substitute - they catch a grossly wrong pairing, not a subtly wrong one.
"""

import json

import numpy as np

# What a loaded rig must satisfy before anything is computed from it. These
# are not precision bounds; each one catches a specific way of holding the
# files wrong.
MIN_BASELINE_M = 0.070       # a wrong square size scales the baseline outright
MAX_BASELINE_M = 0.090
MAX_RELATIVE_ROTATION_DEG = 3.0   # the mount is bolted; more means swapped files
NOMINAL_FX_PX = 900.0             # 2.70 mm lens on 3.0 um pixels
FX_TOLERANCE_FRACTION = 0.10
EXPECTED_IMAGE_SIZE = (1280, 800)

DEFAULT_EXTRINSICS_PATH = "sp1_vision/calibration_results/stereo_extrinsics.json"
DEFAULT_CONFIG_PATH = "Software/LMSourceCode/ImageProcessing/golf_sim_config.json"


class StereoRigError(ValueError):
    """The rig is not usable, and saying so beats computing from it."""


class StereoRig:
    """Both cameras' intrinsics plus the pose of camera 2 relative to camera 1.

    r and t_m follow OpenCV's stereoCalibrate convention: a point in camera
    1's frame maps to camera 2's as X2 = r @ X1 + t_m. Axes are X right,
    Y *down*, Z forward.
    """

    def __init__(self, k1, d1, k2, d2, r, t_m, image_size=EXPECTED_IMAGE_SIZE):
        self.k1 = np.asarray(k1, dtype=np.float64)
        self.d1 = np.asarray(d1, dtype=np.float64).ravel()
        self.k2 = np.asarray(k2, dtype=np.float64)
        self.d2 = np.asarray(d2, dtype=np.float64).ravel()
        self.r = np.asarray(r, dtype=np.float64)
        self.t_m = np.asarray(t_m, dtype=np.float64).ravel()
        self.image_size = tuple(image_size)

    @property
    def baseline_m(self):
        return float(np.linalg.norm(self.t_m))

    def projection_matrices(self):
        """P1, P2 for *normalised* image coordinates.

        undistortPoints already divides out K, so K must not appear here or
        the intrinsics get applied twice.
        """
        p1 = np.hstack([np.eye(3), np.zeros((3, 1))])
        p2 = np.hstack([self.r, self.t_m.reshape(3, 1)])
        return p1, p2


def _floats(nested):
    """Config numbers are stored as strings; convert without assuming shape."""
    return np.array(nested, dtype=np.float64)


def load_rig(extrinsics_path=DEFAULT_EXTRINSICS_PATH,
             config_path=DEFAULT_CONFIG_PATH):
    """Read both files and return a StereoRig in metres, OpenCV axes."""
    with open(extrinsics_path) as fh:
        ext = json.load(fh)
    with open(config_path) as fh:
        cameras = json.load(fh)["gs_config"]["cameras"]

    return StereoRig(
        k1=_floats(cameras["kCamera1CalibrationMatrix"]),
        d1=_floats(cameras["kCamera1DistortionVector"]),
        k2=_floats(cameras["kCamera2CalibrationMatrix"]),
        d2=_floats(cameras["kCamera2DistortionVector"]),
        r=_floats(ext["rotation_matrix"]),
        t_m=_floats(ext["translation_mm"]) / 1000.0,
    )


def validate_rig(rig):
    """Raise StereoRigError unless the rig is plausibly the one we measured."""
    baseline = rig.baseline_m
    if not MIN_BASELINE_M <= baseline <= MAX_BASELINE_M:
        raise StereoRigError(
            "baseline {:.4f} m is outside {:.2f}-{:.2f} m. A wrong square size "
            "scales this linearly - check --square-mm matched the printed "
            "board.".format(baseline, MIN_BASELINE_M, MAX_BASELINE_M))

    cos_angle = (np.trace(rig.r) - 1.0) / 2.0
    angle_deg = np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0)))
    if angle_deg > MAX_RELATIVE_ROTATION_DEG:
        raise StereoRigError(
            "relative rotation {:.2f} deg exceeds {:.1f} deg. The mount is "
            "bolted solid and measured under 1 deg, so this is a wrong or "
            "swapped extrinsics file.".format(angle_deg, MAX_RELATIVE_ROTATION_DEG))

    for label, k in (("camera 1", rig.k1), ("camera 2", rig.k2)):
        fx = k[0, 0]
        if abs(fx - NOMINAL_FX_PX) > FX_TOLERANCE_FRACTION * NOMINAL_FX_PX:
            raise StereoRigError(
                "{} fx = {:.1f} px, more than {:.0f}% from the measured {:.0f}. "
                "Intrinsics and extrinsics must come from the same solve; this "
                "looks like a different source.".format(
                    label, fx, FX_TOLERANCE_FRACTION * 100, NOMINAL_FX_PX))

    if rig.image_size != EXPECTED_IMAGE_SIZE:
        raise StereoRigError(
            "image size {} is not the {} the intrinsics were solved at".format(
                rig.image_size, EXPECTED_IMAGE_SIZE))
