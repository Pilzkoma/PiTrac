# Trajectory and Spin from Offset Images (ball marks, part 4) — Design

Status: draft 2026-11-22, approach (B) chosen by the owner the same day,
putts in scope (owner, same day). Builder check done; the answers marked
"my call" are mine and open to the owner's correction.
Parent design: `2026-11-13-ball-marks-spin-design.md` (parts 1–3 done,
part 2's hand-turn acceptance in progress). Everything decided there still
holds; this document only adds what part 4 needs.

## Why

Parts 1–3 give, per ball image, an absolute orientation of a marked ball
(`ball_orientation.orient_image`), and a recording in which cam2 sees the
ball 1.0 ms after cam1, each camera under its own flash
(`strobe_shot --trigger --offset-us 1000`, firmware v0.4). Part 4 turns a
recorded shot into numbers: ball position and velocity over the flight, and
spin rate and axis — what GSPro needs and what the dimples could not give
(CLAUDE.md, Known issues 1).

## Goals

- Per shot: launch speed, launch angle (vertical) and direction (horizontal),
  from one trajectory fitted to every ball image of both cameras at its own
  flash time.
- Per shot: total spin (rpm), spin-axis tilt, backspin and sidespin,
  relative to the ball's measured flight direction, in the floor frame.
  Two rates reported side by side: the coarse one from the 1 ms cam1/cam2
  pairs alone, and the fine one from the whole fit (acceptance (b) of the
  parent design compares them).
- A shot whose spin cannot be corroborated reports "no spin" with the reason,
  never a number.
- Offline, as `strobe_event` is today: a recording folder in, a printed table
  and a results file out.

## Non-goals

- Live processing in `pitrac_lm`, sending to GSPro.
- Drives / two flashes per exposure (parent design: later). The method must
  not rule them out (nothing may assume more than ~2 images per camera when
  the code is later fed a two-flash schedule), but this pass is tuned and
  accepted on chips and throws, the only shots possible indoors now.
- Air drag and spin decay. Over the ≤ 0.15 s a chip is in view, drag changes
  the speed by ~1–2 % and spin by far less; constant spin and a gravity-only
  path are the model.
- Fixing the mark classification near the limb. That runs in parallel on
  the hand-turn series; part 4 takes whatever share of oriented images
  part 2 delivers and must work with few.

## Anti-goals (a failure even if it technically works)

- **Aliased spin** (parent design): a rate chosen without a 1 ms pair that
  pins it to within half a turn. No coarse pair among the corroborated
  orientations → no spin.
- **An uncorroborated pose in the spin** (parent design, 2026-11-21
  constraint). With the offset trigger the two cameras never see the same
  instant, so the static "cam1 and cam2 agree within 3°" test does not exist
  in flight. Corroboration is therefore temporal only: an orientation counts
  when one constant rotation fits it together with the others.
- **Spin from a wrong ball centre without noticing.** 1 mm of centre error
  across the line of sight costs ~3.7° of orientation (2026-11-21
  measurement); the centre used for orienting an image must be as good as
  the cone fit can make it, and the fit's residual must be reported.
- **Replacing working simultaneous stereo with something worse.** The new
  trajectory fit must be checked against today's simultaneous-pair method on
  existing (non-offset) recordings before it is trusted (parent design, risks).

## Constraints (measured)

- Flash times: `trigger.json` next to `raw/` gives period, offset, delay and
  pulse; cam1's flash 0.9 ms and cam2's 1.9 ms after cam1's edge, 100 µs
  each. The image's instant is the flash centre. The 1.0 ms between the two
  is set by the Teensy's clock, exact for our purposes.
- Frame arrival times come in USB pairs 8/12 ms apart while edges are exactly
  10 ms apart (`orientation_check.snap_times` rounds steps to whole periods).
  Frames are matched to edges by arrival; a dropped frame shows as a 20 ms
  step.
- Ball centre per image: `sphere_fit.refine_ball_cone` (cone of tangent rays)
  — across-ray residual 0.5–0.8 mm median on putts. Circle centres sit
  0.4–1 px outward off axis.
- Orientation per image: `ball_orientation.orient_image(gray, K, dist,
  centre_cam_m, mmap)` → `Orientation(R map→camera)` or `Refusal`. Share of
  frames oriented on putts: cam1 35–56 %, cam2 27–38 %. Single-camera poses
  can be wrong by a symmetry of the site set (72/120/144/180°) about 1 image
  in 2000.
- Stereo: `stereo_extrinsics.json` (2026-11-10), cam2 = R·cam1 + t,
  baseline 80.47 mm. Floor attitude: pitch +1.60°, roll +0.36°
  (2026-11-11), camera 1 111.9 mm above the floor.
- Speeds in scope now: putts ~1 m/s (rolling, §3), chips 4–5 m/s, throws
  10–15 m/s. At
  15 m/s the ball moves 15 mm between cam1's and cam2's image of one period.
- The IR beam is flat: chips leave the light ~100 mm below the image top
  (2026-11-13). Few frames per shot (chips: ~7 tracked points).
- Python in `sp1_vision`, tests with every change; no new libraries.
  Must run on the Jetson (Python 3.8, numpy 1.17, OpenCV 4.5.4) and on
  Windows (3.14, OpenCV 5).

## Approaches

- **(A) Pairwise.** Coarse rate from each 1 ms pair, fine rate from pairs
  10 ms (or more) apart with the number of whole turns taken from the coarse
  rate; average. Simple, but every pair stands alone: a wrong pose in one
  image makes a wrong pair, and nothing ties the estimates together, so
  corroboration has to be bolted on.
- **(B) One constant rotation over the whole shot — chosen (owner,
  2026-11-22).** All orientations of a shot, both cameras, at their flash
  times, fitted by one rotation R(t) = Exp(ω (t − t0)) R0. The 1 ms pairs
  seed ω unambiguously; a consensus search keeps the orientations the
  rotation explains (the corroboration) and drops the rest; a least-squares
  fit over the kept ones gives the fine ω. The coarse rate is still
  reported separately.
- Rejected for the trajectory: keeping simultaneous stereo pairs. With the
  offset the cameras see the ball 1 ms apart; the ball's motion between the
  two images lies mostly along the image rows, i.e. along the epipolar line,
  and goes straight into the disparity (a chip at 5 m/s: 5 mm ≈ 10 px of
  disparity ≈ 35 mm of depth). Hence one fit over all rays at their own
  times.

## Design

### 1. Frame times

Each frame of each camera gets the trigger-grid time of its flash:
period index k from the arrival sequence (whole-period rounding, as
`snap_times`), t = k·period + that camera's flash centre from
`trigger.json`. cam1 frame k and cam2 frame k belong to the same period
(paired by arrival). Recordings without `trigger.json` (before 2026-11-21)
or without an offset: both cameras at the same flash time — this is how the
comparison against today's stereo (§6) runs on old recordings.

### 2. Ball candidates per camera

Rest ball and impact as today (`strobe_event.find_rest_balls`,
`find_impacts`: the ball is still, the offset does not matter). In the
flight window, per camera and frame: circle candidates in the positive
difference image (as `strobe_event.flight` does, before its stereo step).

### 3. Trajectory (rays at their own times)

Two models, one per kind of shot (putts in scope: owner, 2026-11-22 -
one recording mode for every shot, since the device cannot know in advance
whether a putt comes, and rolling putts are the only known rotation in
motion we have):

- **Flight:** p(t) = p0 + v (t − t0) + ½ g (t − t0)², g = 9.81 m/s² along
  the floor's down direction (from the measured attitude, not fitted), in
  camera 1's frame. Six unknowns.
- **Rolling:** the centre on the plane one ball radius above the floor
  (floor from the attitude and camera 1's height, 111.9 mm), constant
  velocity direction, constant deceleration along it: p(t) = p0 + (s0 (t −
  t0) − ½ a (t − t0)²) d̂, d̂ in that plane. Five unknowns (p0 in the plane,
  d̂, s0, a).
- **Which model (my call):** rolling when the rough association's points
  (below) all lie within `ROLL_HEIGHT_MM` (start 8 mm) of the rolling plane
  and their vertical velocity is under `ROLL_VZ_MPS` (start 0.2 m/s);
  otherwise flight. A chip that lands in view is analysed up to the first
  point that comes back within `ROLL_HEIGHT_MM` of the plane; what it does
  after landing is not reported.

- **Association (rough):** within a period, cam1 and cam2 candidates are
  paired by a loose stereo check (rows, radii, depth near the rest ball's)
  that tolerates the 1 ms of motion; their rough 3D points go into a robust
  consensus fit of the model (pairs of periods propose p0, v; the proposal
  most points agree with wins), as `fit_motion` does today for constant
  velocity. The images of the winning points are the shot's ball images.
- **Fine fit:** each kept image contributes its cone-fit ray (centre
  direction, precise across) at its own time, through its own camera's
  pose; least squares on the across-ray distances of p(t_i) from the rays.
  The cone's half-angle (apparent size, weak depth) may enter with a small
  weight to stabilise depth when one camera has few images — builder's call.
- **Launch instant (my call):** t_imp from arrival times is good to only
  ~±10 ms, and a chip's launch angle moves ~1.2° per 10 ms along a
  ballistic path. Launch is therefore where the fitted path leaves the rest
  ball (its centre ~1 ball radius from the rest position), not t_imp.
- **Report:** launch speed, launch angle and direction in the floor frame at
  that instant; per image the across-ray residual (mm); rms.
- **Direction zero (my call, provisional):** no target-line yaw is measured
  yet. Direction is reported against camera 1's X axis projected onto the
  floor, positive to the right as seen from behind the ball, as
  `strobe_event` does today, and labelled so. Spin is unaffected (it is
  relative to v̂).

### 4. Orientation per image

For every kept image: the centre is the point on that image's own cone axis
at the depth the trajectory gives for its time (across from the image,
along from the fit; along errors cost little: 10 mm ≈ 0.8°). Then
`orient_image` in that camera, and the result is brought into cam1's frame
(`R_cam1 = rig.r.T @ R` for cam2, as `orientation_check.cam1_rotation`).
Images whose across-ray residual exceeds `CENTRE_FLAG_MM` (0.8 mm) are not
oriented; they are listed with the residual. The residual is
**leave-one-out** (the trajectory refitted without that image), as
`orientation_check` measures it against the neighbours - an in-fit residual
flatters every image the fit includes (my call). The gate stays hard; the
tool reports how many images it removed per shot, so acceptance 3 shows
whether it costs chips their spin, and the gate is revisited on that
evidence, not before.

### 5. Spin (approach B)

1. **Coarse:** for every period with an orientation in both cameras,
   ω_k = Log(R2 R1ᵀ) / Δ, Δ = cam2's flash minus cam1's (1.0 ms). Unique for
   rates below half a turn per ms (30,000 rpm).
2. **Consensus by growth (my call after the builder check):** one 1 ms pair
   alone predicts poorly far from itself (~2° pose error per image is
   ~470 rpm of ω error, ~28° of pose 10 ms away - far below half a turn, so
   the whole-turn count is safe, but far above any useful tolerance). So
   each pair seeds a set that grows: add the orientation nearest in time
   whose pose the current ω predicts within half a turn, choose its whole
   turns from that prediction, refit ω and R0 over the set, keep the new
   orientation only if its residual after the refit is within
   `SPIN_TOL_DEG` (start 4°), repeat. The seed whose grown set is largest
   wins (ties: lower rms). A symmetry-wrong pose (72/120/144/180° off) stays
   far outside 4° after any refit and is dropped. Whole turns always come
   from the current ω, never from the 10 ms gap alone.
3. **Fine:** least squares over the agreeing orientations for ω and R0
   (geodesic residuals), started from the winning set's last refit.
4. **Refusal:** "no spin" unless the agreeing set has (a) at least one pair
   that pins the rate (below), (b) at least `MIN_SPIN_POSES` orientations
   (start 4) from at least two different periods, and (c) a time span
   ≥ 10 ms. Reasons printed.
   *Pairs that pin the rate:* in an offset recording, a 1 ms pair. In a
   simultaneous recording (no offset: the 2026-11-18 putts and chips used
   for acceptance 2) there is none; there, and only when the run is started
   with an explicit `--max-rpm N` (N ≤ 3000, under half a turn per 10 ms),
   consecutive 10 ms pairs of one camera seed instead, and same-instant
   cam1/cam2 orientations must agree within 3° to count (static
   corroboration). The output states the assumption. Without the flag a
   simultaneous recording gets trajectory only (my call: a test path, kept
   apart so the aliasing anti-goal cannot be reached by default).
   *Rolling shots (my call):* a putt slows by ~15 % over 0.3 s, ~40° of
   pose drift against one constant rotation. In rolling mode the rotation
   keeps a fixed axis but its rate changes linearly in time, R(t) =
   Exp(â (ω0 τ − ½ α τ²)) R0 with τ = t − t0 - the rotation a ball rolling
   with constant deceleration has. One parameter more; the same growth,
   tolerance and refusals. The rate is measured, never taken from the
   rolling model, so the rolling model stays a test (acceptance 2).
5. **Report:** coarse ω (mean of the agreeing pairs' ω_k, with spread) and
   fine ω; rms of the residuals; which orientations were dropped and by how
   far they missed (a symmetry miss of 72/120/180° is shown as such).

### 6. Output, frames and sign conventions

- Floor frame from the measured attitude (pitch +1.60°, roll +0.36°, as
  `orientation_check.UP_CAM`, plus roll); up = against g; v̂ = the flight
  direction at impact.
- ω is decomposed along three unit vectors: v̂, s = (v̂ × up)/|v̂ × up|
  (horizontal, to the right of the flight), and u' = s × v̂ (perpendicular
  to the flight, tilted back from up by the launch angle).
  **Backspin** = ω·s in rpm (positive for a normal lofted shot: the top of
  the ball turns back toward the player). **Sidespin** = −ω·u' (positive
  when the ball curves right). **Spin-axis tilt** = atan2(sidespin,
  backspin): negative when the ball curves left (draw/hook for a
  right-hander), positive when it curves right, as GSPro's `SpinAxis`.
  Total spin = |ω|; the component along v̂ (rifle spin) is reported
  separately and should be near zero.
- The sign of ω_up is the one the vertical turntable series (part 2,
  acceptance 2) checks directly: turned clockwise seen from above, ω points
  down. That series must pass before part 4's sidespin sign is trusted.

### 7. Tool

One offline command (name and whether it extends `strobe_event` is the
builder's call), e.g. `python -m sp1_vision.strobe_spin RUNDIR`: finds the
shots, prints per shot the trajectory table, the per-image table
(time, camera, residual, Orientation/Refusal, kept/dropped) and the spin
result; `--sheet` writes the unwrapped caps as `orientation_check` does.

## Acceptance

1. **Trajectory against today's stereo**, before anything else is built on
   it, on simultaneous triggered recordings (the 2026-11-12 putts are lost
   and were free-running anyway): `2026-11-12_chips_trigger` (Jetson) and the
   2026-11-18 putts and chips (cut windows of cam1/cam2 JPEGs). Both methods
   are compared **at the same instants and with the same model** - the
   simultaneous stereo positions fitted with the new model (ballistic or
   rolling, §3), and the ray fit - so the test measures the rays-at-own-times
   step, not the model change: velocity at the window midpoint within 2 % in
   speed and 1° in angle and direction; positions at each frame time within
   the stereo's own scatter; the across-ray residual of the ray fit not
   worse than the across-ray part of the stereo fit's residual (the same
   quantity on both sides).
2. **Rolling putts as a known spin:** on the 2026-11-18 putts (simultaneous,
   marked ball, run with `--max-rpm 3000`) the fitted rotation matches the
   rolling model (|v(t)|/r about up × v̂) from 0.1 s after impact on (the
   skid of 2026-11-21 had ended by then): rate within 10 %, axis within
   10° — the same yardstick part 2 used per pair, now as one fit. Rolling
   mode must be chosen for all three putts.
5. **Offset putts** (to be recorded): same check as 2 on putts recorded with
   `--offset-us 1000`, the default path (1 ms pairs, no `--max-rpm`).
3. **Chips and throws with the offset trigger** (to be recorded by the
   owner): coarse and fine rate agree within their stated spreads; values
   physically plausible (parent design, owner decision 3); no shot reports a
   spin from fewer than the required poses; every refusal has its reason.
4. Signs: the vertical turntable series (part 2) passed, and in the chips
   the backspin sign is positive.

## What is left to the builder

- Module layout, the command's name, whether it extends `strobe_event`.
- Association details and tolerances in §3; whether the apparent size
  enters the fine fit and with what weight.
- The optimiser for §3 and §5 (Gauss–Newton on 6 parameters is enough);
  the starting values of `SPIN_TOL_DEG`, `MIN_SPIN_POSES`, tuned on
  acceptance 2 and then frozen before acceptance 3.
- How dropped frames and frames outside the flight window are shown.
