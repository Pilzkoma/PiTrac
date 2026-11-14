# Ball Marks and Mark-Based Spin — Design

**Date:** 2026-11-13
**Sub-project:** SP2 — Spin Detection (with SP1 trigger/strobe work)
**Status:** Draft for owner approval

## Why

Spin decides the flight and the landing of every shot, from chips to drives,
so the owner wants it measured on all of them. PiTrac reads spin from the
ball's dimples; on this hardware that does not work: on 2026-11-13 PiTrac's
dimple front-end, reproduced on correctly aligned frames of a resting ball
turned ~10° by hand, showed no score peak at the true turn, while the same
machinery found the turn as soon as a pen stroke was left in the image
(`sp1_vision/strobe_runs/2026-11-13_dimple_test/`). The cameras deliver MJPEG
(8×8 blocks about a dimple's size) and the flash comes from almost the
camera direction. So spin comes from **marks drawn on the ball**.

The goal from the logbook stands: a 3000 rpm draw and a 5000 rpm fade must
be told apart reliably, and spin values should be plausible against a
commercial launch monitor on the same shot.

## What gets built — four parts, in this order

1. **Mark map and stencil** — the pattern on the ball and the printed
   two-part stencil to draw it. First, so the owner can print and mark the
   5 balls while the software is written.
2. **Mark detection and ball orientation** — per ball image: find the marks,
   classify their shapes, identify them on the map, compute the ball's
   absolute orientation. Validated on a resting ball turned by known amounts.
3. **Offset trigger** — firmware and recording: each camera gets its own
   edge and its own flash, the two offset by about 1 ms.
4. **Trajectory and spin from offset images** — ball position from a fit to
   all observation rays with their exact times; spin from orientation pairs.

Each part is usable and testable before the next starts.

## Goals

- Spin rate and axis (backspin, sidespin) for every shot type, chip to drive.
- Unambiguous rate up to at least 12,000 rpm (no aliasing: a ball turning
  360° between two images must not read as zero).
- Rate precise enough to separate 3000 from 5000 rpm with a wide margin.
- Five identically marked balls, any of which works with the same map.
- Short exposures (0.5 ms as today), keeping the door open for outdoor use.

## Non-goals

- Strong sunlight. The owner wants outdoor use eventually, but "the real
  sunlight problem comes later" (a narrow 850 nm filter is the likely fix;
  not on the hardware list, ask before proposing it).
- Live, in-device processing in `pitrac_lm`. This design is the offline
  chain in `sp1_vision`, as the putt and chip analysis is today; the live
  version comes later.
- PiTrac's Gabor/dimple path. Not removed, not used.
- A camera or lens change.

## Anti-goals (a failure even if it technically works)

- **Aliased spin**: any method that compares two images 10 ms apart without
  first knowing the rate to within half a turn. It reads 6000 rpm as 0
  without noticing.
- A stencil and a software map that can drift apart (two hand-maintained
  copies of the mark positions).
- Marks that only work on the side of the ball facing the camera at
  address. The ball turns up to more than a full revolution between frames;
  any image may show any side.
- Frames matched to shots by "the next frame after the trigger". In trigger
  mode the buffer holds frames from before the switch or from the previous
  shot (2026-11-13). Match by arrival time and prove the alignment
  (interleaved dark shots or equivalent), as `trigger_sweep.assign_frames`
  and `2026-11-13_pulse_test/shot_frames.py` do.

## Constraints (measured, not assumptions)

- Ball radius in the image ≈ 44 px at 45 cm (≈ 2.06 px per mm on the ball
  near its centre). Range in use 40–70 cm.
- Ink: of several pens only a **3 mm permanent marker (Edeka store brand)**
  stays clearly dark at 850 nm; most felt pens vanish. A 3 mm stroke is
  ≈ 6 px wide in the image.
- Flash: +17 / +34 / +50 / +75 / +123 grey levels (ball minus surround) at
  10 / 20 / 30 / 50 / 100 µs, 0.5 ms exposure, gamma 72, both cameras alike.
- Trigger: exposure starts ≈ 0.78 ms after the rising edge, both cameras
  within 25 µs, jitter < 25 µs, one frame per edge, no held-back frame when
  matched by arrival; both cameras follow every edge at 100 fps and only
  every other edge at 105 fps and above. Teensy firmware v0.3
  (`SHOT`, `TRIG_RUN`), cam1 = pin 4, cam2 = pin 5.
