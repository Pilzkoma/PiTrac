# Ball Marks Part 2 - Mark Detection and Ball Orientation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From one strobe-lit ball image and the ball's centre in that camera's frame, find the marks, identify them on the map and return the ball's absolute orientation - or refuse.

**Architecture:** Five focused modules in `sp1_vision`: the map as arrays (`mark_map`), the visible cap unwrapped onto the sphere with a perspective model (`ball_unwrap`), mark blobs and their shapes (`mark_detect`), identification and pose (`ball_orientation`), and an offline check tool (`orientation_check`) that measures the acceptance cases on real recordings. A synthetic renderer of a marked ball (`tests/render_ball.py`) gives exact ground truth for the unit tests; real frames give the acceptance.

**Tech Stack:** Python 3, numpy, OpenCV. No new libraries (no scipy: Kabsch with `np.linalg.svd`).

**Spec:** `docs/superpowers/specs/2026-11-13-ball-marks-spin-design.md` (part 2; owner decisions 2 and 4). Test evidence for the front end: `sp1_vision/strobe_runs/2026-11-18_thin_print/results.txt`.

## Global Constraints

- Target platform Jetson: Python 3.8.10, OpenCV 4.5.4, numpy 1.17.4 - nothing newer (no walrus, no `math.dist`, no OpenCV-5-only calls). Windows has Python 3.14 / numpy 2.5 / OpenCV 5 for quick runs; the Jetson run is the one that counts (`.superpowers/sdd/2026-08-09-stereo-triangulation-block1/run-tests`, fix its `JET=` to `brain@192.168.178.43` first; it syncs `sp1_vision/*.py`, `tests/*.py` and `tests/fixtures/ball_pairs` - add `tests/fixtures/marked_ball` to its fixture sync).
- Tests `unittest`, run from the repo root: `python -m unittest sp1_vision.tests.<module> -v`.
- The map is read only from `sp1_vision/ball_marks/ball_mark_map.json` (single source, spec anti-goal "two hand-maintained copies"). Its conventions block is authoritative: per site `normal`, `north`, `east` (east × north = normal), `outline_mm` on the plane tangent at the shell's inner radius 21.45 mm, ink = that outline projected centrally onto the ball (scale 21.335 / 21.45 = 0.995); bars along `bar_to`; cross arms along north and east; `neighbours` counter-clockwise seen from outside.
- Ball radius `BALL_RADIUS_MM = 21.335`.
- Orientation `R` is a proper rotation (det +1) mapping **map (stencil) frame → camera frame**: `n_cam = R @ n_map`. Camera frames are OpenCV (X right, Y down, Z forward); camera 2 → camera 1: `R_cam1 = rig.r.T @ R_cam2` (`X2 = rig.r @ X1 + rig.t_m`).
- Front end fixed by the 2026-11-18 test: unwrap at **4.69 px per mm of arc** (`R_OUT_PX = 100` for the ball radius), dark = grey < **0.6** × local ball brightness, **2.0 mm** opening on the unwrapped sphere (never in the image plane), marks evaluated only with centroid ≤ **60°** from the view centre.
- Refuse rather than guess (spec owner decision 2): blobs that do not fit the map are clutter; an ambiguous or under-determined identification returns a refusal with a reason, never a pose.
- `CLAUDE.md`: approach agreed (this plan); commit per task; never `git stash`.

## Review Focus

1. **Ball partly outside the image** (flight frames at the edge): unwrapped pixels whose source lies outside the frame must be invalid, not border-replicated (the 2026-11-18 test script replicated the border). Test in Task 2.
2. **Dim ball / brightness gradient** (ball leaving the IR beam, dim lower limb - the 2026-11-18 putts merged limb shading with marks in cam2): detection must not turn shading into ink. Test in Task 3 (rendered gradient) and Task 5 (fixture `limb_cam2_t044.9315.jpg`).
3. **Specular highlight on a mark** punches a hole (2026-11-18, cam1 16.09 s, 98.08 s): the mark must still classify. Test in Task 3 (rendered glint).
4. **Mirror solution**: two-vector or SVD fits can return det −1; a reflected pose must never be reported. Test in Task 4.
5. **Too few or contradictory marks** (only two visible, or a wrong-shape blob where the pose predicts a mark): refuse, never a pose. Test in Task 4.

