# Trajectory and Spin from Offset Images (part 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From a triggered recording (offset or simultaneous), per shot: launch speed, angle and direction from one trajectory fitted to every ball image at its own flash time, and spin (total, axis tilt, backspin, sidespin) from one rotation fitted to the corroborated mark orientations - or "no spin" with the reason.

**Architecture:** Four new modules in `sp1_vision`. `shot_times` puts every frame on the trigger grid at its flash centre. `ball_track` holds the floor frame, the two trajectory models (flight: p0 + v τ + ½ g τ²; rolling: in the plane one radius above the floor, p0 + u τ + w τ²), both **linear** in their parameters, fitted by linear least squares on across-ray distances (plus a weak along-ray term from the apparent size), a robust association over monocular points, model choice, leave-one-out residuals and the launch instant. `spin_fit` holds the rotation models (flight: Exp(ω τ) R0; rolling: fixed axis, rate linear in τ), seeding from 1 ms pairs (or, with `--max-rpm`, from 10 ms pairs), growth with refit, the fine fit, refusals, and the spin components. `strobe_spin` is the command: rest ball and impact from `strobe_event`, candidates, track, cone centres on the fitted depth, `orient_image`, spin, report and JSON.

**Tech Stack:** Python 3.8 / numpy 1.17 / OpenCV 4.5.4 (Jetson) and Python 3.14 / OpenCV 5 (Windows), unittest. No scipy (not on the hardware list): the trajectory fits are linear, the spin fit is a small Gauss-Newton written here.

**Spec:** `docs/superpowers/specs/2026-11-22-trajectory-spin-design.md` (parent: `2026-11-13-ball-marks-spin-design.md`)

## Global Constraints

