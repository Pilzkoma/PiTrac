# Stereo Triangulation and World Geometry Design

**Date:** 2026-08-09
**Sub-project:** SP1 — Core Vision System
**Status:** Draft (pending user review)

## Problem

The 2026-08-09 calibration produced intrinsics and extrinsics that are verified
and trusted, but nothing consumes the extrinsics. The ball-position path is
still PiTrac's monocular radius method, and the world-geometry constants still
hold PiTrac's numbers for a physically different machine. Two consequences:

**Accuracy left on the table.** At the decided 50 cm working distance the
stereo pair resolves roughly 3.65 mm of depth per pixel of disparity error, or
about 1.8 mm at half-pixel correspondence. The radius method's precision is
governed by how well a Hough circle's radius can be estimated, which is a much
softer quantity.

(CLAUDE.md quotes 3.55 mm for the same figure. Both are correct for their
inputs: 3.55 uses Z = 500 mm and b = 78.28 mm, this document uses the actual
line-of-sight Z = 508.7 mm and the committed b = 78.71 mm. The difference is not
a disagreement, and the baseline question below is a separate matter.)

**The device's attitude in the world is unmeasured.** The measured rotations —
pitch −0.94°, yaw +0.36°, roll −0.82° — describe *camera 1 against camera 2*.
They say nothing about how the pair together sits against the floor. The
housing is level by construction and the residual camera tilt is an artefact of
the mount, but no measurement pins the optical frame to the world. An absolute
pitch error rotates the whole velocity vector and lands 1:1 in VLA; an absolute
yaw error lands 1:1 in HLA.

## Findings that shape the design

### The constant named in CLAUDE.md is not the one the code reads

`kCameraNPositionsFromOriginMeters` exists only in PiTrac's documentation
(`docs/camera/camera-calibration.md:130`) and in the dead
`gs_test.cpp.B4_NEW_TEST`. The live code declares and loads
`kCameraNPositionsFromExpectedBallMeters` (`gs_camera.h:100-102`,
`gs_config.cpp:169-171`).

Its only consumer in the live path is `gs_camera.cpp:455-458`, which takes
`CvUtils::GetDistance(...)` — the vector's **norm**, used as the expected
line-of-sight distance that seeds the ball search radius. The direction and
signs of the three components are never evaluated.

For our geometry: optical axis 115 mm above the floor, a resting ball's centre
at 21.3 mm, so the camera sits 93.7 mm above the ball centre at 500 mm
horizontal separation. Line of sight = √(500² + 93.7²) = **508.7 mm**. The ball
sits 10.6° below the bore, comfortably inside the ±23.95° vertical half-field
(2.400 mm sensor height on 2.701 mm focal length).

The value to write is therefore any vector of norm 0.509 m. Written honestly in
PiTrac's own mixed convention (X, Y signed camera-relative with Y up; Z a
horizontal magnitude) that is `[0.0, 0.0937, 0.500]`. If the ball is placed on
the *unit's* centreline rather than camera 1's, X becomes ∓0.039 and the norm
moves to 0.510 — a 0.3% change in a search-radius prior, i.e. irrelevant.

### A second constant belongs to this work and is not on the task list

`kCamera2OffsetFromCamera1OriginMeters` = `[0.00, -0.19, 0.0]` is added in
`gs_camera.cpp:700-703` and `lm_main.cpp:865-868`. These are PiTrac's 19 cm of
*vertical* camera stacking — their camera 1 sits on the top floor. Ours sit side
by side. Until this is corrected the delta path carries a 19 cm offset that does
not exist.

### Two frames that disagree on which way is up

| | X | Y | Z | Handedness |
|---|---|---|---|---|
| `stereo_extrinsics.json` (OpenCV) | right | **down** | forward | right-handed |
| PiTrac camera-perspective (`gs_camera.cpp:1132`, `:1157`) | right | **up** | forward | left-handed |

