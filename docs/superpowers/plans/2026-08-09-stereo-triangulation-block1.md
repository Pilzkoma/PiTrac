# Stereo Triangulation Block 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the committed stereo extrinsics into a working measuring instrument in Python, and use it to measure the device's attitude against the floor and the target line.

**Architecture:** Four small modules under `sp1_vision/`, each with one responsibility. `stereo_geometry.py` is the only place frames, units and signs are converted; `triangulate.py` does the arithmetic; `ground_plane.py` fits the floor and derives attitude; `cli_triangulate.py` drives capture and analysis. A ball detector is added to the existing `frame_analysis.py` alongside `find_board`. Nothing enters the C++ runtime path in this block.

**Tech Stack:** Python 3, NumPy, OpenCV 4.5.4 (JetPack 5.1.6), `unittest`.

## Global Constraints

- **Tests use `unittest`, not pytest.** Follow `sp1_vision/tests/test_camera_paths.py`. Run from the repo root: `python3 -m unittest sp1_vision.tests.test_NAME -v`.
- **Imports are absolute:** `from sp1_vision import camera_paths`, never relative.
- **OpenCV 4.5.4.** Do not use APIs added after 4.5.4.
- **Never write to `golf_sim_config.json` or `stereo_extrinsics.json`.** Tools print numbers; a human enters them.
- **Camera binding goes through `camera_paths.device_for_camera()` / `all_devices()`.** `/dev/videoN` is not a stable identity — both modules report `UC762`.
- **Capture goes through `calibration_capture.CameraPair`.** No new capture path.
- **Units:** metres everywhere inside Python. The extrinsics file is in millimetres; that conversion happens once, in `stereo_geometry.load_rig`.
- **Frames:** OpenCV (X right, Y **down**, Z forward) inside triangulation. PiTrac (X right, Y **up**, Z forward) only at the named conversion boundary.
- Tests run on the Jetson (`brain@192.168.178.194`), which has OpenCV and NumPy. Commits made there must be pushed from the Windows box.

---

## File Structure

| File | Responsibility |
|---|---|
| `sp1_vision/frame_analysis.py` (modify) | add `find_ball`, next to the existing `find_board` |
| `sp1_vision/stereo_geometry.py` (create) | load + validate the rig; the sole frame/unit conversion point |
| `sp1_vision/triangulate.py` (create) | triangulate a point; reproject it to check |
| `sp1_vision/ground_plane.py` (create) | fit the floor plane; derive pitch, roll, yaw |
| `sp1_vision/cli_triangulate.py` (create) | capture the measurement series; analyse it |
| `sp1_vision/tests/test_stereo_geometry.py` (create) | rig loading, validation, frame conversion |
| `sp1_vision/tests/test_triangulate.py` (create) | triangulation against synthetic geometry |
| `sp1_vision/tests/test_ground_plane.py` (create) | plane fit, attitude, conditioning |
| `sp1_vision/tests/test_frame_analysis.py` (modify) | ball detection |
| `sp1_vision/triangulation_run/README.md` (create) | the capture protocol, and what came out |

---

### Task 1: Ball detection, identical in both images

The spec's hard requirement is that both images are evaluated with **the same detector and the same parameters**. A difference there is larger than every second-order effect we are choosing to ignore. One function, called twice, is how that is enforced.

**Files:**
- Modify: `sp1_vision/frame_analysis.py` (add after `find_board`, which ends at line 78)
- Test: `sp1_vision/tests/test_frame_analysis.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `find_ball(frame, min_radius=20, max_radius=70) -> (bool, tuple | None)` returning `(True, (u, v, r))` in pixels, or `(False, None)`. Mirrors `find_board`'s `(bool, payload)` shape.

- [ ] **Step 1: Write the failing test**

Add to `sp1_vision/tests/test_frame_analysis.py`:

```python
class FindBallTest(unittest.TestCase):
    """One ball, found the same way in both images of a pair."""

    def _frame_with_ball(self, cx, cy, r):
        # Dark background, bright disc - the IR-lit case the detector meets.
        frame = np.zeros((800, 1280), dtype=np.uint8)
        cv2.circle(frame, (cx, cy), r, 255, -1)
        return cv2.GaussianBlur(frame, (5, 5), 0)

    def test_finds_a_ball_near_its_true_centre(self):
        found, circle = frame_analysis.find_ball(self._frame_with_ball(700, 520, 38))
        self.assertTrue(found)
        u, v, r = circle
        self.assertAlmostEqual(u, 700, delta=3)
        self.assertAlmostEqual(v, 520, delta=3)
        self.assertAlmostEqual(r, 38, delta=5)

    def test_reports_absence_rather_than_guessing(self):
        found, circle = frame_analysis.find_ball(np.zeros((800, 1280), dtype=np.uint8))
        self.assertFalse(found)
        self.assertIsNone(circle)

    def test_accepts_colour_frames_like_find_board(self):
        gray = self._frame_with_ball(640, 400, 30)
        colour = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        self.assertTrue(frame_analysis.find_ball(colour)[0])

    def test_radius_bounds_are_honoured(self):
        # A 38 px ball must not be reported when only 50-70 px is allowed.
        found, _ = frame_analysis.find_ball(
            self._frame_with_ball(700, 520, 38), min_radius=50, max_radius=70)
        self.assertFalse(found)
```

Ensure the test file imports `cv2` and `numpy as np` at the top; add them if absent.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest sp1_vision.tests.test_frame_analysis -v`
Expected: FAIL with `AttributeError: module 'sp1_vision.frame_analysis' has no attribute 'find_ball'`

- [ ] **Step 3: Write minimal implementation**

Append to `sp1_vision/frame_analysis.py`:

```python
# A golf ball is 42.67 mm across. At fx = 900 px that is a 48 px radius at
# 40 cm, so the 35-70 cm measurement range spans roughly 55 px down to 27 px.
# The bounds below leave margin on both ends without admitting the lens
# barrel or a reflection on the floor.
BALL_MIN_RADIUS_PX = 20
BALL_MAX_RADIUS_PX = 70

# One ball is in frame, so any second detection is a false positive rather
# than a competing candidate. minDist is set wide enough that Hough cannot
# return two circles for the same ball.
BALL_MIN_SEPARATION_PX = 200


def find_ball(frame, min_radius=BALL_MIN_RADIUS_PX, max_radius=BALL_MAX_RADIUS_PX):
    """Locate the ball, returning (found, (u, v, r)) in pixels.

    Both images of a pair must be measured by this same function with the
    same parameters. The centre of a sphere's silhouette is not exactly the
    projection of its centre - it migrates outward with off-axis angle, by
    around 0.3 px at our geometry - but that bias is common to both cameras
    and largely cancels in disparity. A *difference* in how the two images
    are measured does not cancel, and is far larger. Hence one function.

    Returns (False, None) rather than a best guess when nothing is found:
    a wrong centre produces a confident, wrong 3D point, and only the
    reprojection residual would catch it.
    """
    gray = _as_gray(frame)
    gray = cv2.medianBlur(gray, 5)
    circles = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT, dp=1.0, minDist=BALL_MIN_SEPARATION_PX,
        param1=100, param2=30, minRadius=int(min_radius), maxRadius=int(max_radius),
    )
    if circles is None:
        return False, None
    # OpenCV returns candidates strongest-accumulator first.
    u, v, r = circles[0][0]
    return True, (float(u), float(v), float(r))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest sp1_vision.tests.test_frame_analysis -v`
Expected: PASS, all tests

- [ ] **Step 5: Commit**

```bash
git add sp1_vision/frame_analysis.py sp1_vision/tests/test_frame_analysis.py
git commit -m "SP1: one ball detector, used for both images of a pair"
```

---

### Task 2: Load and validate the stereo rig