- Python 3.8 syntax, nothing newer than numpy 1.17.4 / OpenCV 4.5.4; no new libraries.
- Camera 1's frame (X right, Y down, Z forward, metres) is the frame of every fit; cam2 enters through `rig` (X2 = r X1 + t): cam2 centre in cam1 = `stereo_geometry.camera2_centre_in_camera1(rig)`, a cam2 direction d2 is `rig.r.T @ d2` in cam1, a cam2 pose R2 is `rig.r.T @ R2` (`orientation_check.cam1_rotation`).
- Attitude (2026-11-11): pitch +1.60°, roll +0.36°, camera 1 0.1119 m above the floor; up in cam1 = (−sin φ, −cos θ cos φ, sin θ cos φ) with θ = pitch, φ = roll (`ground_plane.attitude_from_plane`'s convention). g = 9.81 m/s² along −up.
- Ball radius `mark_map.BALL_RADIUS_MM` (21.335 mm).
- Image instant = flash centre: t = k·period + cam_flash_us + pulse_us/2 (from `trigger.json`); without `trigger.json` both cameras at k·period + 900 µs + 50 µs (the defaults of the pre-2026-11-21 triggered recordings).
- Spec constants, start values: `SPIN_TOL_DEG = 4.0`, `MIN_SPIN_POSES = 4`, `MIN_SPIN_SPAN_S = 0.010`, `ROLL_HEIGHT_MM = 8.0`, `ROLL_VZ_MPS = 0.2`, `CENTRE_FLAG_MM = 0.8` (reuse `orientation_check.CENTRE_FLAG_MM`), `MAX_RPM_LIMIT = 3000` for `--max-rpm`. Tuned on acceptance 2, then frozen before acceptance 3.
- An uncorroborated pose never enters a spin; a rate never comes from 10 ms pairs unless `--max-rpm` was given; every refusal prints its reason.
- Tests with every change; run on Windows and on the Jetson before each commit of tasks 5-6.

## Review Focus

- **The ball in one camera only** (out of cam2's view, or cam2's images all dim): the track fits from one camera's rays plus the size term and says so ("one camera"); no crash, no silent stereo-quality claim. Test in Task 3.
- **A dropped frame** (20 ms arrival step in one camera): the period index skips one, the other camera's frame of that period stays unpaired, no frame gets its neighbour's time. Test in Task 1.
- **The ball leaving the IR beam:** late frames hold only clutter (static highlights, the club); association must not extend the track with it. Test in Task 3.
- **A symmetry-wrong pose inside the first 1 ms pair:** that seed grows a small set; the winning set comes from another seed, the wrong pose is dropped and shown with its miss (≈72°). Test in Task 4.
- **A chip that lands in view:** points after the first return to the rolling plane are cut off, the flight fit uses only the part before. Test in Task 3.

---

### Task 1: Frame times on the trigger grid

**Files:**
- Create: `sp1_vision/shot_times.py`
- Test: `sp1_vision/tests/test_shot_times.py`

**Interfaces:**
- Produces:
  - `load_trigger_info(rec_dir) -> dict | None` (reads `rec_dir/trigger.json`, as written by `strobe_shot.trigger_info`).
  - `flash_times_s(info) -> (f1_s, f2_s)`: each camera's flash centre within the period; `(0.00095, 0.00095)` for `None`.
  - `period_grid(arrivals1, arrivals2, period_s=0.010, pair_max_dt_s=strobe_event.PAIR_MAX_DT_S) -> list of (k, i1, i2)`: k = period index from cam1's arrival steps rounded to whole periods (as `orientation_check.snap_times`), i1 / i2 = index into each camera's frame list or `None`; cam2 frames take the k of the cam1 frame they pair with (nearest arrival within `pair_max_dt_s`); an unpaired cam2 frame gets its own k from its arrival relative to its nearest paired neighbour.
  - `frame_time_s(k, cam, info, period_s) -> float` = k·period + that camera's flash centre.

- [ ] **Step 1: Write the failing tests** - `test_offset_flash_times_are_one_ms_apart` (info with offset 1000, delay 900, pulse 100 → f2 − f1 = 0.0010 exactly, f1 = 0.00095); `test_no_trigger_json_is_simultaneous` (`flash_times_s(None)` equal); `test_usb_pairs_snap_to_the_grid` (arrivals 0, 0.008, 0.020, 0.028, 0.040 … → k = 0..4); `test_a_dropped_cam2_frame_leaves_its_period_unpaired` (cam2 misses k = 3: grid row k = 3 has i2 None, k = 4 pairs correctly); `test_a_dropped_cam1_frame` (cam1 jumps 20 ms: k skips 2, cam2's frame of the missing period gets k = 2 with i1 None).
- [ ] **Step 2: Run** `python -m unittest sp1_vision.tests.test_shot_times` - expect ImportError.
- [ ] **Step 3: Implement** the four functions.
- [ ] **Step 4: Run** - expect PASS.
- [ ] **Step 5: Commit** `shot_times: every frame on the trigger grid at its flash centre`.

### Task 2: Floor frame and the two trajectory models (linear fits)

**Files:**
- Create: `sp1_vision/ball_track.py`
- Test: `sp1_vision/tests/test_ball_track.py`

**Interfaces:**
- Consumes: `stereo_geometry.camera2_centre_in_camera1(rig)`.
- Produces:
  - `Floor(up, height_m)` with `Floor.default()` (attitude above) and `roll_plane_point()` = `-(height_m - r_m) * up`, the point of the rolling plane (ball centres, one radius above the floor) straight below camera 1.
  - `Obs(t, cam, origin, direction, range_m=None, k=None, ref=None)`: a unit ray in cam1's frame; `range_m` the monocular range from the apparent size (weak term), `ref` caller data (frame index, candidate).
  - `obs_from_pixel(rig, cam, uv, radius_px, t, k=None, ref=None) -> Obs` (undistort with that camera's K, d; cam2 rotated into cam1; range = fx·r / radius_px as `ball_unwrap.centre_from_circle`).
  - `Track(model, params, t0, floor)` with `position(t) -> (3,)`, `velocity(t) -> (3,)`.
  - `fit_track(obs, model, t0, floor, size_weight=SIZE_WEIGHT) -> Track` where model is `"flight"` or `"rolling"`. Flight unknowns p0, v (g fixed); rolling unknowns in-plane p0 (2), u (2), w (2) in an orthonormal basis of the plane (the plane fixes the third coordinate). Rows: (I − d dᵀ)(p(t) − o) = 0 per ray, plus `size_weight`·(d·(p(t) − o) − range) for rays with a range. `SIZE_WEIGHT = 0.05` (start; the along-ray scatter of a monocular range is ~20× the across-ray one).
  - `fit_points(times, xyz, model, t0, floor) -> Track` - the same models fitted to 3D points (for acceptance 1: stereo positions under the new model).
  - `across_residuals_m(track, obs) -> np.ndarray` and `loo_across_m(obs, model, t0, floor) -> np.ndarray` (each obs against the fit without it).

- [ ] **Step 1: Write the failing tests** - synthetic exact data from both cameras (`stereo_geometry.load_rig()`), 8 periods, cam2 1 ms after cam1: `test_flight_is_recovered_from_offset_rays` (p0, v within 1e-6 m, 1e-6 m/s, ranges given with 5 % error: still within 0.5 mm / 0.01 m/s because the across rows dominate); `test_rolling_stays_in_the_plane` (a decelerating straight putt, |p(t)·up − plane| < 1e-9, speeds recovered); `test_rolling_allows_a_curved_putt` (w not parallel to u: recovered); `test_fit_points_matches_fit_track` on the same synthetic path; `test_loo_flags_a_displaced_ray` (one ray rotated so its across distance is 1.5 mm: LOO residual > 1.2 mm, all others < 0.1 mm).
- [ ] **Step 2: Run** `python -m unittest sp1_vision.tests.test_ball_track` - expect ImportError.
- [ ] **Step 3: Implement** with `np.linalg.lstsq` on the stacked rows.
- [ ] **Step 4: Run** - PASS.
- [ ] **Step 5: Commit** `ball_track: floor frame, flight and rolling models, rays at their own times`.

### Task 3: Association, model choice, landing, launch

**Files:**
- Modify: `sp1_vision/ball_track.py`
- Test: `sp1_vision/tests/test_ball_track.py`

**Interfaces:**
- Consumes: Task 2.
- Produces:
  - `associate(obs, rest_xyz, t_imp, floor, seed=0) -> (Track, kept_obs, info)`: consensus over hypotheses from pairs of observations in different periods (flight: the two points with their ranges give p0, v; rolling: the two points projected into the plane, w = 0); an obs agrees when its across distance < `ACROSS_TOL_M = 0.004` and its along distance < `ALONG_TOL_M = 0.040`; at most one obs per (camera, period), the nearest; the hypothesis must reach the rest ball (|p(t) − rest| ≤ 2 r for some t within ±`LAUNCH_WINDOW_S = 0.03` of t_imp) or it is skipped. Both models are tried; `choose_model` below decides; then `fit_track` on the kept obs. `info` = {"model", "cameras": set, "landed_at": t or None, "n_hyp"}.
  - `choose_model(points_xyz, times, floor) -> "rolling" | "flight"`: rolling when every point is within `ROLL_HEIGHT_MM` of the rolling plane and the vertical velocity of a line fit is below `ROLL_VZ_MPS`.
  - Landing: in flight mode, obs after the first time the fitted centre comes back within `ROLL_HEIGHT_MM` of the rolling plane (after having left it) are removed and the fit repeated; `info["landed_at"]`.
  - `launch(track, rest_xyz) -> dict`: t where |p(t) − rest| = r (bisection after t_imp − 0.03), speed, launch angle = asin(v·up/|v|), direction_deg = −atan2(((f × v_h)·up), f·v_h) with v_h the horizontal part of v and f camera 1's X axis projected onto the floor, signed so f·v_h > 0 (positive = to the right seen from behind the ball; provisional zero per spec §3).

- [ ] **Step 1: Write the failing tests** - `test_clutter_and_a_second_object_are_left_out` (static circles at fixed pixels in every frame and a second object moving at 0.5 m/s 300 mm away: kept obs are exactly the ball's); `test_late_clutter_does_not_extend_the_track` (ball images stop after period 6, clutter continues: no kept obs after period 6); `test_one_camera_only` (cam2 has no ball obs: track from cam1 rays + sizes, `info["cameras"] == {"cam1"}`, speed within 3 %); `test_putt_is_rolling_chip_is_flight` (choose_model on both synthetic paths); `test_a_landing_chip_is_cut_at_the_floor` (flight then roll-out: `landed_at` within one period of the true landing, the flight fit unaffected by the roll-out points); `test_launch_signs` (ball travelling +X rising 30°: angle +30°; heading 5° towards the unit while travelling +X: direction +5°; the same heading travelling −X: −5°).
- [ ] **Step 2: Run** - FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** - PASS.
- [ ] **Step 5: Commit** `ball_track: association, model choice, landing, launch`.

### Task 4: Spin fit (approach B)

**Files:**
- Create: `sp1_vision/spin_fit.py`
- Test: `sp1_vision/tests/test_spin_fit.py`

**Interfaces:**
- Consumes: `ball_orientation.rotation_angle_deg`.
- Produces:
  - `Pose(t, cam, k, R)` with R map → cam1.
  - `SpinResult` with `omega` (rad/s, cam1 frame, fine) or `None`, `coarse` (mean ω of the agreeing pairs) and `coarse_spread_rpm`, `model`, `rms_deg`, `used` (list of Pose), `dropped` (list of (Pose, miss_deg)), `refusal` (str or None), `assumption` (str or None, e.g. "rate < 3000 rpm (--max-rpm)").
  - `fit_spin(poses, model="flight", dt_pair_s=0.001, max_rpm=None, tol_deg=SPIN_TOL_DEG) -> SpinResult`. Model `"flight"`: R(t) = Exp(ω τ) R0; `"rolling"`: R(t) = Exp(â (ω0 τ − ½ α τ²)) R0. Seeds: every period with poses in both cameras when `dt_pair_s > 0` (ω_k = Log(R2 R1ᵀ)/dt); when `dt_pair_s == 0` (simultaneous recording) only if `max_rpm` is given (≤ `MAX_RPM_LIMIT`, else ValueError): same-camera poses in consecutive periods, seed kept only if |ω| ≤ max_rpm; and same-period cam1/cam2 poses disagreeing by more than 3° are both dropped first. Growth: nearest-in-time pose next, refit (Gauss-Newton on the rotation-vector residuals Log(R_i R(t_i)ᵀ), numerical Jacobian, ≤ 20 iterations), keep if its residual ≤ tol; largest set wins, ties lower rms. Refusals in this order of checks: "no pair pins the rate", "only N corroborated poses (need MIN_SPIN_POSES)", "poses from one period only", "span X ms < 10 ms".
  - `spin_components(omega, v_hat, up) -> dict(total_rpm, backspin_rpm, sidespin_rpm, axis_tilt_deg, rifle_rpm)` per spec §6: s = (v̂ × up)/|…|, u' = s × v̂, backspin = ω·s, sidespin = −ω·u', tilt = atan2(sidespin, backspin), rifle = ω·v̂, all in rpm.

- [ ] **Step 1: Write the failing tests** - synthetic poses, 2° random error each, a pose pair (cam1 at t, cam2 at t + 1 ms) every 10 ms over 80 ms, 60 % of poses kept at random: `test_flight_spin_is_recovered` (3000 rpm about a tilted axis: fine rate within 1 %, axis within 2°, coarse within its spread); `test_fast_spin_is_not_aliased` (9000 rpm, 270° per 10 ms: fine within 1 %); `test_a_symmetry_wrong_pose_in_the_first_pair_is_dropped` (first pair's cam2 pose 72° off about a site axis: result correct, that pose in `dropped` with miss ≈ 72°); `test_ten_ms_only_is_refused_by_default` (no 1 ms pairs, dt_pair_s = 0.001 but every period has one camera only: refusal "no pair pins the rate"); `test_simultaneous_needs_max_rpm` (dt_pair_s = 0, no max_rpm: refused; with max_rpm = 3000 on a 450 rpm rolling ball: recovered, `assumption` set); `test_rolling_deceleration` (rolling model, 500 → 400 rpm over 0.3 s: ω0 and α within 2 %, the flight model on the same data leaves rms > tol); `test_too_few_poses` and `test_one_period_only` (refusal strings); `test_spin_components_signs` (ball flying +X: ω along s gives backspin > 0, tilt 0; ω along +up gives sidespin < 0 and tilt < 0 - curves left; clockwise seen from above (ω along −up) gives tilt > 0).
- [ ] **Step 2: Run** - FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** - PASS.
- [ ] **Step 5: Commit** `spin_fit: one rotation over the shot, seeded by 1 ms pairs, grown and refitted`.

### Task 5: strobe_spin - the shot from recording to spin

**Files:**
- Create: `sp1_vision/strobe_spin.py`
- Test: `sp1_vision/tests/test_strobe_spin.py`

**Interfaces:**
- Consumes: Tasks 1-4; `strobe_event.find_rest_balls`, `find_impacts`, `PositiveReference`, `REF_FROM_S`, `REF_TO_S`, `FLIGHT_S`, `MAX_CANDIDATES`; `frame_analysis.ball_candidates`, `ball_pair.radius_bounds_px`; `sphere_fit.refine_ball_cone`; `ball_orientation.orient_image`; `orientation_check.cam1_rotation`, `CENTRE_FLAG_MM`; `strobe_shot.load_raw`.
- Produces:
  - `analyse_shot(rig, mmap, frames, grid, info, rest_xyz, t_imp, floor, max_rpm=None) -> dict` where `frames = {"cam1": [(gray, positive)], "cam2": [...]}` indexed as `grid` refers to them: candidates per camera and period on the positive image → `obs_from_pixel` → `associate` → for each kept obs: `refine_ball_cone` on the gray image (refused → listed, not oriented), the centre = the point on that cone axis at the track's depth for its time, LOO across residual > `CENTRE_FLAG_MM` → not oriented, else `orient_image` and `Pose`; then `fit_spin` with the track's model and `dt_pair_s = f2 − f1`. Returns {"track", "info", "launch", "images": per kept obs (t, cam, k, loo_mm, status), "spin": SpinResult, "components": dict or None}.
  - `main(argv)`: `python -m sp1_vision.strobe_spin RECDIR [--max-rpm N] [--shot K] [--sheet] [--compare-stereo]`; `--sheet` writes `RECDIR/spin_shotK_sheet.jpg`, the unwrapped caps of the oriented images in time order (tile drawing as `orientation_check._sheet`); per shot prints the track table, the image table, launch, spin (coarse and fine side by side, refusal or assumption); writes `RECDIR/spin_shotK.json`. `--compare-stereo` (acceptance 1): also runs `strobe_event.flight` on the same shot, fits its positions with `fit_points` under the chosen model, and prints both velocities at the window midpoint and the across-ray part of both residuals.

- [ ] **Step 1: Write the failing test** - `test_rendered_offset_chip` (`tests/render_ball.render_ball`, dark background so the image is its own positive): 7 periods, ball from rest at 4.5 m/s, 30° up, 2500 rpm backspin, cam2 1 ms after cam1, both cameras rendered at their own times and poses; `analyse_shot` gives speed within 2 %, launch angle within 1°, backspin within 5 % and > 0, sidespin within ±150 rpm, `spin.refusal is None`; and `test_rendered_simultaneous_putt_needs_max_rpm` (rolling, no offset: refusal without `max_rpm`, rate within 10 % with `max_rpm=3000`).
- [ ] **Step 2: Run** - FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** on Windows and on the Jetson - PASS on both.
- [ ] **Step 5: Commit** `strobe_spin: trajectory and spin of a recorded shot`.

### Task 6: Acceptance 1 and 2 on existing recordings, constants frozen

**Files:**
- Create: `sp1_vision/strobe_runs/2026-11-2x_part4/results.txt` (date of the run), README entry in `sp1_vision/strobe_runs/README.md`
- Modify: `CLAUDE.md` (Current task: part 4 state, command, what is open)

- [ ] **Step 1: Acceptance 1** on the Jetson: `python3 -m sp1_vision.strobe_spin ~/recordings/2026-11-12_chips_trigger --compare-stereo` and the same on `~/recordings/2026-11-18_line_ball_shots`. Pass: midpoint velocity within 2 % in speed and 1° in angle and direction for every shot both methods find; ray-fit across residual not worse than the stereo fit's across part. Write the per-shot table to results.txt. If it fails, stop and report - nothing below is trusted on a failed trajectory.
- [ ] **Step 2: Acceptance 2:** `python3 -m sp1_vision.strobe_spin ~/recordings/2026-11-18_line_ball_shots --max-rpm 3000` - the three putts (impacts near 8.7, 16.0, 44.8 s): rolling model chosen for all three; from 0.1 s after impact the fitted rate within 10 % of |v(t)|/r and the axis within 10° of up × v̂. Record shares of images oriented, dropped poses with their misses, refusals.
- [ ] **Step 3: Tune and freeze.** Only `SPIN_TOL_DEG`, `MIN_SPIN_POSES`, `ACROSS_TOL_M`, `ALONG_TOL_M`, `SIZE_WEIGHT` may move, each change with its reason in results.txt; then they are frozen (comment at the constants: "frozen 2026-11-xx, acceptance 2") before any offset recording is analysed.
- [ ] **Step 4:** CLAUDE.md and the strobe_runs README updated; commit `part 4: acceptance 1 and 2 on existing recordings`.

Acceptances 3 (offset chips and throws), 4 (signs: the vertical turntable series passed, backspin > 0 on the chips) and 5 (offset putts) wait for the owner's recordings: `strobe_shot --trigger --offset-us 1000 --seconds 60 --out RUNDIR`, then `strobe_spin RUNDIR` with the frozen constants. They are run as a follow-up, not as part of this plan's tasks.