---

### Task 1: Map as arrays and a synthetic marked-ball renderer

**Files:**
- Create: `sp1_vision/mark_map.py`
- Create: `sp1_vision/tests/render_ball.py` (test helper, not a test module)
- Test: `sp1_vision/tests/test_mark_map.py`

**Interfaces:**
- Produces:
  - `BALL_RADIUS_MM = 21.335`, `MAP_PATH = "sp1_vision/ball_marks/ball_mark_map.json"`
  - `class MarkMap` with `normals (20,3)`, `shapes` (list of `"dot"|"bar"|"cross"`), `directions (20,3)` - unit tangent per site: bars towards `bar_to` (projected into the tangent plane), crosses `east`, dots zeros; `neighbours` (list of 3-lists), `outlines_mm` (list of `(k,2)` arrays, (east, north) at radius 21.45), `east`, `north` `(20,3)`, `ink_area_mm2` `{"dot": a, "bar": a, "cross": a}` (polygon area of `outline_mm` × 0.995²), `neighbour_angle_deg` (mean angle between neighbouring normals).
  - `load_map(path=MAP_PATH) -> MarkMap`
  - `render_ball(mmap, K, dist, centre_cam_m, R, size=(1280, 800), ball_grey=200, ink_grey=40, background=15, gradient=None, glint=None, line=None) -> np.ndarray uint8` in `tests/render_ball.py`: ray-sphere intersection per pixel (undistort the pixel grid once with `cv2.undistortPoints`); a surface point is ink if, mapped back to the map frame (`R.T @ n`), its central projection onto the tangent plane of the nearest site (within 20°) at radius 21.45 lies inside that site's `outline_mm` polygon (`cv2.pointPolygonTest`). `gradient=(direction_xy, factor)` multiplies ball brightness linearly across the ball down to `factor`; `glint=(normal_cam, radius_mm)` sets 255 inside; `line=(normal_a, normal_b, width_mm, grey)` draws a great-circle arc as a thin stroke. Output then blurred with a 3×3 Gaussian.

- [ ] **Step 1: Failing tests**

```python
def test_sites_and_shapes(self):
    m = mark_map.load_map()
    self.assertEqual(m.normals.shape, (20, 3))
    self.assertEqual([m.shapes.count(s) for s in ("dot", "bar", "cross")], [5, 10, 5])
    np.testing.assert_allclose(np.linalg.norm(m.normals, axis=1), 1, atol=1e-9)

def test_directions_tangent(self):
    m = mark_map.load_map()
    for i, s in enumerate(m.shapes):
        if s != "dot":
            self.assertAlmostEqual(float(m.directions[i] @ m.normals[i]), 0, places=9)
            self.assertAlmostEqual(float(np.linalg.norm(m.directions[i])), 1, places=9)

def test_ink_areas(self):
    a = mark_map.load_map().ink_area_mm2
    self.assertAlmostEqual(a["dot"], 38.0, delta=0.6)     # 32-gon of 7 mm, x 0.995^2
    self.assertAlmostEqual(a["bar"], 38.1, delta=0.3)     # 11 x 3.5
    self.assertAlmostEqual(a["cross"], 57.2, delta=0.3)   # 2 x 10 x 3.5 - 3.5^2

def test_neighbour_angle(self):
    self.assertAlmostEqual(mark_map.load_map().neighbour_angle_deg, 41.81, delta=0.05)

def test_renderer_puts_ink_at_the_site(self):
    # K from the repo calibration (stereo_geometry.load_rig().k1), ball 0.45 m ahead,
    # R chosen so site 0 faces the camera: the pixel of the ball centre is ink.
```