**Files:**
- Create: `sp1_vision/stereo_geometry.py`
- Test: `sp1_vision/tests/test_stereo_geometry.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `class StereoRigError(ValueError)`
  - `class StereoRig` with attributes `k1, d1, k2, d2, r, t_m, image_size` (all `np.ndarray` except `image_size`, a `(width, height)` tuple), property `baseline_m -> float`, method `projection_matrices() -> (np.ndarray, np.ndarray)` returning the 3x4 pair for **normalised** coordinates.
  - `load_rig(extrinsics_path, config_path) -> StereoRig`
  - `validate_rig(rig) -> None`, raising `StereoRigError`

- [ ] **Step 1: Write the failing test**

Create `sp1_vision/tests/test_stereo_geometry.py`:

```python
"""The rig is the one place frames, units and signs are converted.

Everything here guards a failure mode that is invisible downstream: a
mismatched intrinsics source, a millimetre read as a metre, a swapped pair.
"""

import json
import os
import shutil
import tempfile
import unittest

import numpy as np

from sp1_vision import stereo_geometry


def write_extrinsics(path, translation_mm=(78.710, -0.279, -2.457), rotation=None):
    if rotation is None:
        rotation = [[0.9998768, 0.0143309, 0.0063980],
                    [-0.0144342, 0.9997613, 0.0163990],
                    [-0.0061615, -0.0164893, 0.9998451]]
    with open(path, "w") as fh:
        json.dump({
            "method": "cv.stereoCalibrate with CALIB_FIX_INTRINSIC",
            "square_mm": 24.0,
            "rms_px": 0.846,
            "baseline_mm": float(np.linalg.norm(translation_mm)),
            "translation_mm": list(translation_mm),
            "rotation_matrix": rotation,
        }, fh)


def write_config(path, fx1=900.375, fx2=899.989):
    def matrix(fx, cx, cy):
        return [[str(fx), "0.0", str(cx)], ["0.0", str(fx), str(cy)],
                ["0.0", "0.0", "1.0"]]
    with open(path, "w") as fh:
        json.dump({"gs_config": {"cameras": {
            "kCamera1CalibrationMatrix": matrix(fx1, 635.097, 420.049),
            "kCamera1DistortionVector": ["0.0086", "-0.0060", "0.0021",
                                         "-0.0024", "-0.0880"],
            "kCamera2CalibrationMatrix": matrix(fx2, 631.043, 421.086),
            "kCamera2DistortionVector": ["0.0090", "-0.0062", "0.0020",
                                         "-0.0025", "-0.0870"],
        }}}, fh)


class LoadRigTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.ext = os.path.join(self.root, "stereo_extrinsics.json")
        self.cfg = os.path.join(self.root, "golf_sim_config.json")
        write_extrinsics(self.ext)
        write_config(self.cfg)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_translation_is_converted_from_mm_to_m(self):
        rig = stereo_geometry.load_rig(self.ext, self.cfg)
        self.assertAlmostEqual(rig.t_m[0], 0.078710, places=6)
        self.assertAlmostEqual(rig.baseline_m, 0.078749, places=5)

    def test_intrinsics_are_parsed_from_strings_to_floats(self):
        rig = stereo_geometry.load_rig(self.ext, self.cfg)
        self.assertAlmostEqual(rig.k1[0, 0], 900.375, places=3)
        self.assertAlmostEqual(rig.k2[1, 2], 421.086, places=3)
        self.assertEqual(rig.d1.shape, (5,))

    def test_projection_matrices_are_for_normalised_coordinates(self):
        # P1 = [I|0] and P2 = [R|t]. Anything with K baked in would silently
        # double-apply the intrinsics after undistortPoints normalises.
        rig = stereo_geometry.load_rig(self.ext, self.cfg)
        p1, p2 = rig.projection_matrices()
        np.testing.assert_allclose(p1[:, :3], np.eye(3), atol=1e-12)
        np.testing.assert_allclose(p1[:, 3], np.zeros(3), atol=1e-12)
        np.testing.assert_allclose(p2[:, :3], rig.r, atol=1e-12)
        np.testing.assert_allclose(p2[:, 3], rig.t_m, atol=1e-12)


class ValidateRigTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.ext = os.path.join(self.root, "stereo_extrinsics.json")
        self.cfg = os.path.join(self.root, "golf_sim_config.json")
        write_config(self.cfg)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_accepts_the_real_rig(self):
        write_extrinsics(self.ext)
        stereo_geometry.validate_rig(stereo_geometry.load_rig(self.ext, self.cfg))

    def test_rejects_a_baseline_that_means_the_wrong_square_size(self):
        # A 20 mm board assumed against a 24 mm print gave 66.40 mm once
        # already. That is a wrong answer, not a noisy one.
        write_extrinsics(self.ext, translation_mm=(66.40, 0.0, 0.0))
        with self.assertRaises(stereo_geometry.StereoRigError):
            stereo_geometry.validate_rig(stereo_geometry.load_rig(self.ext, self.cfg))

    def test_rejects_a_rotation_far_from_identity(self):
        theta = np.radians(20.0)
        write_extrinsics(self.ext, rotation=[
            [np.cos(theta), 0.0, np.sin(theta)],
            [0.0, 1.0, 0.0],
            [-np.sin(theta), 0.0, np.cos(theta)]])
        with self.assertRaises(stereo_geometry.StereoRigError):
            stereo_geometry.validate_rig(stereo_geometry.load_rig(self.ext, self.cfg))

    def test_rejects_intrinsics_from_a_different_source(self):
        # Extrinsics solved with CALIB_FIX_INTRINSIC absorb the intrinsics'
        # error into R and T. Pairing them with other intrinsics is the one
        # combination that is definitely wrong and looks fine in the RMS.
        write_extrinsics(self.ext)
        write_config(self.cfg, fx1=1400.0)
        with self.assertRaises(stereo_geometry.StereoRigError):
            stereo_geometry.validate_rig(stereo_geometry.load_rig(self.ext, self.cfg))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest sp1_vision.tests.test_stereo_geometry -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sp1_vision.stereo_geometry'`

- [ ] **Step 3: Write minimal implementation**

Create `sp1_vision/stereo_geometry.py`:

```python
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
# CORRECTION found during implementation (2026-08-09): these two values are
# WRONG as written here. 0.05-0.12 m does not reject this task's own test
# case of 66.40 mm - the baseline a 20 mm square size produces against the
# 24 mm board actually used - so the bound fails at the one job it exists
# for. The shipped values are 0.070 / 0.090 m, which still leave ample margin
# around the measured 78.7 mm (subset spread 77.99-78.66 mm). Read the code.
MIN_BASELINE_M = 0.05        # a wrong square size scales the baseline outright
MAX_BASELINE_M = 0.12
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest sp1_vision.tests.test_stereo_geometry -v`
Expected: PASS, all tests

- [ ] **Step 5: Commit**

```bash
git add sp1_vision/stereo_geometry.py sp1_vision/tests/test_stereo_geometry.py
git commit -m "SP1: load the stereo rig, in metres, and refuse a wrong one"
```

---

### Task 3: The frame conversion, and the camera-2 offset

This is the single most likely place in the whole task for a silent sign error, which is why it gets its own review gate rather than riding along with Task 2.

**Files:**
- Modify: `sp1_vision/stereo_geometry.py` (append)
- Test: `sp1_vision/tests/test_stereo_geometry.py` (append)

**Interfaces:**
- Consumes: `StereoRig` from Task 2.
- Produces:
  - `to_pitrac_frame(xyz) -> np.ndarray` — OpenCV (Y down) to PiTrac (Y up)
  - `camera2_centre_in_camera1(rig) -> np.ndarray` — metres, OpenCV axes
  - `camera2_offset_from_camera1(rig) -> np.ndarray` — metres, **PiTrac** axes; the value for `kCamera2OffsetFromCamera1OriginMeters`

