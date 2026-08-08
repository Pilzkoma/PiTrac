# Calibration capture sets

```
cam1/, cam2/           the current set, 2026-08-08, 24 pairs — the source of
                       both the intrinsics and the extrinsics in use
2026-08-06_springs/    archived set, superseded (see its own README)
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

The springs behind the camera mount were removed and the plate bolted solid,
which changes the pose of the two cameras relative to each other. This set was
captured to measure the new pose. It ended up replacing the intrinsics as well;
see "What came out".

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
  and 2.4 % on 2026-08-08. This is the check that catches one lens having been
  knocked, and it works because both look at the same board in the same light.
* **The direction the number moves when you turn a lens.** That is what the
  readout is for. Already at a local maximum means focused.
* **Not the absolute value against a remembered one.** Laplacian variance
  scales with the square of scene contrast and with how large the board sits
  in the frame, so it is only comparable within one session under one light.
  The 3028 / 2945 of 2026-08-06 and the 1050 / 1075 of 2026-08-08 are the same
  lenses under different lamps.

### Conditions to aim for

| | |
|---|---|
| Board | `Software/CalibrateCameraDistortions/checkerboard.png`, 9×6 inner corners |
| **Square size** | **24 mm, measured with a ruler** — pass `--square-mm 24.0` |
| Distance | **30–90 cm**, spread across the set |
| Board | **standing, propped or leaned — not hand-held** |
| Tilt | 20–45°, varied in direction |
| Coverage | must include the **lower third of the frame** — see below |
| Pairs | ~24 |
| Exposure | 20 ms is fine once nothing moves |

**Standing, not hand-held.** The archived set was shot hand-held at 20 ms in a
dim room and its per-image reprojection errors run from 0.19 to 3.30 px. With
the board propped and the unit bolted down, nothing moves and the exposure time
stops mattering.

**Depth spread is what pins the baseline.** Subsets of this set that contain
the 25–90 cm sweep give a baseline of 78.2–78.5 mm; subsets built only from the
45–55 cm shots give 81.0–81.7. The archive, which spanned only 35–55 cm, is
loose for exactly this reason.

**The lower third is not optional, and this is the lesson of this set.** The
lower image *corners* really are pointless — floor off to the side, no ball
crosses them, and their radii are within 2 % of the upper corners' anyway. But
vertical coverage as a whole is what separates `cy` from the board's placement,
and `cy` is what **pitch** is made of. Skipping it does not blur pitch, it
biases it, and the reprojection error stays low while it happens. The first 18
pairs of this set stopped at y = 641 of 800 and left pitch uncertain by 1.1°;
the six shots that reached y = 727 cut that to 0.21°.

### The 24 shots, as taken

```
Distance sweep, frontal:      01-07   25, 35, 45, 55, 65, 75, 90 cm
Rotation about vertical:      08-09   50 cm, ±30°
Rotation about horizontal:    10-11   50 cm, ±30°
Image regions:                12-16   left/right top, top centre, left/right middle
Combined tilt and roll:       17-18   50 cm, ~30°
Lower frame, centre:          19-22   35, 45, 55, 75 cm
Lower frame, left and right:  23-24   45 cm
```

All 24 gave a board in both cameras. Shot 01 at 25 cm is at the geometric
limit — the 80 mm baseline leaves only 27 mm of lateral play for a 240 mm
board at that distance — and it was placed inside it, but the stereo solve
drops it as an outlier anyway. 30 cm is the sensible floor.

### Analysing

Not the dashboard's Run button: `/calibration/run` writes no JSON, so the
result stays in a browser window. Run both steps here.

```bash
cd Software/CalibrateCameraDistortions
SET=../../sp1_vision/calibration_images

python3 CameraCalibration.py --images $SET/cam1 --label 1 --save-npz /tmp/cam1.npz \
    --undistort-check /tmp/undistort_cam1.png
python3 CameraCalibration.py --images $SET/cam2 --label 2 --save-npz /tmp/cam2.npz \
    --undistort-check /tmp/undistort_cam2.png

python3 StereoCalibration.py --cam1-npz /tmp/cam1.npz --cam2-npz /tmp/cam2.npz \
    --cam1-images $SET/cam1 --cam2-images $SET/cam2 --square-mm 24.0 \
    --save-json ../../sp1_vision/calibration_results/stereo_extrinsics.json
```

**Intrinsics and extrinsics must come from the same solve.** `CALIB_FIX_INTRINSIC`
means the stereo step absorbs whatever error the camera matrices carry into R
and T; the two are only self-consistent as a pair. Mixing one set's intrinsics
with another's extrinsics is the one combination that is definitely wrong, and
it looks fine in the reprojection error.

## What came out — 2026-08-08, 24 pairs

All 24 gave a board in both cameras; the stereo solve keeps 19. Depth 250–928 mm
against the archive's 350–550, corner coverage y 45–727 of 800 against 71–636.

**Intrinsics**, now the authoritative ones and written into `golf_sim_config.json`:

| | archive | **this set** |
|---|---|---|
| cam1 fx / fy | 922.30 / 917.97 | **900.38 / 897.39** |
| cam2 fx / fy | 923.98 / 919.42 | **899.99 / 895.70** |
| cam1 / cam2 cy | 389.05 / 393.50 | **420.05 / 421.09** |
| focal length | 2.767 / 2.772 mm | **2.701 / 2.700 mm** |
| reprojection RMS | 0.557 / 0.550 px | **0.500 / 0.519 px** |

The reason to believe this set over the archive is not the RMS, which barely
moved. It is that the two cameras now agree with each other: fx to 0.04 %
(against 0.18 %) and cy to 1.0 px (against 4.5 px). They are the same part with
the same lens, so agreement is evidence and disagreement was error.

**Extrinsics**, both sets re-solved against these intrinsics so the comparison
is like for like:

| | with springs | **bolted** |
|---|---|---|
| pitch about X | +0.974° | **−0.923°** |
| yaw about Y | +1.032° | **+0.427°** |
| roll about Z | +0.757° | **−0.851°** |
| baseline | 78.63 mm | **78.28 mm** |

Three things follow.

**The rebuild did not null pitch, it inverted it.** +0.97° to −0.92°: the plate
swung through zero and landed almost symmetrically on the far side. Roll did
the same, +0.76° to −0.85°. Only yaw genuinely improved, +1.03° to +0.43°.

**The baseline never changed.** 78.63 with springs against 78.28 without, from
the same intrinsics — 0.35 mm apart, which is the estimator's own noise. The
apparent 79.83 → 78.59 drop reported earlier was an artefact of the archive's
overestimated fx, not a physical shift. The mount is stable in the one
dimension it had no reason to move in.

**78.3 mm against the CAD's 80.00 is real, and is print shrinkage.** −2.1 %,
ordinary for the part. The archive's 0.2 % agreement with the CAD was luck: it
came from a 35–55 cm set, the narrow-depth condition that produces 81 mm here.

Stability, to say how far these digits can be trusted — halves, odds, evens,
with and without the six lower-frame shots:

| | spread |
|---|---|
| pitch | −0.86° to −0.96° |
| roll | −0.82° to −0.88° |
| yaw | +0.36° to +0.47° |
| baseline | 77.99 to 78.66 mm |

The six lower-frame shots on their own give pitch −0.942° at an RMS of 0.425,
the cleanest sub-solve in the set, and they agree with the full 24 to 0.02°.

None of the angles is near the 3° at which rectification starts costing real
frame height, so none of them needs a mechanical fix. Pitch and roll at ~0.9°
cost about 1.5 % of frame height between them.