- [ ] **Step 2: Run, expect FAIL** (module not found).
- [ ] **Step 3: Implement** `mark_map.py` and `tests/render_ball.py`.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** - `git commit -m "mark_map: the mark map as arrays; test renderer for a marked ball"`

### Task 2: Perspective unwrap of the visible cap

**Files:**
- Create: `sp1_vision/ball_unwrap.py`
- Test: `sp1_vision/tests/test_ball_unwrap.py`

**Interfaces:**
- Consumes: `mark_map.BALL_RADIUS_MM`.
- Produces:
  - `R_OUT_PX = 100`, `PX_PER_MM = R_OUT_PX / BALL_RADIUS_MM` (4.687), `MAX_DEG = 70.0`
  - `class Unwrapped` with `image (H,W) uint8`, `valid (H,W) bool`, `theta_deg (H,W)`, `basis (3,3)` rows `w, e1, e2` (w = unit vector from ball centre towards the camera; e1 = camera x made orthogonal to w; e2 = w × e1), `centre_cam_m (3,)`.
  - `unwrap(gray, K, dist, centre_cam_m) -> Unwrapped` - output pixel at offset (x, y) from the middle: θ = hypot/R_OUT_PX, φ = atan2(y, x); surface normal `n = cos θ w + sin θ (cos φ e1 + sin φ e2)`; point `centre + r n` projected with `cv2.projectPoints` (K, dist); sampled with `cv2.remap(..., INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=0)`; `valid` = θ ≤ MAX_DEG **and** the source pixel inside the frame with a 2 px margin (Review Focus 1).
  - `normal_at(u: Unwrapped, x: float, y: float) -> np.ndarray(3)` - unit normal in the camera frame for an unwrapped pixel.
  - `tangent_at(u: Unwrapped, x: float, y: float, dx: float, dy: float) -> np.ndarray(3)` - unit tangent on the sphere for an unwrapped direction at that pixel.
  - `centre_from_circle(K, dist, uv, radius_px) -> np.ndarray(3)` - monocular ball centre: undistorted ray through `uv`, range from `radius_px` (`range = fx * r / radius_px`, the inverse of `ball_pair.apparent_radius_px`), for frames where stereo is missing.

- [ ] **Step 1: Failing tests** (all with the renderer from Task 1)

