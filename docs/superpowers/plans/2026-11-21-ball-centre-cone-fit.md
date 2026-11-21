# Ball Centre by Cone Fit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Find the direction to the ball's centre to well under a pixel by fitting the cone of sight rays tangent to the sphere, and measure on synthetic and real frames whether it beats the circle fit.

**Architecture:** A new module `sp1_vision/sphere_fit.py`: subpixel outline points along rays (the existing `frame_analysis._outermost_edge_per_ray`), undistorted to unit rays, a linear cone fit (d_i · w = 1, axis = w/|w|, cos α = 1/|w|) with MAD trimming, returned through the same `(u, v, r)` refiner interface `ball_pair` already takes: (u, v) = the distorted pixel of the cone axis (the projected sphere centre), r = fx · tan α. So triangulation and the pair gates stay unchanged. `orientation_check` gets `--centre circle|cone`.

**Tech Stack:** Python 3.8 / numpy 1.17 / OpenCV 4.5.4 (Jetson) and 3.14 / OpenCV 5 (Windows), unittest.

**Spec:** `docs/superpowers/specs/2026-11-21-ball-centre-cone-fit-design.md`

## Global Constraints

- No OpenCV / numpy API newer than 4.5.4 / 1.17.4; Python 3.8 syntax.
- Ball radius from `sp1_vision.mark_map.BALL_RADIUS_MM` (42.67 / 2).
- Intrinsics and distortion from the rig (`stereo_geometry` / config); never hard-coded in the module.
- The Hough candidate search and the pair gates are not changed (spec non-goal).
- Real-frame yardstick: the three putts of `JetsonLM_recordings/2026-11-18_line_ball` (outside the repo) through `orientation_check roll`, windows 8.74-9.05, 16.02-16.42 and 44.86-45.13 s, as in `sp1_vision/strobe_runs/2026-11-21_orientation/results.txt`.
- Whether the triangulated track then uses cone or circle centres is decided on the measured numbers (spec).

## Review Focus

- A ball cut by the image edge: rays off the image must not enter the fit; with too few rays (< REFINE_TRIM_MIN_POINTS) the refiner returns None, not a guess.
- A dark mark on the limb or a glint: the outermost-edge rule and the trim must keep the axis within 0.2 px (synthetic marked ball).
- A seed several pixels off (Hough): the result must not depend on it beyond the noise (seed guards as `_within_seed_guards`).
- The cone radius vs the circle radius: `ball_pair`'s radius gates were tuned on circle radii that read 10-15 % small. A correct radius must not push good pairs out of the gates; count pairs found per putt before/after.
- Degenerate input (all rays nearly parallel, e.g. a 2-px "ball"): None, no division by zero.

---

### Task 1: Antialiased rendering for subpixel ground truth

**Files:**
- Modify: `sp1_vision/tests/render_ball.py` (`render_ball(..., oversample=1)`)
- Test: `sp1_vision/tests/test_render_ball.py` (create)

**Interfaces:**
- Produces: `render_ball(mmap, K, dist, centre_cam_m, R, ..., oversample=1)`. With oversample = n each pixel is the mean of n × n sub-pixel samples (edge area-weighted); the final 3×3 blur stays. Default 1 keeps every existing fixture byte-identical.

- [ ] **Step 1: Tests** — `test_default_is_unchanged` (oversample=1 equals a call without the argument, array_equal); `test_oversampled_area_matches_the_projected_disc` (plain ball, no ink: sum(img − background)/(ball_grey − background) within 1 % of the area of the exact projected ellipse, on axis at 0.44 m); `test_oversampled_centroid_is_the_circle_centre_on_axis` (ball on the optical axis, no distortion: brightness-weighted centroid within 0.02 px of (cx, cy)).
- [ ] **Step 2: Run, expect failure** — `python -m unittest sp1_vision.tests.test_render_ball` → TypeError (unknown argument).
- [ ] **Step 3: Implement** — sample at pixel + ((k + 0.5)/n − 0.5) offsets, average.
- [ ] **Step 4: Tests pass**, plus `test_ball_orientation`, `test_mark_detect`, `test_ball_unwrap` unchanged.
- [ ] **Step 5: Commit.**

### Task 2: sphere_fit - cone fit and the refiner

**Files:**
- Create: `sp1_vision/sphere_fit.py`
- Test: `sp1_vision/tests/test_sphere_fit.py`

