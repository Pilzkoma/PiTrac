# OV9281 Intrinsics + Stereo Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a re-runnable calibration tool — clickable from the Jetson dashboard — that measures the real intrinsics of both OV9281 cameras and the stereo extrinsics between them.

**Architecture:** A hardware-facing Python module (`sp1_vision/`) with two front ends over it: a Flask blueprint mounted into the existing `sp4_gspro/dashboard.py`, and a CLI fallback. Cameras bind by USB port path because both modules report the same USB serial. A background grabber thread keeps one barrier-synced frame pair current, which both the live MJPEG streams and the capture button read from, so pair simultaneity is structural rather than something each caller has to get right. Analysis reuses PiTrac's `CameraCalibration.py`, patched for our resolution and extended with `stereoCalibrate`.

**Tech Stack:** Python 3.8.10, OpenCV 4.5.4, Flask 3.0.3, numpy 1.17.4, `unittest` from the standard library (the Jetson has no pytest and this plan does not add dependencies to a working device), `v4l2-ctl` for exposure control.

**Spec:** `docs/superpowers/specs/2026-08-06-ov9281-intrinsics-stereo-calibration-design.md`

---

## Working loop

Code is written in the Windows checkout; it runs on the Jetson. Iterate with `scp`, commit from Windows when green.

```bash
# push one file to the Jetson for a test run
scp -i ~/.ssh/jetsonlm_key <local-path> brain@192.168.178.194:~/JetsonLM/<repo-relative-path>

# run something there
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM && <command>"
```

Every `ssh` prints a post-quantum key-exchange warning. It is harmless; filter it with `| grep -v "post-quantum\|store now\|openssh.com/pq"` when it clutters output.

All tests run **on the Jetson**, because the Windows checkout has no OpenCV. Test command shape, used throughout:

```bash
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM && python3 -m unittest sp1_vision.tests.<module> -v"
```

After a task goes green, commit **from Windows** and push. The Jetson has no push credentials — if a commit is ever made there instead, retrieve it with:

```bash
GIT_SSH_COMMAND="ssh -i $HOME/.ssh/jetsonlm_key" git fetch "ssh://brain@192.168.178.194/home/brain/JetsonLM" main
git merge --ff-only FETCH_HEAD && git push origin main
```

---

## File structure

| File | Responsibility |
|---|---|
| `sp1_vision/__init__.py` (create) | Makes `sp1_vision` importable as a package |
| `sp1_vision/camera_paths.py` (create) | Logical camera number → real device node, via USB port path. No OpenCV, no hardware. |
| `sp1_vision/frame_analysis.py` (create) | Pure frame maths: sharpness score, chessboard detection. No hardware. |
| `sp1_vision/calibration_capture.py` (create) | `CameraPair` (open/grab/release, barrier-synced) and `CalibrationSession` (background grabber, latest-pair cache, idle release) |
| `sp1_vision/cli_calibrate.py` (create) | CLI front end: `--focus`, `--shots` |
| `sp1_vision/tests/` (create) | `unittest` suites |
| `sp4_gspro/calibration_page.py` (create) | Flask blueprint: page, MJPEG streams, capture, run. Kept out of `dashboard.py`, which is already ~1400 lines. |
| `sp4_gspro/dashboard.py` (modify) | Register the blueprint, add a nav link |
| `Software/CalibrateCameraDistortions/CameraCalibration.py` (modify) | Resolution, CLI args, `cornerSubPix` fix, per-image error, JSON output, `stereoCalibrate` |
| `Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp` (modify) | Bind by port path instead of hardcoded `/dev/videoN` |

---

### Task 1: Package scaffolding and stable camera binding

`sp1_vision/` is currently two loose scripts. It becomes a package so the dashboard and the CLI can both import from it.

**Files:**
- Create: `sp1_vision/__init__.py`
- Create: `sp1_vision/tests/__init__.py`
- Create: `sp1_vision/tests/test_camera_paths.py`
- Create: `sp1_vision/camera_paths.py`

- [ ] **Step 1: Create the two empty package markers**

```bash
cd d:/Users/lasse/Documents/JetsonLM
mkdir -p sp1_vision/tests
touch sp1_vision/__init__.py sp1_vision/tests/__init__.py
```

- [ ] **Step 2: Write the failing test**

Create `sp1_vision/tests/test_camera_paths.py`:

```python
"""Camera binding must be stable across reboots and must fail loudly."""

import os
import shutil
import tempfile
import unittest

from sp1_vision import camera_paths


class DeviceForCameraTest(unittest.TestCase):
    def setUp(self):
        # A stand-in for /dev/v4l/by-path containing symlinks that point at
        # real files, so os.path.realpath has something to resolve.
        self.root = tempfile.mkdtemp()
        self.dev = os.path.join(self.root, "dev")
        self.by_path = os.path.join(self.root, "by-path")
        os.makedirs(self.dev)
        os.makedirs(self.by_path)

    def tearDown(self):
        shutil.rmtree(self.root)

    def _link(self, camera_number, target_name):
        target = os.path.join(self.dev, target_name)
        open(target, "w").close()
        os.symlink(
            target,
            os.path.join(self.by_path, camera_paths.CAMERA_PORT_PATHS[camera_number]),
        )
        return target

    def test_resolves_symlink_to_real_device_node(self):
        target = self._link(1, "video0")
        self.assertEqual(
            camera_paths.device_for_camera(1, by_path_dir=self.by_path), target
        )

    def test_binding_follows_the_port_not_the_device_number(self):
        # The same port path now points at a different /dev/videoN, exactly
        # what happens when enumeration order changes across a reboot.
        target = self._link(2, "video7")
        self.assertEqual(
            camera_paths.device_for_camera(2, by_path_dir=self.by_path), target
        )

    def test_missing_port_raises_rather_than_falling_back(self):
        # A silent fallback to /dev/video0 would mirror the stereo baseline
        # with nothing visibly wrong in the images.
        with self.assertRaises(camera_paths.CameraBindingError):
            camera_paths.device_for_camera(1, by_path_dir=self.by_path)

    def test_unknown_camera_number_raises(self):
        with self.assertRaises(camera_paths.CameraBindingError):
            camera_paths.device_for_camera(3, by_path_dir=self.by_path)

    def test_both_cameras_are_mapped_to_distinct_ports(self):
        self.assertEqual(sorted(camera_paths.CAMERA_PORT_PATHS), [1, 2])
        self.assertEqual(len(set(camera_paths.CAMERA_PORT_PATHS.values())), 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
scp -i ~/.ssh/jetsonlm_key sp1_vision/__init__.py brain@192.168.178.194:~/JetsonLM/sp1_vision/
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "mkdir -p ~/JetsonLM/sp1_vision/tests"
scp -i ~/.ssh/jetsonlm_key sp1_vision/tests/__init__.py sp1_vision/tests/test_camera_paths.py brain@192.168.178.194:~/JetsonLM/sp1_vision/tests/
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM && python3 -m unittest sp1_vision.tests.test_camera_paths -v"
```

Expected: `ImportError: cannot import name 'camera_paths' from 'sp1_vision'`

- [ ] **Step 4: Write the implementation**

Create `sp1_vision/camera_paths.py`:

```python
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
# carrier board. Which physical module sits on which port is established
# empirically in Task 2 - do not assume from the numbering.
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
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
scp -i ~/.ssh/jetsonlm_key sp1_vision/camera_paths.py brain@192.168.178.194:~/JetsonLM/sp1_vision/
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM && python3 -m unittest sp1_vision.tests.test_camera_paths -v"
```

Expected: `Ran 5 tests` / `OK`

- [ ] **Step 6: Verify it resolves against the real hardware**

```bash
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM && python3 -c 'from sp1_vision import camera_paths; print(camera_paths.all_devices())'"
```

Expected: `{1: '/dev/video0', 2: '/dev/video2'}` — or different numbers, which is exactly the point.

- [ ] **Step 7: Commit**

```bash
cd d:/Users/lasse/Documents/JetsonLM
git add sp1_vision/__init__.py sp1_vision/tests/__init__.py sp1_vision/tests/test_camera_paths.py sp1_vision/camera_paths.py
git commit -m "SP1: bind cameras by USB port path, not /dev/videoN

Both OV9281 modules report iSerial UC762 - Arducam's SKU code rather than a
per-unit serial - so by-id collides and the device numbers are assigned in
enumeration order. A swap mirrors the stereo baseline and nothing looks wrong
in the images, so the binding fails loudly instead of falling back."
git push origin main
```

---

### Task 2: Establish which USB port holds which physical camera

The numbering in `CAMERA_PORT_PATHS` is an assumption until observed. Getting it backwards mirrors every stereo result, so it is settled by looking, before anything depends on it.

**Files:**
- Modify: `sp1_vision/camera_paths.py` (the `CAMERA_PORT_PATHS` comment, and the mapping itself if the observation contradicts it)