```python
def test_site_lands_where_predicted(self):
    # render with site 3 at 30 deg from the view centre; unwrap; the dark blob's
    # centroid, through normal_at, is within 0.5 deg of R @ normals[3]

def test_roundtrip_normal(self):
    # for 20 random (theta<=60, phi) pixels: normal_at gives n with angle(n, w) == theta within 0.05 deg

def test_widths_equal_at_centre_and_limb(self):
    # a 3.5 mm wide bar rendered at 5 deg and at 55 deg: its width in the unwrapped
    # image (min-area rect short side / PX_PER_MM) is 3.5 +- 0.4 mm in both

def test_out_of_frame_is_invalid(self):                 # Review Focus 1
    # ball centre projected 20 px inside the right image edge: the part of the cap
    # beyond the edge is valid == False and image == 0 there

def test_centre_from_circle(self):
    # a ball rendered at (0.05, 0.08, 0.45): centre_from_circle on its true circle
    # (projected centre, apparent radius) is within 3 mm
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** `ball_unwrap.py`.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** - `git commit -m "ball_unwrap: perspective unwrap of the visible cap onto the sphere"`

### Task 3: Mark blobs and shapes

**Files:**
- Create: `sp1_vision/mark_detect.py`
- Test: `sp1_vision/tests/test_mark_detect.py`

**Interfaces:**
- Consumes: `ball_unwrap.Unwrapped`, `normal_at`, `tangent_at`, `PX_PER_MM`; `mark_map.MarkMap.ink_area_mm2`.
- Produces:
  - Constants: `DARK_RATIO = 0.6`, `BRIGHTNESS_DISC_MM = 8.0` (grey closing for the local ball brightness - larger than the 7 mm dot, smaller than the 12 mm the test used, which over-estimated brightness at the dim limb), `GLINT_HOLE_MM2 = 6.0`, `OPEN_MM = 2.0`, `EVAL_DEG = 60.0`, `MIN_AREA_MM2 = 8.0`, `AREA_BAND = (0.6, 1.5)` (× the map's ink area), `ELONGATED = 1.8` (major/minor axis of the blob's second moments), `ROUND = 1.5`, `SOLID = 0.85` (area / convex-hull area).
  - `class MarkBlob` with `normal (3,)` (camera frame, from the blob centroid), `shape` (`"dot"|"bar"|"cross"|None`), `direction (3,)` or `None` (bar: major axis as a sphere tangent; cross: the arm direction, see below), `area_mm2`, `theta_deg`, `elongation`, `solidity`.
  - `dark_mask(u: Unwrapped) -> np.ndarray uint8` - ratio test against `cv2.morphologyEx(MORPH_CLOSE, disc BRIGHTNESS_DISC_MM)` then Gaussian σ 3 px, only on `valid`; then fill holes inside dark components smaller than `GLINT_HOLE_MM2` (glints, Review Focus 3).
  - `detect_marks(u: Unwrapped, mmap: MarkMap) -> list[MarkBlob]` - `dark_mask`, opening with a disc of `OPEN_MM`, connected components ≥ `MIN_AREA_MM2`, centroid θ ≤ `EVAL_DEG`, then classification:
    - dot: area in band of `dot`, elongation < `ROUND`, solidity ≥ `SOLID`;
    - bar: area in band of `bar`, elongation ≥ `ELONGATED`;
    - cross: area in band of `cross`, elongation < `ROUND`, solidity < `SOLID`;
    - else `None` (clutter, still returned so the identifier can see conflicts).
    Cross direction: the angle α (mod 90°) maximising the blob's pixel count along the two lines through the centroid at α and α+90° (1° steps); turned into a tangent with `tangent_at`.

- [ ] **Step 1: Failing tests** (renderer, ball at 0.45 m, several rotations)

```python
def test_each_shape_classified_up_to_55deg(self):
    # for rotations putting a dot, a bar and a cross at 0, 30 and 55 deg from the view
    # centre: the blob nearest each site has the right shape; bar direction within 10 deg
    # of R @ directions[site] (mod 180), cross within 10 deg (mod 90)

def test_thin_line_through_a_cross_is_ignored(self):
    # line=(cross site, its neighbour, 1.0 mm, ink_grey): still one blob there, shape cross

def test_thick_print_is_clutter(self):
    # paint a filled 4 x 4 mm square (ink_grey) into the Unwrapped image at theta 20 deg,
    # away from all marks: its blob has shape None (16 mm^2 is under every area band)

def test_glint_on_cross(self):                          # Review Focus 3
    # glint of radius 1.0 mm at the cross centre: still classified cross

def test_gradient_does_not_create_ink(self):            # Review Focus 2
    # gradient to 0.35 x brightness across the ball, no marks inside 60 deg on the dim
    # side except the rendered ones: no blob with shape None and area >= 20 mm^2
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** `mark_detect.py`.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** - `git commit -m "mark_detect: dark blobs on the unwrapped ball, thin print removed, shapes classified"`

### Task 4: Identification and pose

**Files:**
- Create: `sp1_vision/ball_orientation.py`
- Test: `sp1_vision/tests/test_ball_orientation.py`