**Interfaces:**
- Produces:
  - `fit_cone(rays) -> (axis, half_angle) | None`: rays (N,3) unit vectors; linear fit, then MAD trim on the angular residual (REFINE_TRIM_K, REFINE_ITERATIONS, REFINE_TRIM_MIN_POINTS from frame_analysis); None if < REFINE_TRIM_MIN_POINTS or degenerate.
  - `limb_rays(gray, K, dist, u, v, r) -> (rays (N,3), pixels (N,2)) | None`: outline points by `frame_analysis._outermost_edge_per_ray` on the 5×5-blurred ROI (as `refine_ball_by_contrast`), undistorted with `cv2.undistortPoints`.
  - `refine_ball_cone(frame, u, v, r, K, dist) -> (u, v, r) | None`: iterates limb_rays → fit_cone REFINE_ITERATIONS times, re-seeding at the projected axis; returns the axis's distorted pixel (`cv2.projectPoints`), r = fx · tan α; `frame_analysis._within_seed_guards` applied.
  - `cone_refiner(K, dist)`: a closure with the `refine(frame, u, v, r)` signature `ball_pair` expects.
  - `centre_from_cone(axis, half_angle) -> centre_cam_m`: axis · R_ball / sin α.

- [ ] **Step 1: Tests** — exact cone (axis 25° off z, α 2.8°, 72 rays) → axis error < 1e-9 rad, α error < 1e-9; 20 % outlier rays 0.3° outside → axis error < 1e-3°; 5 rays → None; rendered oversampled balls (Task 1) at 0.44 m, 0 / 10 / 20 / 30° off axis, the calibrated cam1 distortion: projected-centre error of `refine_ball_cone` < 0.1 px, and with the default marks pose < 0.2 px; `refine_ball` at 20° off axis is ≥ 0.4 px off (pins the bias the fix removes); a ball cut by the right image edge keeps < 0.3 px or returns None; seed 4 px off gives the same result within 0.05 px; `centre_from_cone` of the exact cone returns the true centre within 0.01 mm.
- [ ] **Step 2: Run, expect failure** (module missing).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Tests pass on Windows and on the Jetson** (copy of sp1_vision + config + calibration_results to /tmp/sp1test, `python3 -m unittest discover -s sp1_vision/tests -t .`; the 5 pre-existing failures are known: 4 test_real_frames, 1 live-camera staleness).
- [ ] **Step 5: Commit.**

### Task 3: Synthetic diagnosis - what each error costs

**Files:**
- Create: `sp1_vision/strobe_runs/2026-11-21_centre/centre_diagnosis.py`, `diagnosis.txt`

- [ ] **Step 1:** Script renders oversampled balls with cam1's K and distortion at 0.40-0.48 m, off-axis 0-30° in several directions, without and with marks, then JPEG at the cameras' MJPEG-like quality (q 85) plus Gaussian noise σ 2; per refiner (`refine_ball`, `refine_ball_by_contrast`, `refine_ball_cone`) the projected-centre error split radial / tangential (radial = towards the image centre), median and 90th percentile, in px and in degrees of orientation (1.7° per px at 420 mm).
- [ ] **Step 2:** Run it, write `diagnosis.txt`, read it: how much is projection + distortion bias (circle refiners, noise-free) vs pixel noise. Expected: the circle refiners' radial bias grows with off-axis angle (~0.4 px at 10°, ~0.9 px at 20°); the cone fit has none.
- [ ] **Step 3: Commit.**

### Task 4: orientation_check --centre cone, real putts

**Files:**
- Modify: `sp1_vision/orientation_check.py` (the three `frame_analysis.refine_ball` uses, lines ~127, 128, 134, 262, become a refiner chosen by `--centre`, default `circle`)
- Test: `sp1_vision/tests/test_orientation_real.py` (the static pair also with `centre="cone"`: Orientation in both cameras, agreement < 3°)

- [ ] **Step 1: Test** — static fixture pair with the cone refiner: both cameras Orientation, agreement < 3°.
- [ ] **Step 2: Run, expect failure** (no such parameter).
- [ ] **Step 3: Implement** — `orient_pair(..., refine=None)` / the monocular path take the refiner; CLI `--centre {circle,cone}`; the cone refiner built from the rig's K / dist per camera.
- [ ] **Step 4: Tests pass** (Windows + Jetson).
- [ ] **Step 5: Run the three putts both ways** on Windows (`python -m sp1_vision.orientation_check roll ... --centre cone`), keeping the tables in `sp1_vision/strobe_runs/2026-11-21_centre/`; compare per putt: frames on track, Orientation share, across residual median, flagged centres, cam1/cam2 agreement median / max, rolling median angle / axis error, signs.
- [ ] **Step 6: Commit** the tool change and the tables.

### Task 5: Decide and write up

- [ ] **Step 1:** `sp1_vision/strobe_runs/2026-11-21_centre/results.txt`: synthetic and real numbers side by side, what the cone fit changed, and the decision (cone becomes `orientation_check`'s default only if across residual and axis error improve without losing tracked frames; otherwise it stays an option and the reason is written down).
- [ ] **Step 2:** If adopted, switch the default, rerun the tests; note in CLAUDE.md "Current task" and in the spec's results section.
- [ ] **Step 3: Commit.**