- [ ] **Step 1: Grab one frame from each port and write them out**

```bash
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM && python3 -c \"
import cv2
from sp1_vision import camera_paths
for n, dev in camera_paths.all_devices().items():
    cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 800)
    for _ in range(5):
        cap.read()
    ok, frame = cap.read()
    cv2.imwrite('/tmp/ident_cam%d.png' % n, frame)
    print(n, dev, ok, frame.shape)
    cap.release()
\""
```

Expected: two lines, both `True (800, 1280, 3)`.

- [ ] **Step 2: Repeat with the left-hand lens physically covered**

Cover the **left** module (looking at the unit from the front, the one at CAD X = −4 mm) with a hand or a lens cap, then re-run the command from Step 1 into different filenames:

```bash
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM && python3 -c \"
import cv2, numpy
from sp1_vision import camera_paths
for n, dev in camera_paths.all_devices().items():
    cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 800)
    for _ in range(5):
        cap.read()
    ok, frame = cap.read()
    print('camera', n, dev, 'mean brightness', round(float(numpy.mean(frame)), 1))
    cap.release()
\""
```

Expected: one camera's mean brightness drops sharply (covered), the other does not. The dark one is the left-hand module.

- [ ] **Step 3: Record the finding**

If the dark camera was reported as `1`, the mapping is already correct — replace the "established empirically in Task 2" comment in `sp1_vision/camera_paths.py` with the observation, for example:

```python
# Logical camera number -> USB port path, as enumerated on the Xavier NX
# carrier board. Verified 2026-08-06 by covering each lens in turn:
#   camera 1 = left-hand module  (CAD X = -4 mm, port 2.3)
#   camera 2 = right-hand module (CAD X = +76 mm, port 2.4)
# The baseline sign in every stereo result depends on this mapping.
```

If the dark camera was reported as `2`, swap the two port path strings in `CAMERA_PORT_PATHS` and write the comment to match what was observed.

- [ ] **Step 4: Re-run the binding test**

```bash
scp -i ~/.ssh/jetsonlm_key sp1_vision/camera_paths.py brain@192.168.178.194:~/JetsonLM/sp1_vision/
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM && python3 -m unittest sp1_vision.tests.test_camera_paths -v"
```

Expected: `Ran 5 tests` / `OK`

- [ ] **Step 5: Commit**

```bash
git add sp1_vision/camera_paths.py
git commit -m "SP1: pin camera 1/2 to physical modules by observation

Covered each lens in turn and watched which port went dark. The numbering was
an assumption until now, and getting it backwards mirrors every stereo result."
git push origin main
```

---

### Task 3: Sharpness score for focusing

**Files:**
- Create: `sp1_vision/tests/test_frame_analysis.py`
- Create: `sp1_vision/frame_analysis.py`

- [ ] **Step 1: Write the failing test**

Create `sp1_vision/tests/test_frame_analysis.py`:

```python
"""Pure frame maths - no cameras involved."""

import unittest

import cv2
import numpy as np

from sp1_vision import frame_analysis


def _synthetic_checkerboard(square=40, rows=20, cols=32):
    """High-contrast edges, i.e. something a focus metric should score high."""
    img = np.zeros((rows * square, cols * square), dtype=np.uint8)
    for r in range(rows):
        for c in range(cols):
            if (r + c) % 2 == 0:
                img[r * square:(r + 1) * square, c * square:(c + 1) * square] = 255
    return img


class SharpnessScoreTest(unittest.TestCase):
    def test_sharp_image_scores_higher_than_blurred(self):
        sharp = _synthetic_checkerboard()
        blurred = cv2.GaussianBlur(sharp, (31, 31), 0)
        self.assertGreater(
            frame_analysis.sharpness_score(sharp),
            frame_analysis.sharpness_score(blurred) * 10,
        )

    def test_flat_image_scores_near_zero(self):
        flat = np.full((800, 1280), 128, dtype=np.uint8)
        self.assertLess(frame_analysis.sharpness_score(flat), 1.0)

    def test_accepts_colour_input(self):
        # The capture path yields CV_8UC3 BGR; the metric must not care.
        sharp = _synthetic_checkerboard()
        colour = cv2.cvtColor(sharp, cv2.COLOR_GRAY2BGR)
        self.assertAlmostEqual(
            frame_analysis.sharpness_score(colour),
            frame_analysis.sharpness_score(sharp),
            delta=1.0,
        )

    def test_roi_fraction_restricts_to_centre(self):
        # Sharp centre, flat surround: a centre ROI must score far higher
        # than the whole frame.
        img = np.full((800, 1280), 128, dtype=np.uint8)
        patch = _synthetic_checkerboard(square=10, rows=20, cols=20)
        img[300:500, 540:740] = patch
        whole = frame_analysis.sharpness_score(img, roi_fraction=1.0)
        centre = frame_analysis.sharpness_score(img, roi_fraction=0.25)
        self.assertGreater(centre, whole)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
scp -i ~/.ssh/jetsonlm_key sp1_vision/tests/test_frame_analysis.py brain@192.168.178.194:~/JetsonLM/sp1_vision/tests/
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM && python3 -m unittest sp1_vision.tests.test_frame_analysis -v"
```

Expected: `ImportError: cannot import name 'frame_analysis' from 'sp1_vision'`

- [ ] **Step 3: Write the implementation**

Create `sp1_vision/frame_analysis.py`:

```python
#!/usr/bin/env python3
"""Frame maths used by the calibration tool. No cameras, no I/O."""

import cv2
import numpy as np

# Inner corners of the board in Software/CalibrateCameraDistortions/checkerboard.png.
# Verified 2026-08-06 against both that file and
# checkerboard_test_image_for_undistortion.png.
CHESSBOARD_SIZE = (9, 6)

# cornerSubPix termination, matching PiTrac's CameraCalibration.py.
SUBPIX_CRITERIA = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)


def _as_gray(frame):
    if frame.ndim == 3:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return frame


def sharpness_score(frame, roi_fraction=0.4):
    """Variance of the Laplacian over a centred ROI.

    Higher is sharper. The absolute value is meaningless - it depends on
    scene content - so it is only useful while turning a lens and watching
    the number move. Restricting to the centre keeps a cluttered background
    from drowning out the subject.
    """
    gray = _as_gray(frame)
    if roi_fraction < 1.0:
        h, w = gray.shape[:2]
        rh, rw = int(h * roi_fraction), int(w * roi_fraction)
        y0, x0 = (h - rh) // 2, (w - rw) // 2
        gray = gray[y0:y0 + rh, x0:x0 + rw]
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def find_board(frame, refine=True):
    """Locate the calibration board.

    Returns (found, corners). Corners are sub-pixel refined when found -
    PiTrac's original computed the refinement and then appended the coarse
    corners instead, discarding it. Sub-pixel precision is what makes the
    stereo extrinsics trustworthy, so it is not optional here.
    """
    gray = _as_gray(frame)
    found, corners = cv2.findChessboardCorners(gray, CHESSBOARD_SIZE, None)
    if not found:
        return False, None
    if refine:
        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), SUBPIX_CRITERIA)
    return True, corners
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
scp -i ~/.ssh/jetsonlm_key sp1_vision/frame_analysis.py brain@192.168.178.194:~/JetsonLM/sp1_vision/
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM && python3 -m unittest sp1_vision.tests.test_frame_analysis -v"
```

Expected: `Ran 4 tests` / `OK`

- [ ] **Step 5: Commit**

```bash
git add sp1_vision/frame_analysis.py sp1_vision/tests/test_frame_analysis.py
git commit -m "SP1: sharpness metric and board detection for calibration

find_board returns sub-pixel refined corners. PiTrac's CameraCalibration.py
computes the refinement at line 51 and then appends the coarse corners at
line 52, throwing it away - accuracy given up for nothing, and it matters
more here because the stereo extrinsics rest on it."
git push origin main
```

---

### Task 4: Board detection against a real capture

Task 3 tested sharpness against synthetic images. `find_board` needs a real one, and the repo already contains a suitable 1456×1088 capture.

**Files:**
- Modify: `sp1_vision/tests/test_frame_analysis.py`

- [ ] **Step 1: Add the failing test**

Append to `sp1_vision/tests/test_frame_analysis.py`, before the `if __name__` block:

```python
class FindBoardTest(unittest.TestCase):
    # A real IMX296 capture of the calibration board, shipped with PiTrac.
    FIXTURE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "Software", "CalibrateCameraDistortions",
        "checkerboard_test_image_for_undistortion.png",
    )

    def test_finds_board_in_a_real_capture(self):
        img = cv2.imread(self.FIXTURE, cv2.IMREAD_GRAYSCALE)
        self.assertIsNotNone(img, "fixture not readable: " + self.FIXTURE)
        found, corners = frame_analysis.find_board(img)
        self.assertTrue(found)
        expected = frame_analysis.CHESSBOARD_SIZE[0] * frame_analysis.CHESSBOARD_SIZE[1]
        self.assertEqual(corners.shape[0], expected)

    def test_refinement_moves_corners_but_only_slightly(self):
        img = cv2.imread(self.FIXTURE, cv2.IMREAD_GRAYSCALE)
        _, coarse = frame_analysis.find_board(img, refine=False)
        _, fine = frame_analysis.find_board(img, refine=True)
        shift = np.linalg.norm(fine - coarse, axis=2).max()
        self.assertGreater(shift, 0.0, "cornerSubPix result was discarded")
        self.assertLess(shift, 5.0, "refinement moved a corner implausibly far")

    def test_no_board_in_a_flat_image(self):
        flat = np.full((800, 1280), 128, dtype=np.uint8)
        found, corners = frame_analysis.find_board(flat)
        self.assertFalse(found)
        self.assertIsNone(corners)
```

Add `import os` to the imports at the top of the file.

- [ ] **Step 2: Run the test to verify the new cases fail**

```bash
scp -i ~/.ssh/jetsonlm_key sp1_vision/tests/test_frame_analysis.py brain@192.168.178.194:~/JetsonLM/sp1_vision/tests/
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM && python3 -m unittest sp1_vision.tests.test_frame_analysis -v"
```

Expected: `Ran 7 tests` / `OK` — `find_board` was already written in Task 3, so these pass immediately. If any fail, the fixture path or the refinement behaviour is wrong and must be fixed before continuing; the whole point of this task is that the assertion is real rather than assumed.

- [ ] **Step 3: Commit**

```bash
git add sp1_vision/tests/test_frame_analysis.py
git commit -m "SP1: test board detection against a real capture

Uses PiTrac's own checkerboard_test_image_for_undistortion.png as fixture -
a genuine 1456x1088 frame - and asserts that cornerSubPix actually moved the
corners, which is the bug the upstream script has."
git push origin main
```

---

### Task 5: Paired capture

Both frames of a pair must come from the same instant, or the stereo extrinsics describe a rig that never existed.

**Files:**
- Create: `sp1_vision/calibration_capture.py`
- Create: `sp1_vision/tests/test_calibration_capture.py`

- [ ] **Step 1: Write the failing test**

Create `sp1_vision/tests/test_calibration_capture.py`:

```python
"""CameraPair against the real hardware.

These tests open the cameras. They only pass on the Jetson with both modules
plugged in and nothing else holding the devices - a V4L2 node has a single
owner, so stop the dashboard first if it is streaming.
"""

import time
import unittest

from sp1_vision import calibration_capture


class CameraPairTest(unittest.TestCase):
    def setUp(self):
        self.pair = calibration_capture.CameraPair()
        self.pair.open()

    def tearDown(self):
        self.pair.release()

    def test_grab_returns_one_frame_per_camera_at_full_resolution(self):
        frames = self.pair.grab()
        self.assertEqual(sorted(frames), [1, 2])
        for n in (1, 2):
            self.assertEqual(frames[n].shape[:2], (800, 1280))

    def test_frames_in_a_pair_are_captured_close_together(self):
        # The barrier should hold the two reads to within a frame period or
        # two. Anything worse and a moving board would be in different places
        # in the two images.
        _, skew_s = self.pair.grab_with_skew()
        self.assertLess(skew_s, 0.030)

    def test_repeated_grabs_return_fresh_frames(self):
        first = self.pair.grab()
        time.sleep(0.1)
        second = self.pair.grab()
        # BUFFERSIZE 1 plus a live scene means consecutive frames should
        # differ somewhere. Identical frames mean a stale buffer.
        self.assertFalse((first[1] == second[1]).all())

    def test_release_is_idempotent(self):
        self.pair.release()
        self.pair.release()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
scp -i ~/.ssh/jetsonlm_key sp1_vision/tests/test_calibration_capture.py brain@192.168.178.194:~/JetsonLM/sp1_vision/tests/
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM && python3 -m unittest sp1_vision.tests.test_calibration_capture -v"
```

Expected: `ImportError: cannot import name 'calibration_capture' from 'sp1_vision'`

- [ ] **Step 3: Write the implementation**

Create `sp1_vision/calibration_capture.py`:

```python
#!/usr/bin/env python3
"""Simultaneous capture from both OV9281 modules, for calibration.

Sequential per-camera series can never yield stereo extrinsics - the two
views must show the board in the same place at the same moment. That makes
paired capture the one irreversible decision in this tool, so it is the
primitive everything else is built on rather than something each caller
arranges for itself.

Capture setup follows sp1_vision/dual_camera_test.py, which established that
MJPG FOURCC must be set before resolution or format negotiation falls back to
YUYV at 10 FPS.
"""

import subprocess
import threading
import time

import cv2

from sp1_vision import camera_paths

FRAME_WIDTH = 1280
FRAME_HEIGHT = 800
FRAME_RATE = 120
FOURCC = cv2.VideoWriter_fourcc("M", "J", "P", "G")
WARMUP_FRAMES = 5


def set_manual_exposure(device, exposure_units):
    """Force manual exposure so a capture series is consistently lit.

    exposure_units are 100 us steps, matching V4L2's exposure_absolute
    (range 1..5000 on these modules). Pass None to restore auto.

    Done through v4l2-ctl rather than cv2.CAP_PROP_AUTO_EXPOSURE because the
    OpenCV property semantics vary across versions on the V4L2 backend.
    """
    if exposure_units is None:
        ctrl = "exposure_auto=3"
    else:
        ctrl = "exposure_auto=1,exposure_absolute={}".format(int(exposure_units))
    subprocess.run(
        ["v4l2-ctl", "--device={}".format(device), "--set-ctrl={}".format(ctrl)],
        check=False, capture_output=True,
    )


class CameraPair:
    """Both cameras, opened together, grabbed together."""

    def __init__(self, exposure_units=None):
        self.exposure_units = exposure_units
        self._caps = {}
        self._devices = {}

    def open(self):
        self._devices = camera_paths.all_devices()
        for n, dev in self._devices.items():
            if self.exposure_units is not None:
                set_manual_exposure(dev, self.exposure_units)
            cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
            if not cap.isOpened():
                self.release()
                raise RuntimeError(
                    "camera {} at {} would not open; another process may hold "
                    "it (a V4L2 node has a single owner)".format(n, dev)
                )
            cap.set(cv2.CAP_PROP_FOURCC, FOURCC)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
            cap.set(cv2.CAP_PROP_FPS, FRAME_RATE)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            for _ in range(WARMUP_FRAMES):
                cap.read()
            self._caps[n] = cap
        return self

    def grab(self):
        """Return {camera_number: BGR frame}, captured simultaneously."""
        frames, _ = self.grab_with_skew()
        return frames

    def grab_with_skew(self):
        """Return ({camera_number: frame}, skew_seconds).

        Skew is the spread between the two read completions - a health
        measure for how simultaneous the pair really was.
        """
        frames = {}
        stamps = {}
        errors = {}
        barrier = threading.Barrier(len(self._caps))

        def worker(n, cap):
            try:
                barrier.wait()
                ok, frame = cap.read()
                stamps[n] = time.perf_counter()
                if not ok or frame is None:
                    errors[n] = "read failed"
                else:
                    frames[n] = frame
            except Exception as exc:            # noqa: BLE001 - reported below
                errors[n] = repr(exc)

        threads = [
            threading.Thread(target=worker, args=(n, cap))
            for n, cap in self._caps.items()
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if errors:
            raise RuntimeError("paired grab failed: {}".format(errors))
        return frames, max(stamps.values()) - min(stamps.values())

    def release(self):
        for n, cap in list(self._caps.items()):
            cap.release()
            del self._caps[n]
        if self.exposure_units is not None:
            for dev in self._devices.values():
                set_manual_exposure(dev, None)

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.release()
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
scp -i ~/.ssh/jetsonlm_key sp1_vision/calibration_capture.py brain@192.168.178.194:~/JetsonLM/sp1_vision/
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM && python3 -m unittest sp1_vision.tests.test_calibration_capture -v"
```

Expected: `Ran 4 tests` / `OK`

If `test_frames_in_a_pair_are_captured_close_together` fails, report the measured skew rather than loosening the threshold — a large skew means the pairing is not doing its job and the stereo result would be quietly wrong.

- [ ] **Step 5: Commit**

```bash
git add sp1_vision/calibration_capture.py sp1_vision/tests/test_calibration_capture.py
git commit -m "SP1: barrier-synced paired capture from both OV9281

Sequential series can never yield stereo extrinsics, so pairing is the
primitive rather than a caller responsibility. grab_with_skew reports how
simultaneous the pair actually was, and the test asserts on it."
git push origin main
```