- [ ] **Step 1: Write the failing test**

Append to `sp1_vision/tests/test_stereo_geometry.py`:

```python
class FrameConversionTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.ext = os.path.join(self.root, "stereo_extrinsics.json")
        self.cfg = os.path.join(self.root, "golf_sim_config.json")
        write_extrinsics(self.ext)
        write_config(self.cfg)
        self.rig = stereo_geometry.load_rig(self.ext, self.cfg)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_pitrac_frame_negates_y_and_nothing_else(self):
        # gs_camera.cpp:1157 - "Y distance, positive is upward". The
        # extrinsics are Y down. Getting this backwards inverts launch angle.
        np.testing.assert_allclose(
            stereo_geometry.to_pitrac_frame([1.0, 2.0, 3.0]),
            [1.0, -2.0, 3.0], atol=1e-12)

    def test_pitrac_frame_is_its_own_inverse(self):
        there = stereo_geometry.to_pitrac_frame([0.1, -0.2, 0.3])
        np.testing.assert_allclose(
            stereo_geometry.to_pitrac_frame(there), [0.1, -0.2, 0.3], atol=1e-12)

    def test_camera2_sits_left_of_camera1_in_the_cameras_own_frame(self):
        # T_x is +78.7 mm, which is camera 1's origin seen from camera 2. So
        # camera 2 is at NEGATIVE x in camera 1's frame. Reading the positive
        # T_x as "camera 1 is on the right" is the trap; the unit's frame and
        # the player's are mirrored, and camera 1 is the player's left module.
        centre = stereo_geometry.camera2_centre_in_camera1(self.rig)
        self.assertLess(centre[0], 0.0)
        self.assertAlmostEqual(centre[0], -0.078720, places=5)
        self.assertAlmostEqual(np.linalg.norm(centre), self.rig.baseline_m, places=9)

    def test_camera2_offset_matches_the_hand_computed_value(self):
        # -R.T @ t, then Y negated for PiTrac. The rotation matters here: a
        # plain -t gets the small components wrong by more than a factor of
        # two, which is the argument for computing rather than typing it.
        offset = stereo_geometry.camera2_offset_from_camera1(self.rig)
        np.testing.assert_allclose(
            offset, [-0.078720, 0.000890, 0.001957], atol=2e-6)

    def test_offset_replaces_pitracs_vertical_stacking(self):
        # PiTrac ships [0, -0.19, 0] - their cameras sit 19 cm apart
        # vertically. Ours are side by side; the dominant term must be X.
        offset = stereo_geometry.camera2_offset_from_camera1(self.rig)
        self.assertGreater(abs(offset[0]), 20 * abs(offset[1]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest sp1_vision.tests.test_stereo_geometry -v`
Expected: FAIL with `AttributeError: module 'sp1_vision.stereo_geometry' has no attribute 'to_pitrac_frame'`

- [ ] **Step 3: Write minimal implementation**

Append to `sp1_vision/stereo_geometry.py`:

```python
# OpenCV's camera frame is X right, Y down, Z forward - right-handed.
# PiTrac's camera-perspective frame is X right, Y *up*, Z forward
# (gs_camera.cpp:1132 and :1157, "positive is upward") - left-handed. The
# cross-check is PiTrac's own kCamera2OffsetFromCamera1OriginMeters of
# [0, -0.19, 0]: their camera 2 sits 19 cm BELOW camera 1, and a negative Y
# only means below if Y is up.
#
# Negating one axis flips handedness, which is why this is a conversion and
# not a relabelling.
_PITRAC_Y_FLIP = np.diag([1.0, -1.0, 1.0])


def to_pitrac_frame(xyz):
    """Convert an OpenCV-frame vector to PiTrac's Y-up frame, or back.

    The operation is its own inverse, so one function serves both directions.
    """
    return _PITRAC_Y_FLIP @ np.asarray(xyz, dtype=np.float64).ravel()


def camera2_centre_in_camera1(rig):
    """Camera 2's optical centre in camera 1's frame, metres, OpenCV axes.

    stereoCalibrate gives X2 = R @ X1 + T, so T is camera 1's origin seen
    from camera 2. Setting X2 = 0 and solving gives the centre below.

    Our T_x is positive, which puts this at negative x: camera 2 is to
    camera 1's left as the unit looks out. A golfer faces the unit and sees
    that mirrored, so camera 1 is the player's LEFT module - confirmed
    independently by the two physical experiments in camera_paths.py.
    """
    return -rig.r.T @ rig.t_m


def camera2_offset_from_camera1(rig):
    """The value for kCamera2OffsetFromCamera1OriginMeters, in metres.

    PiTrac ships [0.00, -0.19, 0.0] - 19 cm of vertical camera stacking that
    our side-by-side mount does not have. Computed from R and T rather than
    typed: dropping the rotation and using -T alone gets the Y and Z
    components wrong by more than a factor of two.
    """
    return to_pitrac_frame(camera2_centre_in_camera1(rig))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest sp1_vision.tests.test_stereo_geometry -v`
Expected: PASS, all tests

- [ ] **Step 5: Commit**

```bash
git add sp1_vision/stereo_geometry.py sp1_vision/tests/test_stereo_geometry.py
git commit -m "SP1: the Y-up conversion, and camera 2's offset computed not typed"
```

---

### Task 4: Triangulation, and the reprojection check

**Files:**
- Create: `sp1_vision/triangulate.py`
- Test: `sp1_vision/tests/test_triangulate.py`

**Interfaces:**
- Consumes: `StereoRig`, `stereo_geometry.load_rig` from Task 2.
- Produces:
  - `class TriangulationError(ValueError)`
  - `triangulate_point(rig, uv1, uv2) -> np.ndarray` — XYZ in camera 1's frame, metres, OpenCV axes
  - `reprojection_error(rig, xyz_m, uv1, uv2) -> (float, float)` — pixel residuals in camera 1 and camera 2
  - `depth_sensitivity_mm_per_px(rig, depth_m) -> float`

- [ ] **Step 1: Write the failing test**

Create `sp1_vision/tests/test_triangulate.py`:

```python
"""Triangulation against synthetic geometry, where truth is known exactly.

Testing against real images would confound the arithmetic with detection
error. Here a known 3D point is projected into two known cameras and must
come back.
"""

import unittest

import cv2
import numpy as np

from sp1_vision import stereo_geometry, triangulate


def make_rig(camera2_centre_m=(-0.07872, 0.0, 0.0), pitch_deg=0.0,
             distortion=None):
    """A rig with camera 2 placed where we say, in camera 1's frame.

    Placing the CENTRE rather than T keeps the test readable: T = -R @ centre
    is exactly the conversion the production code has to get right, so
    stating it here in the opposite direction is a genuine cross-check.
    """
    k = np.array([[900.0, 0.0, 640.0],
                  [0.0, 900.0, 400.0],
                  [0.0, 0.0, 1.0]])
    d = np.zeros(5) if distortion is None else np.asarray(distortion, float)
    r, _ = cv2.Rodrigues(np.array([np.radians(pitch_deg), 0.0, 0.0]))
    centre = np.asarray(camera2_centre_m, dtype=float)
    t = -r @ centre
    return stereo_geometry.StereoRig(k1=k, d1=d, k2=k, d2=d, r=r, t_m=t)


def project(rig, xyz):
    """Where a camera-1-frame point lands in each image."""
    xyz = np.asarray(xyz, dtype=float).reshape(1, 3)
    zero = np.zeros(3)
    uv1, _ = cv2.projectPoints(xyz, zero, zero, rig.k1, rig.d1)
    rvec, _ = cv2.Rodrigues(rig.r)
    uv2, _ = cv2.projectPoints(xyz, rvec, rig.t_m, rig.k2, rig.d2)
    return uv1.reshape(2), uv2.reshape(2)


class TriangulateTest(unittest.TestCase):
    def test_recovers_a_known_point_exactly(self):
        rig = make_rig()
        truth = np.array([0.05, 0.0937, 0.500])
        xyz = triangulate.triangulate_point(rig, *project(rig, truth))
        np.testing.assert_allclose(xyz, truth, atol=1e-9)

    def test_recovers_a_known_point_through_lens_distortion(self):
        rig = make_rig(distortion=[0.0086, -0.0060, 0.0021, -0.0024, -0.0880])
        truth = np.array([-0.08, 0.05, 0.42])
        xyz = triangulate.triangulate_point(rig, *project(rig, truth))
        np.testing.assert_allclose(xyz, truth, atol=1e-7)

    def test_recovers_a_known_point_with_the_pair_rotated(self):
        rig = make_rig(pitch_deg=-0.94)
        truth = np.array([0.02, 0.09, 0.65])
        xyz = triangulate.triangulate_point(rig, *project(rig, truth))
        np.testing.assert_allclose(xyz, truth, atol=1e-9)

    def test_depth_is_positive_for_a_point_in_front(self):
        # A swapped pair or an inverted T produces mirrored depth with
        # nothing else visibly wrong. Depth sign is the cheapest guard.
        rig = make_rig()
        xyz = triangulate.triangulate_point(rig, *project(rig, [0.0, 0.0, 0.5]))
        self.assertGreater(xyz[2], 0.0)

    def test_swapped_correspondences_are_caught_by_reprojection(self):
        rig = make_rig()
        truth = np.array([0.05, 0.0937, 0.500])
        uv1, uv2 = project(rig, truth)
        # Feed the images in the wrong order - a plausible wiring mistake.
        xyz = triangulate.triangulate_point(rig, uv2, uv1)
        e1, e2 = triangulate.reprojection_error(rig, xyz, uv2, uv1)
        self.assertGreater(max(e1, e2), 1.0)


class ReprojectionErrorTest(unittest.TestCase):
    def test_a_true_point_reprojects_onto_its_own_measurements(self):
        rig = make_rig()
        truth = np.array([0.05, 0.0937, 0.500])
        uv1, uv2 = project(rig, truth)
        e1, e2 = triangulate.reprojection_error(rig, truth, uv1, uv2)
        self.assertLess(max(e1, e2), 1e-6)

    def test_a_displaced_point_shows_a_residual(self):
        rig = make_rig()
        truth = np.array([0.05, 0.0937, 0.500])
        uv1, uv2 = project(rig, truth)
        e1, e2 = triangulate.reprojection_error(rig, truth + [0.01, 0, 0], uv1, uv2)
        self.assertGreater(max(e1, e2), 1.0)


class DepthSensitivityTest(unittest.TestCase):
    def test_matches_the_hand_computed_figure_at_the_working_distance(self):
        # Z^2 / (b * f) = 0.5087^2 / (0.07872 * 900) = 3.65 mm per pixel.
        # CORRECTION 2026-08-10: this is a correct unit test of the
        # arithmetic, but 0.5087 m is the straight-line RANGE to the ball,
        # not its depth. The formula takes depth. Our working depth is the
        # 500 mm horizontal leg, giving 3.53 mm/px - see the spec.
        rig = make_rig()
        self.assertAlmostEqual(
            triangulate.depth_sensitivity_mm_per_px(rig, 0.5087), 3.65, delta=0.05)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest sp1_vision.tests.test_triangulate -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sp1_vision.triangulate'`

- [ ] **Step 3: Write minimal implementation**

Create `sp1_vision/triangulate.py`:

```python
#!/usr/bin/env python3
"""Two image points in, one 3D point out - plus the check that it is real.

The reprojection residual returned alongside is not decoration. It catches
swapped images, an inverted translation and a mis-detected ball, all of
which otherwise produce a confident number that is simply wrong.

It is necessary and not sufficient. A small residual means the two rays
intersect; it says nothing about scale. Scale comes from the baseline, and
the baseline is checked against a tape measure, not against this.
"""

import cv2
import numpy as np


class TriangulationError(ValueError):
    """The two rays do not yield a finite point."""


def triangulate_point(rig, uv1, uv2):
    """Return the 3D point in camera 1's frame, metres, OpenCV axes.

    uv1 and uv2 are distorted pixel coordinates, straight from the detector.
    """
    def normalise(uv, k, d):
        pts = np.array([[[float(uv[0]), float(uv[1])]]], dtype=np.float64)
        return cv2.undistortPoints(pts, k, d).reshape(2, 1)

    n1 = normalise(uv1, rig.k1, rig.d1)
    n2 = normalise(uv2, rig.k2, rig.d2)

    p1, p2 = rig.projection_matrices()
    homogeneous = cv2.triangulatePoints(p1, p2, n1, n2)

    w = homogeneous[3, 0]
    if not np.isfinite(w) or abs(w) < 1e-12:
        raise TriangulationError(
            "degenerate triangulation for {} / {}: the rays are parallel, "
            "which usually means the same point was fed twice".format(uv1, uv2))
    return (homogeneous[:3, 0] / w).astype(np.float64)


def reprojection_error(rig, xyz_m, uv1, uv2):
    """Pixel residuals in camera 1 and camera 2 for a solved point."""
    xyz = np.asarray(xyz_m, dtype=np.float64).reshape(1, 3)
    zero = np.zeros(3)

    proj1, _ = cv2.projectPoints(xyz, zero, zero, rig.k1, rig.d1)
    rvec, _ = cv2.Rodrigues(rig.r)
    proj2, _ = cv2.projectPoints(xyz, rvec, rig.t_m, rig.k2, rig.d2)

    e1 = float(np.linalg.norm(proj1.reshape(2) - np.asarray(uv1, dtype=np.float64)))
    e2 = float(np.linalg.norm(proj2.reshape(2) - np.asarray(uv2, dtype=np.float64)))
    return e1, e2


def depth_sensitivity_mm_per_px(rig, depth_m):
    """How much depth error one pixel of disparity error buys, in mm.

    Z^2 / (b * f). CORRECTION 2026-08-10: the figure at the 50 cm working
    DEPTH is 3.53 mm/px. The 3.65 below came from substituting the 508.7 mm
    range, which is the wrong quantity for this formula. Read the shipped
    docstring, not this.
    Z^2 / (b * f). At the 50 cm working distance this is about 3.65 mm per
    pixel, so roughly 1.8 mm at half-pixel detection - the figure that sets
    what counts as agreement with a tape measure.
    """
    fx = float(rig.k1[0, 0])
    return 1000.0 * (float(depth_m) ** 2) / (rig.baseline_m * fx)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest sp1_vision.tests.test_triangulate -v`
Expected: PASS, all tests

- [ ] **Step 5: Commit**

```bash
git add sp1_vision/triangulate.py sp1_vision/tests/test_triangulate.py
git commit -m "SP1: triangulate a point, and reproject it to see if it is real"
```

---

### Task 5: The floor plane, and the device's attitude

**Files:**
- Create: `sp1_vision/ground_plane.py`
- Test: `sp1_vision/tests/test_ground_plane.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure geometry on arrays).
- Produces:
  - `class PlaneFitError(ValueError)`
  - `class PlaneFit` with attributes `normal` (unit, oriented up in camera frame, so `normal[1] < 0`), `centroid`, `residuals_m`, `rms_m`, `conditioning`
  - `fit_plane(points_m) -> PlaneFit`
  - `attitude_from_plane(plane) -> (pitch_deg, roll_deg)`
  - `yaw_from_target_line(plane, near_m, far_m) -> float`

- [ ] **Step 1: Write the failing test**

Create `sp1_vision/tests/test_ground_plane.py`:

```python
"""The floor, fitted - and the two things it can and cannot tell us.

A plane gives pitch and roll. It cannot give yaw: a plane is rotationally
symmetric about its normal, so yaw needs the target-line pair.
"""