`gs_camera.cpp:1157` states it outright: *"Y distance, positive is upward"*.
The cross-check is `kCamera2OffsetFromCamera1OriginMeters` itself: PiTrac's
camera 2 sits 19 cm *below* camera 1 and the constant reads −0.19, which is only
consistent with Y up.

Every conversion between the two must negate Y. This is the single most likely
place for a silent sign error in the whole task, which is why the design
confines it to one function.

### The handedness of the pair, confirmed three ways

`translation_mm` in the extrinsics JSON is the **raw** `T` from
`cv.stereoCalibrate`, written without conversion
(`Software/CalibrateCameraDistortions/StereoCalibration.py:236`). OpenCV's
convention is X₂ = R·X₁ + T, so T is camera 1's origin expressed in camera 2's
frame.

T_x = **+78.710 mm**, therefore camera 2 sits at negative X in camera 1's frame:
camera 2 is to camera 1's left *as the unit looks out*. A golfer faces the unit
and sees that mirrored, so camera 1 is the golfer's left module.

Three independent confirmations agree:

1. The sign of T_x, as derived above.
2. `sp1_vision/camera_paths.py:26-39`, which records two physical experiments
   (occluding a lens, and cross-correlating a patch 76 px between streams) and
   states the resolution explicitly: *"Camera 1 is on your left and on the
   cameras' right. Both statements describe the same module."*
3. The user's direct statement, 2026-08-09.

Note that the naive reading — "T_x is positive, so camera 1 is on the right" —
gives the opposite answer. The mirror between the unit's frame and the player's
frame is the entire difference.

Note also that the `"frame"` field in `stereo_extrinsics.json` is a hardcoded
string literal (`StereoCalibration.py:241-242`), not a value derived from the
solve. It asserts the answer; it does not evidence it. That it happens to be
correct is established by the three points above, not by its presence.

Computed exactly, camera 2's optical centre in camera 1's frame is
−RᵀT = `[-78.720, -0.890, +1.957]` mm (OpenCV frame), which in PiTrac's Y-up
frame is `[-0.078720, +0.000890, +0.001957]` m — practically
**`[-0.0787, 0, 0]`**. The rotation matters for the small components (the
approximation −T alone gets Y and Z wrong by a factor of two or more), which is
the argument for computing this value from R and T in code rather than typing it.

### The baseline is recorded twice, with two values

| Source | Value |
|---|---|
| `stereo_extrinsics.json`, ‖T‖ (committed, will be consumed) | **78.749 mm** |
| CLAUDE.md, `calibration_images/README.md`, LOGBOOK | **78.28 mm** |

0.6%, which propagates linearly into every triangulated depth, and thence into
ball speed and carry — roughly 0.4 m/s at 70 m/s. The README records a
subset-to-subset spread of 77.99–78.66 mm, and 78.749 falls just outside it,
which suggests the committed JSON is not from the same run as the 78.28 figure
(different pair selection, or the second intrinsics source).

**This design does not reopen the calibration.** It notes that the code will
read the file, not the documentation, and that the measurement run specified
below resolves the question empirically as a by-product.

### CLAUDE.md's sensor-size entry is stale

CLAUDE.md lists `CameraHardware::sensor_width_`/`sensor_height_` as still
holding IMX296 values. They are overridden unconditionally in the V4L2 init path
(`v4l2_interface.cpp:831-832`, applied at `camera_hardware.cpp:486-493`). The
19% vertical error is already fixed; `camera_hardware.cpp:251-252` is only the
default that gets overwritten. This matters here because it is what makes a
radius-method-versus-triangulation comparison meaningful rather than a
comparison against a known systematic error.

### Nothing records which intrinsics the extrinsics were solved against

`stereo_extrinsics.json` stores R, T, the pair list and the square size, but no
fingerprint of the camera matrices fed to `CALIB_FIX_INTRINSIC`. Given the
project's own rule — intrinsics and extrinsics are only self-consistent as a
pair — this is a real provenance gap. Recommended: add a hash or a copy of K₁,
K₂ to the JSON so a loader can refuse a mismatched pairing. Small change, and it
closes the one failure mode that is invisible in the reprojection error.

