# Calibration capture sets

```
cam1/, cam2/           the current set — what the tools read and write
2026-08-06_springs/    archived set, superseded for extrinsics, still the
                       source of the intrinsics (see its own README)
```

`cam1/gs_NN.png` and `cam2/gs_NN.png` with the same NN are one simultaneous
pair, captured behind a `threading.Barrier` at under 1 ms skew. Matching
filenames across the two directories are what make the stereo solve possible;
sequential per-camera series cannot yield extrinsics.

**The capture tools always write into `cam1/`, `cam2/` and always number after
whatever is already there** — `_pair_count() + 1` in the dashboard, `existing`
in `cli_calibrate.py`. The dashboard's `IMAGE_ROOT` is hard-coded and takes no
argument. So a new set means moving the old one into a dated directory first,
or the analysis silently averages two different mount geometries into one
answer. That is why `2026-08-06_springs/` exists.

## The current set — 2026-08-08, springs removed

The springs behind the camera mount were removed and the plate bolted solid.
That changes the pose of the two cameras relative to each other, so the
extrinsics had to be measured again. **Only the extrinsics.** No lens was
touched, so focal length, principal point and distortion are unchanged, and
the archived set measures those better than this one can — it has full-frame
board coverage, which the unit sitting on the ground cannot reach.

### Capturing

Use the dashboard at `/calibration`, not the CLI: it reports board detection
per shot, so an unusable frame surfaces while the board is still in front of
you rather than twenty shots later.

Before the first shot, check focus **on the dashboard's sharpness readout,
with the board in view and `on_board` true.** Do not use
`cli_calibrate.py --focus` for this — it calls `sharpness_score`, the centred
ROI, and will happily report the texture of the wall behind a board held low
in the frame. That is exactly how a 5.4x focus error stayed hidden once
already.

Two things to read from it, and one not to:

* **The two cameras against each other.** They were within 3 % on 2026-08-06
  and should still be. This is the check that catches one lens having been
  knocked, and it works because both look at the same board in the same light.
* **The direction the number moves when you turn a lens.** That is what the
  readout is for. Already at a local maximum means focused.
* **Not the absolute value against a remembered one.** Laplacian variance
  scales with the square of scene contrast and depends on how large the board
  sits in the frame, so it is only comparable within one session under one
  light. The 3028 / 2945 recorded on 2026-08-06 describe that evening's lamp
  and that evening's board distance, nothing more. Measured 2026-08-08 with
  the board propped: 1035–1062 and 1066–1083, a factor of 2.8 lower and 2.4 %
  apart — dimmer room, same relative agreement, no evidence of drift.

If focus has drifted, the intrinsics moved with it and the archived `.npz`
can no longer be trusted; that is a bigger job than this one and needs its own
capture with full-frame coverage.

### Conditions to aim for

| | |
|---|---|
| Board | `Software/CalibrateCameraDistortions/checkerboard.png`, 9×6 inner corners |
| **Square size** | **24 mm, measured with a ruler** — pass `--square-mm 24.0` |
| Distance | **30–90 cm, varied** — the widest spread you can reach |
| Board | **standing, propped or leaned — not hand-held** |
| Tilt | 20–45°, varied in direction, across the set |
| Pairs | ~30, expecting 4–5 to be dropped |
| Exposure | 20 ms is fine once nothing moves |

Two of these are the whole point of recapturing rather than reusing:

**Standing, not hand-held.** The archived set was shot hand-held at 20 ms in a
dim room and its per-image reprojection errors run from 0.19 to 3.30 px. With
the board propped and the unit bolted to the floor, nothing moves and the
exposure time stops mattering. This is the single largest improvement
available, and it costs nothing.

**30–90 cm, not 35–55.** A short depth range leaves the baseline loosely
constrained — splitting the archived set in half gave 80.24 and 79.31 mm from
the same hardware. Depth spread is what pins the translation down.

Not worth chasing: board coverage of the lower image corners. Those are floor
off to the side, no ball ever crosses them, and the radial terms they would
constrain are already measured — the upper corners sit at 747 px from the
principal point against the lower corners' 763, within 2 % of the same radius.
The lower *centre* is worth reaching, because that is where the ball rests.

### Analysing

Not the dashboard's Run button. `/calibration/run` recomputes the intrinsics
from whatever is in `cam1/`, `cam2/` and feeds those into the stereo solve,
with no way to say "keep the measured ones". Against a set captured on the
ground that means weakly-constrained distortion and principal point silently
replacing good numbers. Capture on the dashboard, then solve here:

```bash
cd Software/CalibrateCameraDistortions

# intrinsics from the archived full-coverage set
ARCHIVE=../../sp1_vision/calibration_images/2026-08-06_springs
python3 CameraCalibration.py --images $ARCHIVE/cam1 --label 1 --save-npz /tmp/cam1.npz
python3 CameraCalibration.py --images $ARCHIVE/cam2 --label 2 --save-npz /tmp/cam2.npz

# extrinsics from the new set, intrinsics held fixed
python3 StereoCalibration.py --cam1-npz /tmp/cam1.npz --cam2-npz /tmp/cam2.npz \
    --cam1-images ../../sp1_vision/calibration_images/cam1 \
    --cam2-images ../../sp1_vision/calibration_images/cam2 \
    --square-mm 24.0 \
    --save-json ../../sp1_vision/calibration_results/stereo_extrinsics.json
```

`CALIB_FIX_INTRINSIC` is what makes this legitimate: the camera matrices come
from the `.npz` and only R and T are solved. Six parameters against 30 pairs ×
54 points × 2 cameras is heavily overdetermined, which is why this set can
afford to be weak where the archived one is strong.

### Reading the result

Expect the baseline near 79.8 mm again — it is a property of the printed part
and the springs did not sit between the two lenses. A baseline that moved by
more than a millimetre means something else changed, most likely the square
size or a swapped USB cable, and should be understood before the numbers are
believed.

The angles are the actual result. Against the old pitch 1.070°, yaw 0.756°,
roll 0.925°: pitch and yaw should now be near zero if the rebuild did what it
was meant to, and roll should be roughly unchanged, because roll is rotation
about the optical axis and a tip/tilt mount never controlled it. Roll near a
degree is not a defect and needs no mechanical fix — rectification absorbs it,
and it stays well under the 3° at which it starts costing frame height.

Check which angle is which against the JSON's own labels rather than from
memory. `rotation_deg` in `calibration_results/stereo_extrinsics.json` names
all three, and they have been transposed by one position before.