---

### Task 6: Session with a background grabber

Live streaming and pair capture must not fight over the devices, and the cameras must be handed back when calibration is not in progress — `pitrac_lm` cannot open a node the dashboard is holding.

**Files:**
- Modify: `sp1_vision/calibration_capture.py`
- Modify: `sp1_vision/tests/test_calibration_capture.py`

- [ ] **Step 1: Write the failing test**

Append to `sp1_vision/tests/test_calibration_capture.py`, before the `if __name__` block:

```python
class CalibrationSessionTest(unittest.TestCase):
    def tearDown(self):
        calibration_capture.SESSION.release()

    def test_latest_pair_becomes_available_after_start(self):
        session = calibration_capture.SESSION
        session.ensure_open()
        deadline = time.time() + 5.0
        while session.latest_pair() is None and time.time() < deadline:
            time.sleep(0.05)
        pair = session.latest_pair()
        self.assertIsNotNone(pair, "grabber produced no pair within 5 s")
        self.assertEqual(sorted(pair), [1, 2])

    def test_ensure_open_is_idempotent(self):
        session = calibration_capture.SESSION
        session.ensure_open()
        session.ensure_open()
        self.assertTrue(session.is_open())

    def test_release_frees_the_devices_for_another_opener(self):
        session = calibration_capture.SESSION
        session.ensure_open()
        session.release()
        self.assertFalse(session.is_open())
        # If the devices were genuinely released, a plain CameraPair opens.
        pair = calibration_capture.CameraPair()
        pair.open()
        pair.release()

    def test_idle_timeout_releases_without_being_asked(self):
        session = calibration_capture.SESSION
        session.idle_timeout_s = 1.0
        session.ensure_open()
        deadline = time.time() + 6.0
        while session.is_open() and time.time() < deadline:
            time.sleep(0.1)
        self.assertFalse(session.is_open(), "session did not release when idle")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
scp -i ~/.ssh/jetsonlm_key sp1_vision/tests/test_calibration_capture.py brain@192.168.178.194:~/JetsonLM/sp1_vision/tests/
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM && python3 -m unittest sp1_vision.tests.test_calibration_capture -v"
```

Expected: `AttributeError: module 'sp1_vision.calibration_capture' has no attribute 'SESSION'`

- [ ] **Step 3: Write the implementation**

Append to `sp1_vision/calibration_capture.py`:

```python
# Seconds without a request before the grabber gives the cameras back. A
# V4L2 node has a single owner, so a dashboard that never lets go would block
# pitrac_lm from ever starting.
DEFAULT_IDLE_TIMEOUT_S = 120.0


class CalibrationSession:
    """One shared CameraPair behind a background grabber.

    Streams and captures both read the most recent pair rather than touching
    the devices, so any number of viewers cost nothing extra and every
    captured pair is genuinely simultaneous by construction.
    """

    def __init__(self, idle_timeout_s=DEFAULT_IDLE_TIMEOUT_S):
        self.idle_timeout_s = idle_timeout_s
        self._pair = None
        self._latest = None
        self._latest_skew = None
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self._last_use = 0.0

    def is_open(self):
        with self._lock:
            return self._pair is not None

    def ensure_open(self, exposure_units=None):
        with self._lock:
            self._last_use = time.monotonic()
            if self._pair is not None:
                return
            self._pair = CameraPair(exposure_units=exposure_units).open()
            self._latest = None
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def _loop(self):
        while not self._stop.is_set():
            with self._lock:
                pair = self._pair
                idle = time.monotonic() - self._last_use
            if pair is None:
                return
            if idle > self.idle_timeout_s:
                self.release()
                return
            try:
                frames, skew = pair.grab_with_skew()
            except Exception:                   # noqa: BLE001 - keep serving
                time.sleep(0.05)
                continue
            with self._lock:
                self._latest = frames
                self._latest_skew = skew

    def touch(self):
        """Mark the session as in use, deferring the idle release."""
        with self._lock:
            self._last_use = time.monotonic()

    def latest_pair_with_skew(self):
        """Return ({camera: frame}, skew_seconds), or (None, None).

        The skew belongs to the pair it is returned with. Reporting a
        placeholder here would put a number on screen that never means
        anything, which is worse than showing none.
        """
        self.touch()
        with self._lock:
            return self._latest, self._latest_skew

    def latest_pair(self):
        return self.latest_pair_with_skew()[0]

    def latest(self, camera_number):
        pair = self.latest_pair()
        return None if pair is None else pair.get(camera_number)

    def release(self):
        self._stop.set()
        thread = self._thread
        with self._lock:
            pair, self._pair, self._latest, self._thread = self._pair, None, None, None
            self._latest_skew = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        if pair is not None:
            pair.release()


# One session per process. The dashboard is single-process, and two grabbers
# on the same devices would only fight.
SESSION = CalibrationSession()
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
scp -i ~/.ssh/jetsonlm_key sp1_vision/calibration_capture.py brain@192.168.178.194:~/JetsonLM/sp1_vision/
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM && python3 -m unittest sp1_vision.tests.test_calibration_capture -v"
```

Expected: `Ran 8 tests` / `OK`

- [ ] **Step 5: Commit**

```bash
git add sp1_vision/calibration_capture.py sp1_vision/tests/test_calibration_capture.py
git commit -m "SP1: shared calibration session with idle camera release

A background grabber keeps one barrier-synced pair current; streams and
captures read it rather than touching the devices. Releases after two idle
minutes, because a V4L2 node has a single owner and a dashboard that never
lets go would keep pitrac_lm from ever starting."
git push origin main
```

---

### Task 7: CLI front end

The dashboard is the primary interface, but calibration must stay possible when it is down.

**Files:**
- Create: `sp1_vision/cli_calibrate.py`

- [ ] **Step 1: Write the implementation**

Create `sp1_vision/cli_calibrate.py`:

```python
#!/usr/bin/env python3
"""Command-line calibration capture - the fallback when the dashboard is down.

    python3 -m sp1_vision.cli_calibrate --focus
    python3 -m sp1_vision.cli_calibrate --shots 20 --out images
"""

import argparse
import os
import sys
import time

import cv2

from sp1_vision import calibration_capture, frame_analysis


def run_focus(exposure_units):
    print("Focus mode. Turn each lens until its score peaks. Ctrl-C to stop.")
    with calibration_capture.CameraPair(exposure_units=exposure_units) as pair:
        try:
            while True:
                frames = pair.grab()
                scores = {
                    n: frame_analysis.sharpness_score(f) for n, f in frames.items()
                }
                print(
                    "\rcam1 {:9.1f}   cam2 {:9.1f}".format(scores[1], scores[2]),
                    end="", flush=True,
                )
                time.sleep(0.5)
        except KeyboardInterrupt:
            print()


def run_shots(count, out_dir, exposure_units):
    dirs = {n: os.path.join(out_dir, "cam{}".format(n)) for n in (1, 2)}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)

    print("Capturing {} pairs into {}. Starting in 5 s.".format(count, out_dir))
    time.sleep(5)

    good = 0
    with calibration_capture.CameraPair(exposure_units=exposure_units) as pair:
        for i in range(1, count + 1):
            time.sleep(2)
            print("READY - hold still", flush=True)
            frames, skew = pair.grab_with_skew()

            found = {}
            for n, frame in frames.items():
                found[n], _ = frame_analysis.find_board(frame)
                cv2.imwrite(os.path.join(dirs[n], "gs_{:02d}.png".format(i)), frame)

            both = found[1] and found[2]
            good += 1 if both else 0
            print(
                "  pair {:2d}: cam1 {}  cam2 {}  skew {:.1f} ms  -> {}".format(
                    i,
                    "board" if found[1] else "  --  ",
                    "board" if found[2] else "  --  ",
                    skew * 1000,
                    "keep" if both else "MOVE THE BOARD AND RETRY",
                )
            )
    print("\n{} of {} pairs usable.".format(good, count))
    return 0 if good >= 10 else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--focus", action="store_true",
                        help="live sharpness score for focusing the lenses")
    parser.add_argument("--shots", type=int, metavar="N",
                        help="capture N simultaneous checkerboard pairs")
    parser.add_argument("--out", default="images",
                        help="output directory for --shots (default: images)")
    parser.add_argument("--exposure", type=int, metavar="N",
                        help="manual exposure in 100 us units (1-5000); "
                             "omit for auto")
    args = parser.parse_args(argv)

    if args.focus:
        run_focus(args.exposure)
        return 0
    if args.shots:
        return run_shots(args.shots, args.out, args.exposure)
    parser.error("give either --focus or --shots N")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify focus mode runs and reports two scores**

```bash
scp -i ~/.ssh/jetsonlm_key sp1_vision/cli_calibrate.py brain@192.168.178.194:~/JetsonLM/sp1_vision/
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM && timeout 4 python3 -m sp1_vision.cli_calibrate --focus; true"
```

Expected: a `cam1 <number> cam2 <number>` line that updates, both numbers non-zero.

- [ ] **Step 3: Verify shot mode writes files and reports per-pair detection**

Hold the printed checkerboard in front of both cameras for this.

```bash
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM && python3 -m sp1_vision.cli_calibrate --shots 2 --out /tmp/caltest && ls -l /tmp/caltest/cam1 /tmp/caltest/cam2"
```

Expected: two `pair NN:` lines reporting board/`--` per camera and a skew in milliseconds, then two PNGs in each directory.

- [ ] **Step 4: Commit**

```bash
git add sp1_vision/cli_calibrate.py
git commit -m "SP1: CLI front end for calibration capture