## Scope

The work splits into two blocks. **This design covers Block 1 only.**

### Block 1 — triangulation as a measuring instrument (this design)

Python, in `sp1_vision/`, alongside the existing calibration tooling. Delivers a
verified triangulation function and a measurement run that produces the world
geometry numbers.

Rationale for doing this first: building triangulation directly as a C++ layer
inside `pitrac_lm` means debugging it where no trusted reference exists. If the
radius method and triangulation disagree by 4 cm, nothing in the running system
says which is right. A tape measure is the arbiter, and it does not participate
in a `pitrac_lm` run.

### Block 2 — triangulation in the runtime path (separate design)

The C++ port of the same arithmetic, running alongside the radius method with
both logged. Its acceptance criterion is reproducing Block 1's numbers on the
same committed test images, which is also the guard against two implementations
drifting apart.

For the *flying* ball Block 2 is gated on `WaitForCam2Trigger`, still a
`JETSON_STUB`. Two unsynchronised cameras at 120 FPS see a 60 m/s ball 500 mm
apart between frames; triangulating that is meaningless. The resolution is the
strobe — both global shutters open, one flash defines the instant for both
sensors — but that requires a camera-2 capture path to exist at all.

## Design — Block 1

### Where the origin is — the answer to the original question

The task was framed as "first establish where the origin lies and what
convention PiTrac expects there". Having read what the code actually does, the
honest answer is that **there is no single world origin to define**, and looking
for one is what makes the task appear larger than it is. The three constants are
each relative to a different thing:

| Constant | Referenced to | What we owe it |
|---|---|---|
| `kCameraNPositionsFromExpectedBallMeters` | the expected ball | a norm, 0.509 m |
| `kCamera2OffsetFromCamera1OriginMeters` | camera 1's optical centre | R and T, converted |
| `kCameraNAngles` | the bore against world horizontal | a measurement |

PiTrac's documentation does define an origin — "the point on the floor directly
below where the camera is focused" (`camera-calibration.md:130`) — but that
belongs to `kCameraNPositionsFromOriginMeters`, a constant this codebase no
longer has. Only the third row needs anything measured, and that is what the
capture run below produces.

For the triangulation itself the natural frame is camera 1's optical centre,
because that is what `triangulatePoints` returns with P₁ = [I|0]. Everything
else is a rigid transform away from it.

### Modules

**`sp1_vision/stereo_geometry.py`** — the only place frames and units are
touched.

Loads `stereo_extrinsics.json` and the intrinsics from `golf_sim_config.json`
into a `StereoRig` carrying K₁, D₁, K₂, D₂, R, T (metres) and image size.
Provides the projection-matrix pair and the one named conversion into PiTrac's
Y-up frame. Nothing else in the codebase performs a frame or unit conversion.

Validation at load, failing loudly:

| Check | Bound | Catches |
|---|---|---|
| ‖T‖ | 0.070–0.090 m | wrong square size, wrong file |
| R against identity | < 3° | swapped or corrupt extrinsics |
| fx, both cameras | within 10% of 900 | mismatched intrinsics source |
| image size | 1280×800 | wrong capture mode |

**`sp1_vision/triangulate.py`** — the arithmetic.

- `triangulate_point(rig, uv1, uv2) -> np.ndarray` — XYZ in camera 1's frame,
  metres. `undistortPoints` to normalised coordinates, then `triangulatePoints`
  with P₁ = [I|0], P₂ = [R|t].
- `reprojection_error(rig, xyz, uv1, uv2)` — projects the solved point back into
  both images and returns the residuals.

The reprojection residual is a per-measurement validity flag, not decoration. It
is necessary and not sufficient: a small residual means the two rays intersect,
not that the scale is right. Scale is the tape measure's job. This distinction
is the same one that cost a session during calibration and is restated here
deliberately.