**Interfaces:**
- Consumes: `mark_detect.MarkBlob`, `mark_map.MarkMap`, `ball_unwrap.unwrap`, `mark_detect.detect_marks`.
- Produces:
  - Constants: `PAIR_TOL_DEG = 6.0` (blob pair angle vs `neighbour_angle_deg`), `MATCH_TOL_DEG = 6.0`, `DIR_TOL_DEG = 20.0`, `MIN_MATCHED = 3`, `MAX_RMS_DEG = 3.0`, `DISTINCT_DEG = 10.0`.
  - `kabsch(map_vectors (n,3), cam_vectors (n,3)) -> R (3,3)` - SVD with the det correction, so det(R) = +1 always (Review Focus 4).
  - `class Orientation` with `R`, `matched` (list of `(blob_index, site_id)`), `rms_deg`.
  - `class Refusal` with `reason` (str, plain English, e.g. `"only 2 classified marks"`, `"ambiguous: 2 poses fit 4 marks"`, `"best pose leaves a dot where a cross belongs"`).
  - `identify(blobs, mmap) -> Orientation | Refusal`:
    1. hypotheses: every ordered pair of classified blobs (i, j) with angle within `PAIR_TOL_DEG` of `neighbour_angle_deg` × every neighbouring site pair (a, b) with the same shapes; R from the triad (normal, normalised cross product) of both pairs; additionally, if blob i is a bar or cross, its direction must agree with `R @ directions[a]` within `DIR_TOL_DEG` (mod 180 / mod 90);
    2. verify each hypothesis: a classified blob matches site s if the angle to `R @ normals[s]` ≤ `MATCH_TOL_DEG`, the shapes agree and the directions agree; a **conflict** is a classified blob within `MATCH_TOL_DEG` of a predicted site with a different shape or direction, or a predicted site within 50° of the view centre whose position holds no dark blob at all while it lies in `valid` - any conflict discards the hypothesis;
    3. refit each surviving hypothesis with `kabsch` on all its matches; keep matches within `MATCH_TOL_DEG` after the refit;
    4. best = most matches, then lowest rms; refuse if fewer than `MIN_MATCHED`, if rms > `MAX_RMS_DEG`, or if another surviving hypothesis with the same match count differs from the best by more than `DISTINCT_DEG` (Review Focus 5).
  - `orient_image(gray, K, dist, centre_cam_m, mmap) -> (Orientation | Refusal, Unwrapped, list[MarkBlob])` - convenience wrapper.

- [ ] **Step 1: Failing tests** (renderer)