- The IR beam is flat: brightness halves ~9° above the camera axis at 45 cm
  (ball leaves the light before it leaves the image on high launches).
- The two cameras are calibrated as a stereo pair
  (`sp1_vision/calibration_results/stereo_extrinsics.json`); unit attitude
  against the floor: pitch +1.60°, roll +0.36°.
- No new libraries without asking. OpenSCAD was allowed by the owner, but
  the owner then asked for a real STEP, which OpenSCAD cannot produce; the
  B-rep tool is still to be approved. The owner works in Shapr3D; any STL
  handed over must stay under 10,000 triangles.
- `CLAUDE.md`: approach agreed in plain language before code; tests with
  every code change, as in the rest of `sp1_vision`.

## Decisions made with the owner

### Mark pattern (part 1)

- **20 mark sites at the vertices of a regular dodecahedron**, oriented
  **vertex-up** along the stencil axis (builder's check, my call): the sites
  then sit at heights ±1, ±0.745, ±0.333 of the radius, 10 per half, the
  nearest 19.5° (≈ 7.3 mm of arc) from the seam, so no 9–11 mm cutout is
  split by it. (Face-up, as first written, puts 10 sites only 10.8° from
  the seam and their cutouts across it.) Any orientation with at least that
  clearance is acceptable. Neighbouring sites ≈ 42° apart (≈ 15.6 mm).
  Expect 4–6 marks usable per view (within ~55–60° of the ball centre seen
  from the camera; marks nearer the limb are too foreshortened and are not
  evaluated).
- **Three shapes: dot, bar, cross**, each ≈ 9–11 mm, drawn with the 3 mm
  marker. Bars carry a direction. The assignment of shapes (and bar/cross
  in-plane angles) to sites is chosen by a script so that **every site is
  identifiable from its own shape plus the shapes and positions of its
  visible neighbours**. Each site has exactly three neighbours (the faces
  are pentagons, so no three sites are mutually adjacent). The rule (my
  call, after the builder check): every configuration "a site plus any two
  of its neighbours", with the shapes, the order round the centre and the
  bar/cross directions, occurs only once on the ball. Three visible marks
  in such a V then identify all three.
- Shapes chosen over (B) six large asymmetric glyphs (often only 1–2
  visible; L vs F doubtful at 6 px strokes and blur) and (C) a dot
  constellation (needs many visible dots and a harder geometric matcher).

### Stencil (part 1)

- **Two half-shells closing round the ball**, locating pins, held by a
  rubber band or clip. All 20 marks are drawn in one go without moving the
  ball, so every mark is exactly where the map says relative to all others,
  on all 5 balls. Rejected: one cup and turning the ball (the halves would
  only line up to a few degrees, and that error goes straight into spin).
- Nominal: shell ≈ 1.5 mm thick, inner diameter 42.9 mm (ball 42.67 mm
  plus clearance), cutouts chamfered outward so the 3 mm tip reaches the
  ball surface.
- **Deliverable: a real STEP file** (exact B-rep geometry) per half, so the
  owner can edit it later in Shapr3D. **Not** a STEP converted from an STL
  (the owner explicitly does not want that). It is generated by a script
  from the same mark-map file the analysis reads, using a B-rep CAD kernel
  (OpenSCAD only makes meshes, so it does not qualify for the STEP). Tool
  pending the owner's choice (FreeCAD scripting or CadQuery). An STL for
  direct printing may be exported alongside, < 10,000 triangles. Also hand
  over a table (and a simple drawing) of every site: direction (azimuth,
  elevation in the stencil frame), shape, size, in-plane angle.

### Spin measurement (parts 3–4)

- **Offset trigger** (the owner's idea): cam1's edge at t, cam2's at t + Δ
  with Δ ≈ 1 ms; each camera exposes ~0.5 ms and gets **its own flash**
  inside its own window; the windows do not overlap, so neither camera sees
  the other's flash. Repeated every 10 ms (100 fps).
- Per ball image, the **absolute orientation** of the ball from the
  identified marks and the map. cam2's orientation is brought into cam1's
  frame through the stereo extrinsics.
- **Unambiguous rate** from the cam1/cam2 pair Δ ≈ 1 ms apart (at 12,000 rpm
  ≈ 72°, far below half a turn). **Precise rate** from orientations 10 ms
  (or more) apart, choosing the number of whole turns in between from the
  coarse rate. Axis from the relative rotation.
- **Position** no longer from simultaneous pairs: a constant-velocity (or
  ballistic, builder's call) trajectory fitted to all rays from both
  cameras with their exact times. Rest-ball detection stays as today (the
  ball is still).
- **Output** (my call): total spin and spin-axis tilt in GSPro's
  convention, plus backspin and sidespin, all relative to the ball's
  measured flight direction; chained cam2 → cam1 through the stereo
  extrinsics and to the floor frame through the measured attitude
  (`ground_plane.py`). GSPro sending stays out of scope.
- Fast balls (drive at 75 m/s is in view ≈ 9 ms, about one frame per
  camera) will later need two flashes per exposure, PiTrac-style; not in
  this design's first pass, but the firmware command should not rule it out.

## What is left to the builder

- The exact Δ and flash placement inside each window (start of exposure is
  0.78 ms after the edge; windows must not overlap; leave margin for the
  measured < 25 µs jitter).
- Shape dimensions within 9–11 mm, cutout chamfer, pin and clearance
  details; whether the seam gets a lip.
- The shape-assignment search and the identification algorithm (neighbour
  graph matching, hypothesis-and-verify, etc.), as long as identification is
  unique and wrong identifications are rejected rather than guessed.
- Shape classification method (blob moments, skeleton, template), the
  projection model from image to sphere (orthographic is ~0.5° off at our
  geometry; perspective is better), the pose solver (Kabsch on unit vectors
  is the obvious start).
- Trajectory model and fit details; how cam1/cam2 rays enter one fit.
- File layout inside `sp1_vision` and the mark-map file format (one file,
  read by both the OpenSCAD generator and the analysis).
- Whether the firmware gets a new command or `TRIG_RUN` gets parameters.

## How each part is accepted

1. **Stencil:** the owner prints it and marks 5 balls; a strobe-lit image of
   a marked ball in both cameras shows the expected shapes at the expected
   places (the analysis of part 2 can check this).
2. **Orientation:** resting marked ball, turned by hand by known amounts
   (and about different axes): recovered turn within a few degrees, in
   both cameras; cam1 and cam2 orientations agree after the extrinsics.
   Wrong or ambiguous identifications are refused, not reported. **Sign
   checks**: hand turns of known direction (backspin-like, hook-like) must
   come out with the right sign and axis, since coarse and fine estimates
   would share a sign or axis error and cannot catch it themselves.
3. **Offset trigger:** a flash-delay sweep per camera (as `trigger_sweep`)
   shows each camera sees only its own flash; frames aligned (proven).
4. **Spin:** chips and throws indoors give spin values that are physically
   plausible and consistent between the coarse (1 ms) and fine (10 ms)
   estimates; a spinning ball with a known rate (if a reference can be
   arranged) reads within the target. Full swings once there is a net or
   garage.

## Risks

- **Identification at the limb and under blur.** Marks at 9–11 mm are
  20–23 px; at 30 µs and 75 m/s blur is 2.3 mm (~5 px). Mitigated by
  evaluating only the central cap and by refusing low-confidence matches.
- **Too few marks visible** in a frame (ball partly out of the IR beam on
  high launches, or at the image edge). Then that image gives no
  orientation; the method must work with the images that do.
- **Stencil fit**: if the ball can move in the shell, the marks drift from
  the map. The accept test of part 2 would show it as a systematic error.
- **Asynchronous position fit** is new code replacing working simultaneous
  stereo; its accuracy must be checked against the current method on the
  same recordings before it replaces anything.

## Open with the owner (2026-11-13, end of session)

1. B-rep tool for the STEP: FreeCAD scripting (recommended) or CadQuery.
2. Factory print on the balls (dark at 850 nm): all 5 the same model? Can
   the print be removed or print-free balls used? Otherwise the detector
   rejects every dark blob that does not fit the map, and the ball goes into
   the stencil with the logo between cutouts.
3. Access to a commercial launch monitor as a spin reference? If not,
   acceptance rests on coarse/fine agreement plus hand-turn sign checks.