import unittest

import numpy as np

from sp1_vision import ground_plane


def floor_points(pitch_deg=0.0, roll_deg=0.0, n_x=4, n_z=3):
    """Ball centres on a floor seen by a camera at the given attitude.

    Camera frame: X right, Y down, Z forward. A level camera sees the floor
    below it, so the plane's normal is -Y.
    """
    xs = np.linspace(-0.25, 0.25, n_x)
    zs = np.linspace(0.35, 0.70, n_z)
    pts = np.array([[x, 0.0937, z] for z in zs for x in xs])

    p = np.radians(pitch_deg)
    rx = np.array([[1, 0, 0],
                   [0, np.cos(p), -np.sin(p)],
                   [0, np.sin(p), np.cos(p)]])
    q = np.radians(roll_deg)
    rz = np.array([[np.cos(q), -np.sin(q), 0],
                   [np.sin(q), np.cos(q), 0],
                   [0, 0, 1]])
    return pts @ (rz @ rx).T


class FitPlaneTest(unittest.TestCase):
    def test_level_floor_has_an_upward_normal(self):
        plane = ground_plane.fit_plane(floor_points())
        np.testing.assert_allclose(plane.normal, [0.0, -1.0, 0.0], atol=1e-9)
        self.assertLess(plane.rms_m, 1e-9)

    def test_normal_is_always_oriented_upward(self):
        # SVD returns a normal of arbitrary sign. Left alone, half the runs
        # would report the pitch negated.
        for pitch in (-2.0, 2.0):
            plane = ground_plane.fit_plane(floor_points(pitch_deg=pitch))
            self.assertLess(plane.normal[1], 0.0)

    def test_reports_residuals_for_a_noisy_floor(self):
        pts = floor_points()
        pts[3, 1] += 0.004
        plane = ground_plane.fit_plane(pts)
        self.assertGreater(plane.rms_m, 1e-4)

    def test_refuses_a_near_collinear_set(self):
        # Points along one line fit a plane beautifully and determine
        # nothing. The residual will not show it; conditioning does. This is
        # the same failure that left cy unconstrained at an RMS of 0.90.
        collinear = np.array([[0.0, 0.0937, z] for z in np.linspace(0.35, 0.7, 6)])
        with self.assertRaises(ground_plane.PlaneFitError):
            ground_plane.fit_plane(collinear)

    def test_refuses_fewer_than_three_points(self):
        with self.assertRaises(ground_plane.PlaneFitError):
            ground_plane.fit_plane(np.array([[0.0, 0.09, 0.4], [0.1, 0.09, 0.5]]))


class AttitudeTest(unittest.TestCase):
    def test_level_device_reads_zero(self):
        pitch, roll = ground_plane.attitude_from_plane(
            ground_plane.fit_plane(floor_points()))
        self.assertAlmostEqual(pitch, 0.0, places=6)
        self.assertAlmostEqual(roll, 0.0, places=6)

    def test_recovers_pitch(self):
        pitch, roll = ground_plane.attitude_from_plane(
            ground_plane.fit_plane(floor_points(pitch_deg=1.7)))
        self.assertAlmostEqual(pitch, 1.7, places=3)
        self.assertAlmostEqual(roll, 0.0, places=3)

    def test_recovers_roll(self):
        pitch, roll = ground_plane.attitude_from_plane(
            ground_plane.fit_plane(floor_points(roll_deg=-1.1)))
        self.assertAlmostEqual(pitch, 0.0, places=3)
        self.assertAlmostEqual(roll, -1.1, places=3)

    def test_recovers_both_together(self):
        pitch, roll = ground_plane.attitude_from_plane(
            ground_plane.fit_plane(floor_points(pitch_deg=-0.9, roll_deg=0.8)))
        self.assertAlmostEqual(pitch, -0.9, places=2)
        self.assertAlmostEqual(roll, 0.8, places=2)


class YawTest(unittest.TestCase):
    def test_target_line_straight_ahead_reads_zero(self):
        plane = ground_plane.fit_plane(floor_points())
        yaw = ground_plane.yaw_from_target_line(
            plane, [0.0, 0.0937, 0.40], [0.0, 0.0937, 0.70])
        self.assertAlmostEqual(yaw, 0.0, places=6)

    def test_target_line_swung_right_reads_positive(self):
        plane = ground_plane.fit_plane(floor_points())
        yaw = ground_plane.yaw_from_target_line(
            plane, [0.0, 0.0937, 0.40], [0.10, 0.0937, 0.70])
        self.assertAlmostEqual(yaw, np.degrees(np.arctan2(0.10, 0.30)), places=4)

    def test_two_coincident_points_are_refused(self):
        plane = ground_plane.fit_plane(floor_points())
        with self.assertRaises(ground_plane.PlaneFitError):
            ground_plane.yaw_from_target_line(
                plane, [0.0, 0.0937, 0.40], [0.0, 0.0937, 0.40])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest sp1_vision.tests.test_ground_plane -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sp1_vision.ground_plane'`

- [ ] **Step 3: Write minimal implementation**

Create `sp1_vision/ground_plane.py`:

```python
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

    With the camera level the floor normal is exactly (0, -1, 0). Pitching
    the camera up by theta rotates it to (0, -cos, +sin), and rolling by phi
    to (+sin, -cos, 0), so the two angles read straight off the normal.
    Positive pitch is nose-up; positive roll follows the camera's Z axis.

    Yaw is absent on purpose - see yaw_from_target_line.
    """
    n = plane.normal
    pitch_deg = float(np.degrees(np.arcsin(np.clip(n[2], -1.0, 1.0))))
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest sp1_vision.tests.test_ground_plane -v`
Expected: PASS, all tests

- [ ] **Step 5: Commit**

```bash
git add sp1_vision/ground_plane.py sp1_vision/tests/test_ground_plane.py
git commit -m "SP1: fit the floor, and read pitch and roll off its normal"
```

---

### Task 6: Capture the measurement series

Tape distances and the target-line flag are prompted for **at capture time** and written next to the images. Recording them afterwards invites transcription errors, and the target-line positions in particular cannot be identified after the fact — a floor-only series simply cannot yield yaw, and the run would have to be repeated.

**Files:**
- Create: `sp1_vision/cli_triangulate.py`
- Test: none. This step is interactive and hardware-bound; its logic is the prompting, and the analysis half in Task 7 is where the testable arithmetic lives.

**Interfaces:**
- Consumes: `calibration_capture.CameraPair`, `frame_analysis.find_ball` (Task 1).
- Produces: a run directory containing `cam1/gs_NN.png`, `cam2/gs_NN.png` and `run.json` with the shape:
  ```json
  {"shots": [{"name": "gs_01.png", "tape_mm": 350.0, "series": "depth"}]}
  ```
  `series` is exactly one of `"depth"`, `"spread"` or `"target"`, and the three
  are consumed differently in Task 7 — the plane takes `depth` and `spread`,
  the scale fit takes `depth` alone, yaw takes `target`. A plain
  floor/target-line boolean is not enough: the scale fit compares 3D distance
  against a difference of two tape readings, and that identity only holds for
  positions on one line. Mixing a laterally offset `spread` shot into it
  compares a ~250 mm displacement against a ~10 mm tape difference and
  destroys the fit rather than merely biasing it.

- [ ] **Step 1: Write the capture half**

Create `sp1_vision/cli_triangulate.py`:

```python
#!/usr/bin/env python3
"""Capture and analyse a triangulation measurement series.

Capture:  python3 -m sp1_vision.cli_triangulate --shots 12 --out RUNDIR
Analyse:  python3 -m sp1_vision.cli_triangulate --analyse RUNDIR

The series measures three things at once, which is why it is one series and
not three:

  * whether triangulation agrees with a tape measure at all;
  * how the device sits against the floor, which nothing has ever measured;
  * which baseline is right, 78.28 mm or the 78.749 in the extrinsics file.

The suggested layout, 12 shots:

  depth   6 positions along a straight line running directly away from the
          unit, tape-measured, e.g. 350 / 420 / 490 / 560 / 630 / 700 mm.
          Consecutive gaps are known precisely, which is what settles the
          baseline - measuring DIFFERENCES isolates scale from any error in
          where the lens plane sits. These must be collinear: the scale fit
          equates 3D distance with a difference of tape readings, and that
          only holds along one line.
  spread  4 positions off to the sides at assorted distances. They do nothing
          for scale and everything for the plane: without spread across the
          image width the floor fit is undetermined, however small its
          residual.
  target  2 positions along the intended target line. The floor plane cannot
          give yaw - it is rotationally symmetric about its own normal - and
          this pair is the only thing that can. It cannot be added afterwards
          without repeating the run.
"""

import argparse
import json
import os
import sys
import time

import cv2

from sp1_vision import calibration_capture, frame_analysis

RUN_MANIFEST = "run.json"


def _ask_float(prompt):
    while True:
        raw = input(prompt).strip()
        try:
            return float(raw)
        except ValueError:
            print("  need a number, e.g. 420.5")


SERIES = {"d": "depth", "s": "spread", "t": "target"}


def _ask_series():
    """Which of the three series this position belongs to.

    Asked rather than inferred because the three are consumed differently and
    no amount of after-the-fact geometry recovers the distinction reliably.
    """
    while True:
        raw = input("  series - [d]epth line / [s]pread / [t]arget line: ")
        key = raw.strip().lower()[:1]
        if key in SERIES:
            return SERIES[key]
        print("  answer d, s or t")


def run_shots(count, out_dir, exposure_units):
    dirs = {n: os.path.join(out_dir, "cam{}".format(n)) for n in (1, 2)}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)

    manifest_path = os.path.join(out_dir, RUN_MANIFEST)
    shots = []
    if os.path.exists(manifest_path):
        with open(manifest_path) as fh:
            shots = json.load(fh)["shots"]
        print("{} shots already in {} - new ones are numbered after them."
              .format(len(shots), out_dir))

    print(__doc__)
    with calibration_capture.CameraPair(exposure_units=exposure_units) as pair:
        for i in range(len(shots) + 1, len(shots) + count + 1):
            name = "gs_{:02d}.png".format(i)
            print("\n--- shot {} ---".format(i))
            tape_mm = _ask_float("  tape distance to the lens plane, mm: ")
            series = _ask_series()
            input("  place the ball, stand clear, press Enter: ")

            frames, skew = pair.grab_with_skew()
            found = {}
            for n, frame in frames.items():
                found[n], _ = frame_analysis.find_ball(frame)
                cv2.imwrite(os.path.join(dirs[n], name), frame)

            both = found[1] and found[2]
            print("  cam1 {}  cam2 {}  skew {:.1f} ms  -> {}".format(
                "ball" if found[1] else " --  ",
                "ball" if found[2] else " --  ",
                skew * 1000.0,
                "keep" if both else "MOVE THE BALL AND RETAKE"))

            shots.append({"name": name, "tape_mm": tape_mm, "series": series})
            with open(manifest_path, "w") as fh:
                json.dump({"shots": shots}, fh, indent=2)

    counts = {label: sum(1 for s in shots if s["series"] == label)
              for label in sorted(set(SERIES.values()))}
    print("\n{} shots on disk: {}".format(
        len(shots),
        ", ".join("{} {}".format(v, k) for k, v in sorted(counts.items()))))

    short = []
    if counts["target"] < 2:
        short.append("yaw needs 2 target-line positions and cannot be "
                     "recovered later from a floor-only series")
    if counts["depth"] < 4:
        short.append("the scale fit needs 4+ collinear depth positions")
    if counts["depth"] + counts["spread"] < 3:
        short.append("the floor plane needs 3+ positions")
    for line in short:
        print("INCOMPLETE: " + line)
    return 1 if short else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shots", type=int, metavar="N",
                        help="capture N ball positions, prompting for each")
    parser.add_argument("--out", default="sp1_vision/triangulation_run",
                        help="run directory for --shots (default: %(default)s)")
    parser.add_argument("--exposure", type=int, metavar="N",
                        help="manual exposure in 100 us units (1-5000); "
                             "omit for auto")
    args = parser.parse_args(argv)

    if args.shots:
        return run_shots(args.shots, args.out, args.exposure)
    parser.error("give --shots N")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify the CLI parses and refuses an empty invocation**

Run: `python3 -m sp1_vision.cli_triangulate`
Expected: exits non-zero with `error: give --shots N`

Run: `python3 -m sp1_vision.cli_triangulate --help`
Expected: the docstring, including the depth / spread / target layout

- [ ] **Step 3: Commit**

```bash
git add sp1_vision/cli_triangulate.py
git commit -m "SP1: capture a triangulation series, tape and target line recorded live"
```

---

### Task 7: Analyse the series

**Files:**
- Modify: `sp1_vision/cli_triangulate.py` (add `run_analysis`, wire `--analyse`)
- Test: `sp1_vision/tests/test_triangulate.py` (append the scale-fit test)

**Interfaces:**
- Consumes: `stereo_geometry.load_rig`, `validate_rig`, `camera2_offset_from_camera1`; `triangulate.triangulate_point`, `reprojection_error`; `ground_plane.fit_plane`, `attitude_from_plane`, `yaw_from_target_line`; `frame_analysis.find_ball`.
- Produces: `triangulate.fit_scale_factor(measured_m, tape_m) -> (float, float)` returning `(scale, rms_residual_m)`.

- [ ] **Step 1: Write the failing test for the scale fit**

Append to `sp1_vision/tests/test_triangulate.py`:

```python
class ScaleFactorTest(unittest.TestCase):
    """Does the triangulated world match the tape's, in size?

    Fitted on DIFFERENCES between positions, never on absolute distances -
    the lens plane's exact location is a guess, and a constant offset in it
    would masquerade as a scale error.
    """

    def test_perfect_agreement_gives_unit_scale(self):
        tape = np.array([0.070, 0.070, 0.070, 0.070, 0.070])
        scale, rms = triangulate.fit_scale_factor(tape, tape)
        self.assertAlmostEqual(scale, 1.0, places=9)
        self.assertLess(rms, 1e-12)

    def test_recovers_a_known_scale_error(self):
        # 78.28 against 78.749 mm of baseline is 0.6%, and a baseline that is
        # 0.6% too large makes every triangulated distance 0.6% too large.
        tape = np.array([0.070, 0.070, 0.070, 0.070, 0.070, 0.070])
        measured = tape * 1.006
        scale, rms = triangulate.fit_scale_factor(measured, tape)
        self.assertAlmostEqual(scale, 1.006, places=6)
        self.assertLess(rms, 1e-9)

    def test_noise_shows_up_in_the_residual_not_the_scale(self):
        tape = np.full(6, 0.070)
        measured = tape + np.array([0.001, -0.001, 0.0008, -0.0009, 0.0, 0.0011])
        scale, rms = triangulate.fit_scale_factor(measured, tape)
        self.assertAlmostEqual(scale, 1.0, delta=0.01)
        self.assertGreater(rms, 1e-5)

    def test_refuses_mismatched_lengths(self):
        with self.assertRaises(ValueError):
            triangulate.fit_scale_factor(np.array([0.07]), np.array([0.07, 0.07]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest sp1_vision.tests.test_triangulate -v`
Expected: FAIL with `AttributeError: module 'sp1_vision.triangulate' has no attribute 'fit_scale_factor'`

- [ ] **Step 3: Implement the scale fit**

Append to `sp1_vision/triangulate.py`:

```python
def fit_scale_factor(measured_m, tape_m):
    """Least-squares scale between triangulated and tape distances.

    Returns (scale, rms_residual_m). A scale of 1.006 means the triangulated
    world is 0.6% too large, which is what a baseline 0.6% too large would
    produce - the 78.28 against 78.749 question, answered by measurement.

    Both inputs must be DIFFERENCES between positions, not distances from
    the camera. Where exactly the lens plane sits is a guess, and a constant
    error in it would read as a scale error if absolute distances were used.
    """
    measured = np.asarray(measured_m, dtype=np.float64).ravel()
    tape = np.asarray(tape_m, dtype=np.float64).ravel()
    if measured.shape != tape.shape:
        raise ValueError(
            "measured and tape must be the same length, got {} and {}".format(
                measured.shape, tape.shape))
    if measured.size == 0:
        raise ValueError("no displacements to fit a scale from")

    denominator = float(np.dot(tape, tape))
    if denominator <= 0.0:
        raise ValueError("tape displacements are all zero")

    scale = float(np.dot(measured, tape) / denominator)
    residuals = measured - scale * tape
    return scale, float(np.sqrt(np.mean(residuals ** 2)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest sp1_vision.tests.test_triangulate -v`
Expected: PASS, all tests

- [ ] **Step 5: Add the analysis command**

Insert into `sp1_vision/cli_triangulate.py`, above `main`:

```python
# A residual above this means the two rays did not really meet, so the point
# is not evidence about anything. Half a pixel is detection noise; two
# pixels is a mis-detection or a wrong correspondence.
MAX_REPROJECTION_PX = 2.0


def _measure_shot(rig, run_dir, shot):
    """Return (xyz_m, worst_reprojection_px) or (None, reason)."""
    frames = {}
    for n in (1, 2):
        path = os.path.join(run_dir, "cam{}".format(n), shot["name"])
        frame = cv2.imread(path)
        if frame is None:
            return None, "missing {}".format(path)
        frames[n] = frame

    circles = {}
    for n, frame in frames.items():
        found, circle = frame_analysis.find_ball(frame)
        if not found:
            return None, "no ball in cam{}".format(n)
        circles[n] = circle

    uv1 = circles[1][:2]
    uv2 = circles[2][:2]
    xyz = triangulate.triangulate_point(rig, uv1, uv2)
    e1, e2 = triangulate.reprojection_error(rig, xyz, uv1, uv2)
    return xyz, max(e1, e2)


def run_analysis(run_dir, extrinsics_path, config_path):
    rig = stereo_geometry.load_rig(extrinsics_path, config_path)
    stereo_geometry.validate_rig(rig)
    print("rig: baseline {:.3f} mm, fx {:.1f} / {:.1f}".format(
        rig.baseline_m * 1000.0, rig.k1[0, 0], rig.k2[0, 0]))

    with open(os.path.join(run_dir, RUN_MANIFEST)) as fh:
        shots = json.load(fh)["shots"]

    print("\n{:<12} {:>7} {:>9} {:>9} {:>9} {:>9} {:>7} {:>5}".format(
        "shot", "series", "X mm", "Y mm", "Z mm", "tape mm", "reproj", "use"))
    buckets = {"depth": [], "spread": [], "target": []}
    for shot in shots:
        if shot.get("series") not in buckets:
            print("{:<12} {:>62}".format(
                shot["name"], "unknown series " + repr(shot.get("series"))))
            continue
        xyz, info = _measure_shot(rig, run_dir, shot)
        if xyz is None:
            print("{:<12} {:>7} {:>54}".format(
                shot["name"], shot["series"], info))
            continue
        usable = info <= MAX_REPROJECTION_PX
        print("{:<12} {:>7} {:9.1f} {:9.1f} {:9.1f} {:9.1f} {:7.2f} {:>5}".format(
            shot["name"], shot["series"], xyz[0] * 1000, xyz[1] * 1000,
            xyz[2] * 1000, shot["tape_mm"], info, "yes" if usable else "NO"))
        if usable:
            buckets[shot["series"]].append((shot, xyz))

    # The plane wants every floor position it can get - spread across the
    # image width is exactly what makes it determined. The scale fit does
    # NOT: it equates a 3D distance with a difference of two tape readings,
    # and that identity holds only along the collinear depth line.
    floor = buckets["depth"] + buckets["spread"]
    if len(floor) < 3:
        print("\nOnly {} usable floor shots; a plane needs 3.".format(len(floor)))
        return 1

    # --- attitude -------------------------------------------------------
    plane = ground_plane.fit_plane(np.array([xyz for _, xyz in floor]))
    pitch, roll = ground_plane.attitude_from_plane(plane)
    print("\nfloor plane: rms {:.2f} mm, conditioning {:.3f}".format(
        plane.rms_m * 1000.0, plane.conditioning))
    print("  pitch {:+.3f} deg   roll {:+.3f} deg".format(pitch, roll))

    if len(buckets["target"]) >= 2:
        ordered = sorted(buckets["target"], key=lambda item: item[1][2])
        yaw = ground_plane.yaw_from_target_line(
            plane, ordered[0][1], ordered[-1][1])
        print("  yaw   {:+.3f} deg".format(yaw))
    else:
        yaw = None
        print("  yaw     not measured - needs 2 usable target-line shots")

    # --- scale ----------------------------------------------------------
    depth_ordered = sorted(buckets["depth"], key=lambda item: item[0]["tape_mm"])
    measured, taped = [], []
    for (shot_a, xyz_a), (shot_b, xyz_b) in zip(depth_ordered, depth_ordered[1:]):
        gap_tape = (shot_b["tape_mm"] - shot_a["tape_mm"]) / 1000.0
        if gap_tape <= 0.0:
            continue
        measured.append(float(np.linalg.norm(xyz_b - xyz_a)))
        taped.append(gap_tape)

    if len(measured) >= 3:
        scale, rms = triangulate.fit_scale_factor(measured, taped)
        print("\nscale against tape: {:.4f} over {} displacements "
              "(residual {:.2f} mm)".format(scale, len(measured), rms * 1000.0))
        print("  implied baseline: {:.3f} mm against the file's {:.3f} mm".format(
            rig.baseline_m * 1000.0 / scale, rig.baseline_m * 1000.0))
    else:
        print("\nscale: needs 4+ usable collinear depth positions, "
              "have {}".format(len(measured) + 1))

    # --- what to type into the config -----------------------------------
    offset = stereo_geometry.camera2_offset_from_camera1(rig)
    print("\n--- values for golf_sim_config.json (enter by hand) ---")
    print('  "kCamera2OffsetFromCamera1OriginMeters": '
          "[{:.6f}, {:.6f}, {:.6f}]".format(*offset))
    print('  "kCamera1Angles": [{:+.3f}, {:+.3f}]'.format(
        0.0 if yaw is None else yaw, pitch))
    print("  (pan, tilt. Yaw is pan; pitch is tilt. Roll {:+.3f} deg is not "
          "representable in this constant.)".format(roll))
    return 0
```

Add the imports `import numpy as np` and `from sp1_vision import ground_plane, stereo_geometry, triangulate` at the top of the file, and wire the flag in `main` before the `--shots` branch:

```python
    parser.add_argument("--analyse", metavar="RUNDIR",
                        help="analyse a captured run directory")
    parser.add_argument("--extrinsics",
                        default=stereo_geometry.DEFAULT_EXTRINSICS_PATH)
    parser.add_argument("--config", default=stereo_geometry.DEFAULT_CONFIG_PATH)
```

```python
    if args.analyse and args.shots:
        parser.error("--analyse and --shots do different things; pick one")
    if args.analyse:
        return run_analysis(args.analyse, args.extrinsics, args.config)
```

and change the final `parser.error` to `parser.error("give either --shots N or --analyse RUNDIR")`.

- [ ] **Step 6: Verify the CLI still parses**

Run: `python3 -m sp1_vision.cli_triangulate --help`
Expected: both `--shots` and `--analyse` listed

Run: `python3 -m sp1_vision.cli_triangulate --shots 3 --analyse foo`
Expected: exits non-zero with `--analyse and --shots do different things`

- [ ] **Step 7: Run the whole suite**

Run: `python3 -m unittest discover -s sp1_vision/tests -t . -v`
Expected: PASS, everything

- [ ] **Step 8: Commit**

```bash
git add sp1_vision/cli_triangulate.py sp1_vision/triangulate.py \
        sp1_vision/tests/test_triangulate.py
git commit -m "SP1: analyse a triangulation run - attitude, scale, and the config values"
```

---

### Task 8: Run it on hardware, and write down what came out

**Files:**
- Create: `sp1_vision/triangulation_run/README.md`
- Create: `sp1_vision/triangulation_run/cam1/*.png`, `cam2/*.png`, `run.json` (captured)
- Modify: `CLAUDE.md`
- Modify: `LOGBOOK.md`

**Interfaces:**
- Consumes: everything above.
- Produces: measured pitch, roll, yaw; a resolved baseline question; the config values.

- [ ] **Step 1: Capture the series**

On the Jetson, from the repo root:

```bash
python3 -m sp1_vision.cli_triangulate --shots 12 --out sp1_vision/triangulation_run
```

Follow the depth / spread / target layout printed by the tool, answering `d`, `s` or `t` for each shot. Mark each floor position before capturing so the tape reading and the ball agree; the tape is the limiting instrument in the scale check, not the cameras.

The six `depth` positions must lie on **one straight line** running away from the unit — the scale fit equates their 3D separation with the difference of their tape readings, and that is only true along a line. Snap a chalk line or lay a straightedge before starting.

- [ ] **Step 2: Analyse**

```bash
python3 -m sp1_vision.cli_triangulate --analyse sp1_vision/triangulation_run
```

Check before believing anything: every kept row's reprojection residual under 2 px, floor-plane conditioning above 0.15, and plane RMS in the low millimetres. A conditioning warning means the ball positions were not spread widely enough across the image — recapture rather than reason around it.

- [ ] **Step 3: Cross-check the attitude against a second subset**

Re-run the plane fit on the near half and the far half of the floor positions separately, by temporarily moving the other shots' entries out of `run.json`. Pitch and roll should agree between subsets to a few tenths of a degree.

This is the direct lesson from the calibration: two intrinsic sets once gave pitch −0.745° and −1.834° at an identical RMS of 0.90. A residual does not tell you whether a number is determined; re-solving on subsets does.

- [ ] **Step 4: Write the run README**

Create `sp1_vision/triangulation_run/README.md` covering: the date, the ball positions and their tape readings, the measured pitch/roll/yaw with the subset spread from Step 3, the plane RMS and conditioning, the scale factor and what it implies for the 78.28-against-78.749 question, and any shots dropped and why.

- [ ] **Step 5: Enter the config values by hand**

Into `Software/LMSourceCode/ImageProcessing/golf_sim_config.json`, from the tool's final block:

- `kCamera2OffsetFromCamera1OriginMeters` — replacing PiTrac's `[0.00, -0.19, 0.0]`
- `kCamera1Angles` and `kCamera2Angles` — from the measured attitude
- `kCamera1PositionsFromExpectedBallMeters` and `kCamera2PositionsFromExpectedBallMeters` — `[0.0, 0.0937, 0.500]`, norm 0.509 m, replacing `[-0.200, -0.234, 0.54]` and `[0.0, -0.051, 0.45]`

- [ ] **Step 6: Correct CLAUDE.md**

Two edits:

- Under "Still open on the seam", delete the `sensor_width_`/`sensor_height_` paragraph. It is fixed: `v4l2_interface.cpp:831-832` sets the override unconditionally and `camera_hardware.cpp:486-493` applies it.
- Under "Current task", replace items 1 and 2 with the state after this work, and record that the live constant is `kCameraNPositionsFromExpectedBallMeters` — `kCameraNPositionsFromOriginMeters` does not exist in this codebase.

If the scale check contradicts the documented 78.28 mm baseline, correct the figure in CLAUDE.md too, citing the run.

- [ ] **Step 7: Run the whole suite once more, then commit**

```bash
python3 -m unittest discover -s sp1_vision/tests -t . -v
git add sp1_vision/triangulation_run CLAUDE.md LOGBOOK.md \
        Software/LMSourceCode/ImageProcessing/golf_sim_config.json
git commit -m "SP1: the device's attitude, measured - and the world geometry entered"
```

---

## Self-Review

**Spec coverage**

| Spec requirement | Task |
|---|---|
| `stereo_geometry.py`, sole conversion point, load validation table | 2 |
| Y-up conversion, `kCamera2OffsetFromCamera1OriginMeters` from R and T | 3 |
| `triangulate.py`, `undistortPoints` → `triangulatePoints` with P₁=[I\|0] | 4 |
| Reprojection residual as per-measurement validity flag | 4, 7 |
| `ground_plane.py`, normal, pitch, roll, residuals, conditioning reported | 5 |
| Same detector and parameters in both images | 1 |
| Capture via `calibration_capture`, binding via `camera_paths` | 6 |
| 8–10 floor positions over 35–70 cm, spread across the width | 6 |
| Tape distance per position | 6 |
| 2 target-line positions for yaw | 6 |
| Verification against tape | 7 |
| Attitude measurement | 7 |
| Baseline discrepancy settled from displacements | 7 |
| Nothing written to `golf_sim_config.json` automatically | 6, 7, 8 |
| Synthetic-geometry tests incl. swapped-camera guard | 4 |
| Ill-conditioned plane must raise | 5 |
| CLAUDE.md sensor-size correction | 8 |

Two spec items are deliberately not tasks. The provenance gap in
`stereo_extrinsics.json` — nothing records which intrinsics it was solved
against — is recorded in the spec as a recommendation and is a change to
`StereoCalibration.py`, which belongs with a calibration re-run rather than
here; `validate_rig`'s fx check is the partial substitute. The silhouette-centre
bias is documented in `find_ball`'s docstring and left uncorrected, as specified.

**Placeholders:** none. Every code step carries the code; every test step carries
the assertions.

**Type consistency:** `find_ball` returns `(bool, (u, v, r))` and Task 7 slices
`[:2]` for the centre. `fit_plane` takes `(N, 3)` and Task 7 builds it with
`np.array([xyz for _, xyz in kept])`. `fit_scale_factor` returns
`(scale, rms)` and Task 7 unpacks two. `load_rig`'s defaults are the constants
Task 7's argparse references. `PlaneFitError` is raised by both `fit_plane` and
`yaw_from_target_line`, and Task 7 lets it propagate — a run that cannot
determine its geometry should stop, not print a number.

One asymmetry worth flagging to the reviewer rather than silently resolving:
`kCameraNAngles` holds pan and tilt only. The measured **roll** has nowhere to
go in PiTrac's data model. Task 7 prints it and says so. Whether roll needs to
be carried at all is a Block 2 question — it belongs in the rotation applied to
triangulated points, not in a two-element constant.