```python
def test_random_poses_recovered(self):
    # 60 rotations from np.random.RandomState(7) (uniform on SO(3)), ball at 0.45 m:
    # every result is an Orientation within 1.0 deg of the truth, or a Refusal;
    # at least 50 of 60 are Orientations; zero wrong poses (> 5 deg off)

def test_kabsch_never_mirrors(self):                    # Review Focus 4
    # vectors and their mirror image (z negated): det(kabsch(...)) == +1

def test_two_marks_refused(self):                       # Review Focus 5
    # blobs: only two classified neighbours -> Refusal, reason mentions "only 2"

def test_wrong_shape_where_a_mark_belongs_is_refused_or_ignored(self):
    # take a recovered case, change one matched blob's shape to another shape:
    # result is a Refusal or an Orientation within 1 deg - never a different pose

def test_relative_turn_sign(self):
    # render the same ball turned +20 deg about camera y between two images:
    # R2 @ R1.T as a rotation vector (cv2.Rodrigues) is (0, +20 deg, 0) within 1 deg
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** `ball_orientation.py`.
- [ ] **Step 4: Run, expect PASS** (on the Jetson too - the 60-pose test is the slow one; keep it under ~60 s there, render at 640×400 crops around the ball if needed).
- [ ] **Step 5: Commit** - `git commit -m "ball_orientation: identify marks on the map, pose by Kabsch, refuse when unsure"`

### Task 5: Real frames - fixtures, check tool, acceptance

**Files:**
- Create: `sp1_vision/tests/fixtures/marked_ball/` - copied from `D:\Users\lasse\Documents\JetsonLM_recordings\2026-11-18_line_ball\` (keep each file's name, add the camera): `static1/raw/cam1/gs_01_flash.png` → `static_cam1.png`, `.../cam2/gs_01_flash.png` → `static_cam2.png`, `shots/cam1/t016.0788.jpg` → `putt_cam1_t016.0788.jpg` (line into a cross), `shots/cam1/t016.0908.jpg` → `glint_cam1_t016.0908.jpg`, `shots/cam2/t044.9315.jpg` → `limb_cam2_t044.9315.jpg`, plus the matching other-camera frame of each putt frame (nearest arrival, within 6 ms) for stereo.
- Create: `sp1_vision/orientation_check.py` (CLI)
- Test: `sp1_vision/tests/test_orientation_real.py`
- Create: `sp1_vision/strobe_runs/2026-11-xx_orientation/results.txt` (the run's numbers)

**Interfaces:**
- Consumes: `ball_pair.find_ball_pair` (stereo centre; cam2's centre = `rig.r @ xyz + rig.t_m`), `ball_orientation.orient_image`, `mark_map.load_map`, `strobe_event.fit_motion`, `stereo_geometry.load_rig`.
- Produces:
  - `orient_pair(rig, img1, img2, mmap) -> dict` with `ball` (BallPair or None), `cam1`, `cam2` (Orientation | Refusal), `agree_deg` (rotation angle of `R1 @ (rig.r.T @ R2).T`, with `R1`, `R2` the two cameras' orientations; None unless both are Orientations).
  - `rolling_check(frames, rig, mmap, up_cam=(0, -cos 1.6°, sin 1.6°)) -> list[dict]` - for consecutive frames with an Orientation in the same camera: measured relative rotation (angle, axis) vs pure rolling: angle `|v| Δt / r`, axis `up × v̂` (v from `fit_motion` on the stereo track; pitch +1.60° from CLAUDE.md, roll 0.36° ignored).
  - CLI: `python -m sp1_vision.orientation_check static CAM1 CAM2` and `python -m sp1_vision.orientation_check roll DIR1 DIR2 T_FROM T_TO` printing a table.

- [ ] **Step 1: Failing tests on the fixtures**

```python
def test_static_pair_both_cameras_agree(self):
    r = orientation_check.orient_pair(rig, static_cam1, static_cam2, mmap)
    self.assertIsInstance(r["cam1"], ball_orientation.Orientation)
    self.assertIsInstance(r["cam2"], ball_orientation.Orientation)
    self.assertLess(r["agree_deg"], 3.0)                 # spec acceptance: cam1/cam2 agree

def test_line_into_cross_still_identified(self):
    # putt_cam1_t016.0788 + partner: Orientation, and one matched site is a cross

def test_glint_and_limb_frames_do_not_give_wrong_poses(self):   # Review Focus 2, 3
    # each: Orientation agreeing with its partner camera within 3 deg, or Refusal
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** `orientation_check.py`; copy the fixtures; add `tests/fixtures/marked_ball` to `run-tests`' fixture sync.
- [ ] **Step 4: Run, expect PASS**; if the static pair does not agree within 3°, stop and report (it is the spec's acceptance number - do not loosen it).
- [ ] **Step 5: Acceptance run on the three 2026-11-18 putts** (windows 8.74-9.05, 16.02-16.42, 44.86-45.13 s, both cameras, from the recordings folder): `python -m sp1_vision.orientation_check roll ...`. Write `results.txt`: per putt the share of frames with an Orientation per camera, the rolling comparison (median angle error %, median axis error deg, sign of every frame pair), and the refusals by reason. Expected, if the method works: angle within 15 %, axis within 10°, every sign right in the late part of each roll (skid right after impact is allowed to differ).
- [ ] **Step 6: Commit** - `git commit -m "orientation_check: static pair and rolling putts on real frames"`

### Not in this plan

- Hand turns by known amounts (spec acceptance 2) need a turntable with an angle scale - a printed part, so new hardware: owner's approval first. The rolling putts give known turns with sign meanwhile.
- Parts 3 (offset trigger) and 4 (trajectory and spin) get their own plans.