**Correction, established during implementation (2026-08-09):** an earlier draft
of this section claimed the residual also catches swapped cameras and inverted
signs. It does not, and the claim was dangerous because the flag was to be
trusted on that basis. On a rectified rig — R = I, translation along X, matched
intrinsics — a swapped correspondence solves in closed form to Z′ = −Z,
X′ = −(X+b), Y′ = −Y. That is an exact ray intersection, so the residual is
identically zero for every point. Equivalently E = [T]ₓR is skew-symmetric at
R = I, making the epipolar constraint swap-invariant. An inverted translation is
worse still: the residual is computed from the same extrinsics it would have to
indict, so it is self-consistent with them by construction.

The residual's swap sensitivity is roughly proportional to the rig's departure
from rectified, and is carried almost entirely by **pitch**:

| rig pitch | swap residual |
|---|---|
| 0.00° | 0.00 px |
| 0.10° | 2.30 px |
| 0.50° | 11.5 px |
| 0.92° (measured) | 21.2 px |

On this rig's yaw alone (+0.43°) a swapped pair gives 0.32 px, and on roll alone
(−0.85°) 3.4 px, falling to 1.5 px for an on-axis point. So the residual does
detect a swap here — but only because the mount happens to carry pitch, and it
would fall silent if the mount were ever re-shimmed to null it, which is exactly
what the 2026-08-08 rebuild was attempting.

**The structural swap guard is the sign of Z**, which holds for any rig: a
swapped pair yields Z′ = −Z exactly. Any consumer of the residual must require
Z > 0 alongside it, never the residual alone.

**`sp1_vision/ground_plane.py`** — plane and attitude.

Fits a plane to N triangulated ball centres; returns normal, pitch, roll and
per-point residuals. Additionally reports the point spread in X and Z: points
lying near a line give a well-fitting but poorly determined plane, and the
residual alone will not show it. Reporting conditioning alongside the residual
is the direct lesson from the unconstrained `cy`.

**`sp1_vision/cli_triangulate.py`** — the measurement run.

Takes a directory pair, detects the ball in both images with the same detector
and the same parameters, triangulates, and writes a table: per position the 3D
coordinate, the reprojection residual, and the deviation from the entered tape
measurement.

### Capture protocol

Capture reuses `sp1_vision/calibration_capture.py` — same simultaneity, same
paired filenames, and camera binding by USB port path is already solved there.
No new capture path. Binding **must** go through `camera_paths.device_for_camera()`;
`/dev/videoN` is not a stable identity, since both modules report `UC762`.

- **8–10 ball positions on the floor**, spread over 35–70 cm of distance and
  across the image width, so the plane is supported in both directions.
- **Tape distance to the lens plane recorded for each position.**
- **2 additional positions along the intended target line**, same capture,
  deliberately placed. This is what makes yaw observable and it cannot be
  retrofitted without repeating the run.

### What the run measures

Three results from one capture series:

1. **Is triangulation correct at all?** Absolute distance against tape. At
   508.7 mm the disparity is 139 px and the sensitivity is 3.65 mm of depth per
   pixel of disparity error, so roughly 1.8 mm at half-pixel detection.
   Disagreement beyond about 5 mm is not noise.

2. **How does the device sit?** A plane through the ball centres yields pitch
   and roll. Every resting golf ball has its centre at exactly 21.3 mm above the
   floor, so the centres lie in a plane parallel to the floor by construction —
   verification and world-geometry measurement are the same experiment. The two
   target-line positions supply yaw, which the floor plane cannot: a plane is
   rotationally symmetric about its normal.