Reports board detection per camera immediately after each pair, so unusable
shots surface while the board is still in hand rather than twenty shots later."
git push origin main
```

---

### Task 8: Calibration page as a Flask blueprint

**Files:**
- Create: `sp4_gspro/calibration_page.py`

- [ ] **Step 1: Write the implementation**

Create `sp4_gspro/calibration_page.py`:

```python
#!/usr/bin/env python3
"""Calibration page for the Jetson LM dashboard.

Kept out of dashboard.py, which is already around 1400 lines. Registered as a
blueprint from there.

dashboard.py runs with its working directory set to sp4_gspro/ and imports
its siblings flat, so sp1_vision - a sibling of sp4_gspro under the repo root -
is not importable without help. Hence the sys.path insert below.
"""

import os
import sys
import time

import cv2
from flask import Blueprint, Response, jsonify, render_template_string

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sp1_vision import calibration_capture, frame_analysis  # noqa: E402

calibration_bp = Blueprint("calibration", __name__)

# Where captured pairs land. Relative to the repo root so the CLI and the
# dashboard agree on one location.
IMAGE_ROOT = os.path.join(_REPO_ROOT, "sp1_vision", "calibration_images")

CALIBRATION_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Jetson LM — Calibration</title>
<style>
  :root { --bg:#0c1117; --surface:#161b22; --line:#26303d;
          --text:#e6edf3; --muted:#8b949e; --ok:#3fb950; --bad:#f85149; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font-family: 'DM Sans', system-ui, sans-serif; padding:24px; }
  h1 { font-size:20px; margin:0 0 4px; }
  p.sub { color:var(--muted); margin:0 0 24px; font-size:14px; }
  a.back { color:var(--muted); text-decoration:none; font-size:14px; }
  .cams { display:flex; gap:16px; flex-wrap:wrap; }
  .cam { background:var(--surface); border:1px solid var(--line);
         border-radius:10px; padding:12px; flex:1 1 420px; }
  .cam img { width:100%; border-radius:6px; display:block; background:#000; }
  .score { font-family:'JetBrains Mono', monospace; font-size:22px;
           margin-top:8px; }
  .score small { color:var(--muted); font-size:12px; font-family:inherit; }
  .bar { height:6px; background:var(--line); border-radius:3px;
         margin-top:6px; overflow:hidden; }
  .bar > div { height:100%; background:var(--ok); width:0%; transition:width .2s; }
  .controls { margin-top:24px; display:flex; gap:12px; align-items:center;
              flex-wrap:wrap; }
  button { background:#238636; color:#fff; border:0; border-radius:6px;
           padding:10px 18px; font-size:14px; cursor:pointer; }
  button.secondary { background:var(--surface); border:1px solid var(--line);
                     color:var(--text); }
  button:disabled { opacity:.5; cursor:not-allowed; }
  #log { margin-top:20px; background:var(--surface); border:1px solid var(--line);
         border-radius:10px; padding:14px; font-family:'JetBrains Mono', monospace;
         font-size:13px; max-height:340px; overflow-y:auto; white-space:pre-wrap; }
  .ok { color:var(--ok); } .bad { color:var(--bad); }
</style>
</head>
<body>
<a class="back" href="/">&larr; Dashboard</a>
<h1>Camera Calibration</h1>
<p class="sub">Focus each lens until its score peaks, then capture around 20 board pairs.
Hold the board at working distance, reaching the corners as well as the centre.</p>

<div class="cams">
  <div class="cam">
    <img src="/calibration/stream/1" alt="camera 1">
    <div class="score">cam 1 &nbsp; <span id="s1">—</span> <small>sharpness</small></div>
    <div class="bar"><div id="b1"></div></div>
  </div>
  <div class="cam">
    <img src="/calibration/stream/2" alt="camera 2">
    <div class="score">cam 2 &nbsp; <span id="s2">—</span> <small>sharpness</small></div>
    <div class="bar"><div id="b2"></div></div>
  </div>
</div>

<div class="controls">
  <button id="cap">Capture pair</button>
  <button id="run" class="secondary">Run calibration</button>
  <button id="rel" class="secondary">Release cameras</button>
  <span id="count" style="color:var(--muted)"></span>
</div>

<div id="log">ready</div>

<script>
const log = (msg, cls) => {
  const el = document.getElementById('log');
  el.innerHTML += '\n' + (cls ? '<span class="' + cls + '">' + msg + '</span>' : msg);
  el.scrollTop = el.scrollHeight;
};

let peak = {1: 1, 2: 1};
async function poll() {
  try {
    const r = await fetch('/calibration/sharpness');
    const d = await r.json();
    for (const n of [1, 2]) {
      const v = d['cam' + n];
      if (v === null) continue;
      document.getElementById('s' + n).textContent = v.toFixed(1);
      peak[n] = Math.max(peak[n], v);
      document.getElementById('b' + n).style.width =
        Math.round(100 * v / peak[n]) + '%';
    }
  } catch (e) { /* page probably closing */ }
  setTimeout(poll, 500);
}
poll();

async function refreshCount() {
  const r = await fetch('/calibration/status');
  const d = await r.json();
  document.getElementById('count').textContent = d.pairs + ' pairs captured';
}
refreshCount();

document.getElementById('cap').onclick = async (e) => {
  e.target.disabled = true;
  const r = await fetch('/calibration/capture', {method: 'POST'});
  const d = await r.json();
  if (d.error) log('capture failed: ' + d.error, 'bad');
  else log('pair ' + d.index + ':  cam1 ' + (d.found1 ? 'board' : '  --  ') +
           '   cam2 ' + (d.found2 ? 'board' : '  --  ') +
           '   skew ' + d.skew_ms.toFixed(1) + ' ms' +
           (d.found1 && d.found2 ? '' : '   <- move the board and retry'),
           d.found1 && d.found2 ? 'ok' : 'bad');
  await refreshCount();
  e.target.disabled = false;
};

document.getElementById('run').onclick = async (e) => {
  e.target.disabled = true;
  log('running calibration, this takes a moment...');
  const r = await fetch('/calibration/run', {method: 'POST'});
  const d = await r.json();
  log(d.error ? ('failed: ' + d.error) : d.report, d.error ? 'bad' : 'ok');
  e.target.disabled = false;
};

document.getElementById('rel').onclick = async () => {
  await fetch('/calibration/release', {method: 'POST'});
  log('cameras released - pitrac_lm can open them again');
};
</script>
</body>
</html>
"""


def _pair_dirs():
    dirs = {n: os.path.join(IMAGE_ROOT, "cam{}".format(n)) for n in (1, 2)}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    return dirs


def _pair_count():
    d = os.path.join(IMAGE_ROOT, "cam1")
    if not os.path.isdir(d):
        return 0
    return len([f for f in os.listdir(d) if f.endswith(".png")])


@calibration_bp.route("/calibration")
def calibration_page():
    return render_template_string(CALIBRATION_HTML)


@calibration_bp.route("/calibration/stream/<int:camera_number>")
def calibration_stream(camera_number):
    """Live MJPEG. The browser holds this open; the session's idle timeout is
    deferred by every frame served."""
    def frames():
        calibration_capture.SESSION.ensure_open()
        while True:
            frame = calibration_capture.SESSION.latest(camera_number)
            if frame is None:
                time.sleep(0.05)
                continue
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ok:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                       + buf.tobytes() + b"\r\n")
            time.sleep(1 / 15.0)   # 15 fps is plenty for focusing

    return Response(frames(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


@calibration_bp.route("/calibration/sharpness")
def calibration_sharpness():
    calibration_capture.SESSION.ensure_open()
    pair = calibration_capture.SESSION.latest_pair()
    if pair is None:
        return jsonify({"cam1": None, "cam2": None})
    return jsonify({
        "cam1": frame_analysis.sharpness_score(pair[1]),
        "cam2": frame_analysis.sharpness_score(pair[2]),
    })


@calibration_bp.route("/calibration/status")
def calibration_status():
    return jsonify({"pairs": _pair_count(),
                    "cameras_open": calibration_capture.SESSION.is_open()})


@calibration_bp.route("/calibration/capture", methods=["POST"])
def calibration_capture_pair():
    calibration_capture.SESSION.ensure_open()
    pair, skew = calibration_capture.SESSION.latest_pair_with_skew()
    if pair is None:
        return jsonify({"error": "no frames yet - cameras still starting"})

    dirs = _pair_dirs()
    index = _pair_count() + 1
    found = {}
    for n in (1, 2):
        found[n], _ = frame_analysis.find_board(pair[n])
        cv2.imwrite(os.path.join(dirs[n], "gs_{:02d}.png".format(index)), pair[n])

    return jsonify({"index": index, "found1": found[1], "found2": found[2],
                    "skew_ms": skew * 1000.0})


@calibration_bp.route("/calibration/release", methods=["POST"])
def calibration_release():
    calibration_capture.SESSION.release()
    return jsonify({"cameras_open": False})
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
scp -i ~/.ssh/jetsonlm_key sp4_gspro/calibration_page.py brain@192.168.178.194:~/JetsonLM/sp4_gspro/
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM/sp4_gspro && python3 -c 'import calibration_page; print(calibration_page.calibration_bp)'"
```

Expected: `<flask.blueprints.Blueprint object at 0x...>`

- [ ] **Step 3: Commit**

```bash
git add sp4_gspro/calibration_page.py
git commit -m "SP4: calibration page blueprint

Live MJPEG per camera with a sharpness readout, a capture button that reports
board detection per camera immediately, and an explicit release so pitrac_lm
can have the devices back. Separate module because dashboard.py is already
around 1400 lines."
git push origin main
```

---

### Task 9: Mount the page into the dashboard

**Files:**
- Modify: `sp4_gspro/dashboard.py` (imports near line 32, nav at lines 330-335, `main()` near line 1349)

- [ ] **Step 1: Register the blueprint**

In `sp4_gspro/dashboard.py`, after the existing sibling imports:

```python
from shot_db import ShotDB
from ball_physics import compute_flight
```

add:

```python
from calibration_page import calibration_bp
```

and immediately after `app = Flask(__name__)`:

```python
app = Flask(__name__)
app.register_blueprint(calibration_bp)
db = None  # initialized in main()
```

- [ ] **Step 2: Add the nav link**

In `DASHBOARD_HTML`, replace the tab row at lines 330-335:

```html
<div class="tabs">
  <div class="tab active" onclick="showTab('home')">Dashboard</div>
  <div class="tab" onclick="showTab('sessions')">Sessions</div>
  <div class="tab" onclick="showTab('clubs')">Club Averages</div>
  <div class="tab" onclick="showTab('dispersion')">Dispersion</div>
  <div class="tab" onclick="showTab('compare')">Compare</div>
```

with:

```html
<div class="tabs">
  <div class="tab active" onclick="showTab('home')">Dashboard</div>
  <div class="tab" onclick="showTab('sessions')">Sessions</div>
  <div class="tab" onclick="showTab('clubs')">Club Averages</div>
  <div class="tab" onclick="showTab('dispersion')">Dispersion</div>
  <div class="tab" onclick="showTab('compare')">Compare</div>
  <a class="tab" href="/calibration" style="text-decoration:none">Calibration</a>
```

- [ ] **Step 3: Restart the service and check both pages respond**

```bash
scp -i ~/.ssh/jetsonlm_key sp4_gspro/dashboard.py brain@192.168.178.194:~/JetsonLM/sp4_gspro/
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "sudo systemctl restart jetson-lm-dashboard && sleep 3 && systemctl is-active jetson-lm-dashboard && curl -s -o /dev/null -w 'dashboard %{http_code}\n' http://localhost:5000/ && curl -s -o /dev/null -w 'calibration %{http_code}\n' http://localhost:5000/calibration"
```

Expected:
```
active
dashboard 200
calibration 200
```

If the service fails, read the reason before changing anything:

```bash
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "journalctl -u jetson-lm-dashboard -n 40 --no-pager"
```

- [ ] **Step 4: Confirm the live stream serves frames**

```bash
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "timeout 5 curl -s http://localhost:5000/calibration/stream/1 | wc -c; curl -s http://localhost:5000/calibration/sharpness"
```

Expected: a byte count well above 100000, then a JSON object with two non-null numbers.

- [ ] **Step 5: Hand the cameras back**

```bash
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "curl -s -X POST http://localhost:5000/calibration/release; echo; curl -s http://localhost:5000/calibration/status"
```

Expected: `{"cameras_open":false}` then a status showing `cameras_open: false`.

- [ ] **Step 6: Commit**

```bash
git add sp4_gspro/dashboard.py
git commit -m "SP4: mount the calibration page in the dashboard

Calibration is not a one-off - every mount adjustment invalidates it - so it
belongs behind a link in the UI that already runs, not a remembered command."
git push origin main
```

---

### Task 10: Patch CameraCalibration.py for our hardware

**Files:**
- Modify: `Software/CalibrateCameraDistortions/CameraCalibration.py`

- [ ] **Step 1: Replace the script**

Replace the entire contents of `Software/CalibrateCameraDistortions/CameraCalibration.py` with:

```python
#!/usr/bin/env python3
"""Camera calibration for the Jetson LM.

Derived from PiTrac's original, with four changes:
  - resolution is a parameter, not 1456x1088 baked in for the IMX296
  - image paths are arguments, not hardcoded globs
  - reprojection error is reported per image, so outliers can be dropped
  - the sub-pixel refined corners are actually used; the original computed
    cornerSubPix and then appended the coarse corners, discarding it

Output is a JSON block in golf_sim_config.json's shape, rather than .txt
files whose 3x3 matrix and 5-vector have to be transcribed by hand.

    python3 CameraCalibration.py --images ../../sp1_vision/calibration_images/cam1 \
                                 --label Camera1
"""

import argparse
import glob
import json
import os
import sys

import cv2 as cv
import numpy as np

CHESSBOARD_SIZE = (9, 6)
SUBPIX_CRITERIA = (cv.TERM_CRITERIA_EPS + cv.TERM_CRITERIA_MAX_ITER, 30, 0.001)

# Square size only scales the translation vectors; the camera matrix and the
# distortion coefficients are unaffected. It is set for completeness, not
# because the print has to be exact.
SQUARE_SIZE_MM = 20.0

# OV9281: 1/4", 1280x800, 3.0 um square pixels.
PIXEL_PITCH_MM = 0.003


def object_points():
    objp = np.zeros((CHESSBOARD_SIZE[0] * CHESSBOARD_SIZE[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:CHESSBOARD_SIZE[0], 0:CHESSBOARD_SIZE[1]].T.reshape(-1, 2)
    return objp * SQUARE_SIZE_MM


def collect(image_dir):
    """Return (objpoints, imgpoints, size, used_files, skipped_files)."""
    files = sorted(glob.glob(os.path.join(image_dir, "*.png")))
    if not files:
        raise SystemExit("no PNGs found in " + image_dir)

    objp = object_points()
    objpoints, imgpoints, used, skipped = [], [], [], []
    size = None

    for path in files:
        img = cv.imread(path, cv.IMREAD_GRAYSCALE)
        if img is None:
            skipped.append((path, "unreadable"))
            continue
        if size is None:
            size = (img.shape[1], img.shape[0])
        elif (img.shape[1], img.shape[0]) != size:
            skipped.append((path, "size {}x{} differs from {}x{}".format(
                img.shape[1], img.shape[0], size[0], size[1])))
            continue

        found, corners = cv.findChessboardCorners(img, CHESSBOARD_SIZE, None)
        if not found:
            skipped.append((path, "no board"))
            continue
        # Use the refined corners. The original discarded them.
        corners = cv.cornerSubPix(img, corners, (11, 11), (-1, -1), SUBPIX_CRITERIA)
        objpoints.append(objp)
        imgpoints.append(corners)
        used.append(path)

    return objpoints, imgpoints, size, used, skipped


def per_image_errors(objpoints, imgpoints, rvecs, tvecs, mtx, dist):
    errors = []
    for i in range(len(objpoints)):
        projected, _ = cv.projectPoints(objpoints[i], rvecs[i], tvecs[i], mtx, dist)
        errors.append(cv.norm(imgpoints[i], projected, cv.NORM_L2) / len(projected))
    return errors


def config_block(label, mtx, dist):
    """Emit the two golf_sim_config.json keys, ready to paste."""
    return json.dumps({
        "kCamera{}CalibrationMatrix".format(label): [
            ["{:.12f}".format(v) for v in row] for row in mtx
        ],
        "kCamera{}DistortionVector".format(label): [
            "{:.12f}".format(v) for v in dist.ravel()
        ],
    }, indent=2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", required=True,
                        help="directory of checkerboard PNGs")
    parser.add_argument("--label", default="1",
                        help="camera label for the config keys, 1 or 2")
    parser.add_argument("--save-npz",
                        help="write intrinsics here for the stereo step")
    parser.add_argument("--undistort-check", metavar="PNG",
                        help="write an original|undistorted side-by-side here, "
                             "so the result can be judged by eye")
    args = parser.parse_args(argv)

    objpoints, imgpoints, size, used, skipped = collect(args.images)
    print("using {} images at {}x{}".format(len(used), size[0], size[1]))
    for path, why in skipped:
        print("  skipped {}: {}".format(os.path.basename(path), why))
    if len(used) < 8:
        raise SystemExit("need at least 8 usable images, got {}".format(len(used)))

    rms, mtx, dist, rvecs, tvecs = cv.calibrateCamera(
        objpoints, imgpoints, size, None, None)

    errors = per_image_errors(objpoints, imgpoints, rvecs, tvecs, mtx, dist)
    print("\nreprojection error per image:")
    for path, err in sorted(zip(used, errors), key=lambda p: -p[1]):
        flag = "  <- outlier, consider removing" if err > 0.5 else ""
        print("  {:<28} {:.4f}{}".format(os.path.basename(path), err, flag))
    print("\n  mean {:.4f} px      RMS {:.4f} px".format(float(np.mean(errors)), rms))

    fx, fy = mtx[0, 0], mtx[1, 1]
    print("\nfx {:.2f} px   fy {:.2f} px   fy/fx {:.4f}".format(fx, fy, fy / fx))
    print("focal length  fx x {:.4f} mm/px = {:.3f} mm".format(
        PIXEL_PITCH_MM, fx * PIXEL_PITCH_MM))
    print("              fy x {:.4f} mm/px = {:.3f} mm".format(
        PIXEL_PITCH_MM, fy * PIXEL_PITCH_MM))
    print("sensor        {:.3f} x {:.3f} mm".format(
        size[0] * PIXEL_PITCH_MM, size[1] * PIXEL_PITCH_MM))
    if abs(fy / fx - 1.0) > 0.01:
        print("\nWARNING: fx and fy differ by more than 1%. The 3.0 um square-pixel")
        print("         assumption may be wrong - do not write these to config yet.")

    if args.undistort_check:
        # Numbers can look fine while the result is wrong. Straight edges
        # being straight is the check a person can actually make.
        sample = cv.imread(used[0])
        h, w = sample.shape[:2]
        newmtx, _ = cv.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1, (w, h))
        mapx, mapy = cv.initUndistortRectifyMap(
            mtx, dist, None, newmtx, (w, h), cv.CV_16SC2)
        rectified = cv.remap(sample, mapx, mapy, cv.INTER_LINEAR)
        cv.imwrite(args.undistort_check, np.hstack([sample, rectified]))
        print("\nundistortion check written to {}".format(args.undistort_check))
        print("  left is the original, right is undistorted. The board's rows")
        print("  and columns must be straight on the right, and the squares")
        print("  the same size across the frame.")

    print("\ngolf_sim_config.json block:\n")
    print(config_block(args.label, mtx, dist))

    if args.save_npz:
        np.savez(args.save_npz, mtx=mtx, dist=dist, size=size,
                 objpoints=np.array(objpoints), imgpoints=np.array(imgpoints))
        print("\nintrinsics saved to " + args.save_npz)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify it runs against the shipped fixture**

The single shipped image is not enough to calibrate, so this only confirms the script loads, finds a board, and refuses honestly.

```bash
scp -i ~/.ssh/jetsonlm_key Software/CalibrateCameraDistortions/CameraCalibration.py brain@192.168.178.194:~/JetsonLM/Software/CalibrateCameraDistortions/
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM/Software/CalibrateCameraDistortions && mkdir -p /tmp/onefix && cp checkerboard_test_image_for_undistortion.png /tmp/onefix/ && python3 CameraCalibration.py --images /tmp/onefix --label 1; true"
```

Expected: `using 1 images at 1456x1088` then `need at least 8 usable images, got 1`.

- [ ] **Step 3: Commit**

```bash
git add Software/CalibrateCameraDistortions/CameraCalibration.py
git commit -m "SP1: rework CameraCalibration.py for the OV9281

Resolution and paths become arguments instead of IMX296 constants, error is
reported per image so outliers can be dropped, output is a pasteable config
block, and the sub-pixel refined corners are actually used - the original
computed cornerSubPix at line 51 and appended the coarse corners at line 52.

Also reports fx x 3.0 um, which is the measured focal length the whole
calibration exists to obtain, and warns when fx and fy disagree by more than
1% since that would falsify the square-pixel assumption."
git push origin main
```

---

### Task 11: Stereo extrinsics

**Files:**
- Create: `Software/CalibrateCameraDistortions/StereoCalibration.py`

- [ ] **Step 1: Write the implementation**

Create `Software/CalibrateCameraDistortions/StereoCalibration.py`:

```python
#!/usr/bin/env python3
"""Stereo extrinsics for the Jetson LM camera pair.

Consumes the two per-camera .npz files written by CameraCalibration.py
--save-npz, plus the paired image directories, and reports the rotation and
translation between the cameras.

The CAD says the baseline is 80.00 mm with parallel optical axes
(Hardware/JetsonLM.step). This measures the same thing independently, which
makes it a check on the calibration and on the physical mount at once.

    python3 StereoCalibration.py --cam1-npz cam1.npz --cam2-npz cam2.npz \
        --cam1-images ../../sp1_vision/calibration_images/cam1 \
        --cam2-images ../../sp1_vision/calibration_images/cam2
"""

import argparse
import glob
import math
import os
import sys

import cv2 as cv
import numpy as np

from CameraCalibration import (CHESSBOARD_SIZE, SUBPIX_CRITERIA, object_points)

CAD_BASELINE_MM = 80.00


def paired_corners(dir1, dir2):
    """Find boards in both images of each pair, keeping only complete pairs."""
    names1 = {os.path.basename(p) for p in glob.glob(os.path.join(dir1, "*.png"))}
    names2 = {os.path.basename(p) for p in glob.glob(os.path.join(dir2, "*.png"))}
    shared = sorted(names1 & names2)
    if not shared:
        raise SystemExit("no image pairs share a filename between the two dirs")

    objp = object_points()
    objpoints, pts1, pts2, used, dropped = [], [], [], [], []
    size = None

    for name in shared:
        img1 = cv.imread(os.path.join(dir1, name), cv.IMREAD_GRAYSCALE)
        img2 = cv.imread(os.path.join(dir2, name), cv.IMREAD_GRAYSCALE)
        if img1 is None or img2 is None:
            dropped.append((name, "unreadable"))
            continue
        if size is None:
            size = (img1.shape[1], img1.shape[0])

        ok1, c1 = cv.findChessboardCorners(img1, CHESSBOARD_SIZE, None)
        ok2, c2 = cv.findChessboardCorners(img2, CHESSBOARD_SIZE, None)
        if not (ok1 and ok2):
            dropped.append((name, "board missing in cam{}".format(
                1 if not ok1 else 2)))
            continue

        pts1.append(cv.cornerSubPix(img1, c1, (11, 11), (-1, -1), SUBPIX_CRITERIA))
        pts2.append(cv.cornerSubPix(img2, c2, (11, 11), (-1, -1), SUBPIX_CRITERIA))
        objpoints.append(objp)
        used.append(name)

    return objpoints, pts1, pts2, size, used, dropped


def rotation_to_euler_degrees(R):
    """Return (roll, pitch, yaw) in degrees.

    Camera frame: X along the baseline, Y down, Z forward. Yaw is toe-in/out
    and feeds horizontal disparity, which rectification absorbs as an offset.
    Roll and pitch produce vertical disparity - that is what makes
    correspondence search two-dimensional, so those are the ones to watch.
    """
    sy = math.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
    if sy > 1e-6:
        roll = math.atan2(R[2, 1], R[2, 2])
        pitch = math.atan2(-R[2, 0], sy)
        yaw = math.atan2(R[1, 0], R[0, 0])
    else:
        roll = math.atan2(-R[1, 2], R[1, 1])
        pitch = math.atan2(-R[2, 0], sy)
        yaw = 0.0
    return tuple(math.degrees(a) for a in (roll, pitch, yaw))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cam1-npz", required=True)
    parser.add_argument("--cam2-npz", required=True)
    parser.add_argument("--cam1-images", required=True)
    parser.add_argument("--cam2-images", required=True)
    args = parser.parse_args(argv)

    k1 = np.load(args.cam1_npz)
    k2 = np.load(args.cam2_npz)

    objpoints, pts1, pts2, size, used, dropped = paired_corners(
        args.cam1_images, args.cam2_images)
    print("using {} complete pairs".format(len(used)))
    for name, why in dropped:
        print("  dropped {}: {}".format(name, why))
    if len(used) < 8:
        raise SystemExit("need at least 8 complete pairs, got {}".format(len(used)))

    # Intrinsics are already measured and trusted; solve only for the pose.
    rms, _, _, _, _, R, T, _, _ = cv.stereoCalibrate(
        objpoints, pts1, pts2,
        k1["mtx"], k1["dist"], k2["mtx"], k2["dist"], size,
        criteria=SUBPIX_CRITERIA,
        flags=cv.CALIB_FIX_INTRINSIC,
    )

    baseline = float(np.linalg.norm(T))
    roll, pitch, yaw = rotation_to_euler_degrees(R)
    fx = float(k1["mtx"][0, 0])

    print("\nstereo RMS         {:.4f} px".format(rms))
    print("baseline           {:.2f} mm   (CAD says {:.2f} mm, delta {:+.2f} mm)".format(
        baseline, CAD_BASELINE_MM, baseline - CAD_BASELINE_MM))
    print("translation        [{:.2f}, {:.2f}, {:.2f}] mm".format(*T.ravel()))
    print("\nrelative rotation")
    print("  roll  {:+.3f} deg   vertical disparity, watch this".format(roll))
    print("  pitch {:+.3f} deg   vertical disparity, watch this".format(pitch))
    print("  yaw   {:+.3f} deg   toe-in/out, absorbed as a disparity offset".format(yaw))

    worst = max(abs(roll), abs(pitch))
    shift = fx * math.tan(math.radians(worst))
    print("\nworst vertical misalignment {:.3f} deg -> {:.1f} px shift".format(
        worst, shift))
    print("rectification crops roughly {:.1f}% of frame height".format(
        100.0 * shift / 800.0))
    if worst < 3.0:
        print("-> under 3 deg, no action needed")
    else:
        print("-> over 3 deg, consider shimming before accepting this calibration")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify it loads and reports honestly with no data**

```bash
scp -i ~/.ssh/jetsonlm_key Software/CalibrateCameraDistortions/StereoCalibration.py brain@192.168.178.194:~/JetsonLM/Software/CalibrateCameraDistortions/
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM/Software/CalibrateCameraDistortions && python3 StereoCalibration.py --help | head -5"
```

Expected: the usage line and the first lines of the docstring, no import error.

- [ ] **Step 3: Commit**

```bash
git add Software/CalibrateCameraDistortions/StereoCalibration.py
git commit -m "SP1: stereo extrinsics from the same image pairs

Solves with CALIB_FIX_INTRINSIC since the per-camera matrices are already
measured, and reports the result against the CAD: 80.00 mm baseline with
parallel axes. Rotation is decomposed into roll/pitch/yaw because they are
not equally costly - yaw is absorbed as a disparity offset, roll and pitch
produce vertical disparity and cost frame height in rectification."
git push origin main
```

---

### Task 12: Bind cameras by port path in the C++ startup

The Python side is safe from Task 1. The runtime path is not.

**Files:**
- Modify: `Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp:772-790`

- [ ] **Step 1: Replace the hardcoded device paths**

In `PerformCameraSystemStartup`, replace:

```cpp
        // OV9281 device mapping confirmed in LOGBOOK 2026-03-21:
        //   /dev/video0  → camera 1 (USB bus xhci-2.2.4)
        //   /dev/video2  → camera 2 (USB bus xhci-2.3)
        // /dev/video1 and /dev/video3 are UVC metadata devices and are skipped.
        static const char* kSlot0Path = "/dev/video0";
        static const char* kSlot1Path = "/dev/video2";
```

with:

```cpp
        // Bind by USB port path, never by /dev/videoN.
        //
        // Both B0332 modules report iSerial "UC762" - Arducam's SKU code, not
        // a per-unit serial - so /dev/v4l/by-id/ collides and the device
        // numbers are handed out in enumeration order. If the two swap, the
        // stereo baseline changes sign and depth comes out mirrored with
        // nothing visibly wrong in either image.
        //
        // This has already happened: the previous comment here recorded the
        // cameras on xhci-2.2.4 and xhci-2.3; by 2026-08-06 they enumerated
        // on 2.3 and 2.4. The port is the identity, so the socket a cable is
        // in must not change. Mirrored in sp1_vision/camera_paths.py.
        static const char* kSlot0Path =
            "/dev/v4l/by-path/platform-3610000.xhci-usb-0:2.3:1.0-video-index0";
        static const char* kSlot1Path =
            "/dev/v4l/by-path/platform-3610000.xhci-usb-0:2.4:1.0-video-index0";
```

If Task 2 swapped the mapping in `camera_paths.py`, swap these two the same way.

- [ ] **Step 2: Build on the Jetson**

```bash
scp -i ~/.ssh/jetsonlm_key Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp brain@192.168.178.194:~/JetsonLM/Software/LMSourceCode/ImageProcessing/
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "cd ~/JetsonLM/Software/LMSourceCode/ImageProcessing && ninja -C build_jetson 2>&1 | tail -15"
```

Expected: a successful link, ending in something like `[N/N] Linking target pitrac_lm`.

- [ ] **Step 3: Confirm both cameras still probe**

Release the dashboard's hold on the devices first, or this will fail for the wrong reason.

```bash
ssh -i ~/.ssh/jetsonlm_key brain@192.168.178.194 "curl -s -X POST http://localhost:5000/calibration/release >/dev/null; cd ~/JetsonLM/Software/LMSourceCode/ImageProcessing && timeout 20 ./build_jetson/pitrac_lm --system_mode=camera1_test_standalone --msg_broker_address=tcp://127.0.0.1:61616 --logging_level=trace 2>&1 | grep -iE 'Probed|probe_v4l2|by-path|not a capture' | head"
```

Expected: two `Probed /dev/v4l/by-path/...` lines naming `card="Arducam OV9281 USB Camera"`.

- [ ] **Step 4: Commit**

```bash
git add Software/LMSourceCode/ImageProcessing/v4l2_interface.cpp
git commit -m "SP1: bind cameras by USB port path in PerformCameraSystemStartup

The two modules are indistinguishable by USB serial, so /dev/videoN is the
only thing separating them and it is assigned in enumeration order. The ports
recorded in the old comment had already drifted from 2.2.4/2.3 to 2.3/2.4.
Mirrors sp1_vision/camera_paths.py."
git push origin main
```

---

## Phase 2 — the measurement run

Not a coding task. Once Tasks 1-12 are green, the sequence is:

1. Print `Software/CalibrateCameraDistortions/checkerboard.png` (9×6 inner corners). Do not let the printer scale it to fit the page — the squares must stay square. The absolute size does not matter.
2. Open `http://<jetson-ip>:5000/calibration`. Focus each lens by watching its score peak.
3. Capture around 20 pairs, the board at working distance, reaching the image corners as well as the centre, in ordinary room light. Retake any pair that does not report a board in both cameras.
4. Run the two analysis scripts:

```bash
cd ~/JetsonLM/Software/CalibrateCameraDistortions
python3 CameraCalibration.py --images ../../sp1_vision/calibration_images/cam1 --label 1 \
    --save-npz /tmp/cam1.npz --undistort-check /tmp/undistort_cam1.png
python3 CameraCalibration.py --images ../../sp1_vision/calibration_images/cam2 --label 2 \
    --save-npz /tmp/cam2.npz --undistort-check /tmp/undistort_cam2.png
python3 StereoCalibration.py --cam1-npz /tmp/cam1.npz --cam2-npz /tmp/cam2.npz \
    --cam1-images ../../sp1_vision/calibration_images/cam1 \
    --cam2-images ../../sp1_vision/calibration_images/cam2
```

5. Check against the spec's acceptance criteria: mean reprojection error ≤ 0.5 px, `fx ≈ fy` within 1%, `fx × 3.0 µm` compared against the derived 2.74 mm, measured baseline against the CAD's 80.00 mm, and relative roll/pitch under 3°.
6. Look at `/tmp/undistort_cam1.png` and `/tmp/undistort_cam2.png`. The board's rows and columns must be straight on the right-hand side and the squares the same size across the frame. Numbers can look reasonable while the result is wrong; this is the check a person can actually make.

Phase 4 — writing the results into `golf_sim_config.json` and the `sensor_width_override_` / `sensor_height_override_` statics — gets its own plan, because what it writes depends on what this measures.

**Before any run involving the strobe:** the Jetson's `golf_sim_config.json` still carries the Phase C bench values, `kBaudRateForFastPulses` 1000 and `number_bits_for_fast_on_pulse_` 32, which stretch the strobe to 32 ms pulses so the LED is visible. Production is 115200 and 2, giving 17 µs. Calibration does not involve the strobe, so this does not affect the measurement — but it must be restored before the first real shot.