3. **Which baseline is right.** A 0.6% scale error displaces a measured 400 mm
   translation by 2.4 mm — marginal for one measurement, resolvable by fitting a
   scale factor across five or six displacements. Measuring *differences* rather
   than absolute positions isolates scale from any origin offset, and settles
   78.28 against 78.749 without touching the calibration.

   The limiting instrument here is the tape, not the triangulation. Displacement
   between two marked floor positions is readable to about ±1 mm, which over
   400 mm is 0.25%; across six displacements the standard error of a fitted
   scale factor is roughly 0.10%. Against a 0.6% signal that is a comfortable
   margin — but it is a margin that depends on marking the floor positions
   carefully, not on the camera work.

### Error handling

- Load-time validation as tabulated above; abort, do not warn-and-continue.
- Per-measurement reprojection residual above threshold: flag the row, do not
  silently include it in the plane fit.
- Plane fit reports RMS residual **and** conditioning; refuses to report an
  attitude when the points are near-collinear.
- **Nothing is written into `golf_sim_config.json` automatically.** The tool
  emits numbers; a human enters them. Given that file's history, an automatic
  write is risk without benefit.

### Testing

TDD, against synthetic geometry rather than images:

- Construct a rig with known R and T, project known 3D points, triangulate,
  assert recovery to 1e-9.
- The Y-flip into PiTrac's convention gets its own test.
- Plane fit against synthetically tilted planes, including the ill-conditioned
  near-collinear case, which must raise rather than return a number.
- A swapped-camera rig, asserting the guards fire rather than returning silently
  mirrored depth. Note which guard: on a pitched rig the residual fires, on a
  rectified one only the depth sign does, and both cases need a test so the
  difference is on the record rather than rediscovered.

### Known inaccuracy accepted in v1

The centre of a sphere's silhouette is not the projection of the sphere's
centre; it migrates outward as the off-axis angle grows. At our geometry this is
of order 0.3 px and partly cancels between the two cameras. That is below
detection noise and is left uncorrected, recorded here so it is not
rediscovered later as an unexplained residual.

Far more important than correcting it: **both images must be evaluated with the
same detector and the same parameters.** A difference there is larger than this
effect by a wide margin.

## Non-goals

- Redoing any part of the 2026-08-09 calibration.
- Solving against `2026-08-06_springs/`.
- Any adjustment to the mount.
- Rectification and disparity search. Justified for dense depth maps; for a
  single ball centre it is cost without return. A one-off epipolar diagnostic is
  fine; it does not enter the runtime path.
- Radar. Considered and declined for v1 and for v2-by-default: Doppler gives
  radial velocity, not position, and FMCW range resolution at ISM bandwidths is
  ~600 mm against the ~2 mm at issue here. It would genuinely improve ball speed
  (sub-1% is unremarkable for Doppler, against roughly 1–1.5% for the strobe
  path), but only in combination with camera-derived angles, and it would
  introduce a second uncalibrated direction at the precise moment the first one
  is still unpinned. Revisit only after v1 produces verified numbers and ball
  speed is *measured* to be the limiting error; the cheaper lever at that point
  is the strobe.

## Deliverables

1. Four modules under `sp1_vision/` with tests.
2. A committed capture series with tape measurements.
3. Measured device pitch, roll and yaw against the floor and target line.
4. A resolved answer on the baseline discrepancy.
5. Values ready to enter by hand:
   - `kCameraNPositionsFromExpectedBallMeters` — norm 0.509 m
   - `kCamera2OffsetFromCamera1OriginMeters` — `[-0.0787, 0.0009, 0.0020]`,
     computed from R and T rather than typed
   - `kCameraNAngles` — from the measured attitude
6. A CLAUDE.md correction for the stale sensor-size entry.

## Open risks

- The baseline discrepancy is unresolved until the run is done. If it turns out
  the committed extrinsics are from a different solve than the documented
  figures, that is a finding to act on before Block 2, not after.
- No provenance links `stereo_extrinsics.json` to the intrinsics it was solved
  against. Recommended fix noted above.
- Yaw depends on the target-line positions being placed accurately. The floor
  plane cannot cross-check them; their accuracy is the accuracy of the placement.
