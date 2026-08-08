# Calibration capture set — 2026-08-06 (springs fitted)

The raw evidence behind every optical constant in `golf_sim_config.json`. Kept
so the calibration can be recomputed without recapturing: the numbers took an
hour of standing in front of the cameras holding a board, and a better analysis
later should not have to repeat that.

> **Its extrinsics no longer describe the hardware.** On 2026-08-08 the springs
> behind the camera mount were removed and the plate bolted down solid, which
> moves the two cameras relative to each other. The rotation and translation
> below are the *old* geometry and are kept as the record of it.
>
> **Its intrinsics do still describe the hardware.** No lens was touched, and
> focal length, principal point and distortion are properties of the lens and
> sensor, not of how the pair is aimed. This set therefore remains the source
> for the `.npz` files fed to `StereoCalibration.py --cam1-npz/--cam2-npz`,
> and it is the better source: it has full-frame board coverage, which a set
> captured with the unit sitting on the ground cannot reach.

The set that supersedes it for extrinsics lives one level up in `cam1/`,
`cam2/`.

20 simultaneous pairs. `cam1/gs_NN.png` and `cam2/gs_NN.png` with the same NN
are one pair, captured behind a `threading.Barrier` — measured skew under
1 ms. Filenames matching across the two directories is what makes the stereo
solve possible; sequential per-camera series cannot yield extrinsics.

## Conditions

| | |
|---|---|
| Cameras | Arducam B0332, OV9281, 70°(H) M12, USB 2.0 |
| Resolution | 1280×800 MJPG |
| Exposure | manual, 20 ms, gain 20 — fixed so the series is comparable |
| Board | `Software/CalibrateCameraDistortions/checkerboard.png`, 9×6 inner corners |
| **Square size** | **24 mm, measured with a ruler** |
| Distance | 35–55 cm, varied |
| Lighting | room light plus a lamp; the room was dim and the exposure is long |

**The square size is not decoration.** It scales the translation vector
linearly and therefore sets the stereo baseline outright. Assuming 20 mm
against this 24 mm board produced a baseline of 66.40 mm where the truth is
79.83, which looked exactly like a misbuilt mount. Pass `--square-mm 24.0`.

## Reproducing

Recovers the intrinsics, which is what this set is still for:

```bash
cd Software/CalibrateCameraDistortions
SET=../../sp1_vision/calibration_images/2026-08-06_springs
python3 CameraCalibration.py --images $SET/cam1 \
    --label 1 --save-npz /tmp/cam1.npz --undistort-check /tmp/undistort_cam1.png
python3 CameraCalibration.py --images $SET/cam2 \
    --label 2 --save-npz /tmp/cam2.npz --undistort-check /tmp/undistort_cam2.png
```

The stereo step that followed is kept here for the record of how the old
geometry was measured. **Do not write its output into
`calibration_results/stereo_extrinsics.json` any more** — that file now belongs
to the post-springs set.

```bash
python3 StereoCalibration.py --cam1-npz /tmp/cam1.npz --cam2-npz /tmp/cam2.npz \
    --cam1-images $SET/cam1 --cam2-images $SET/cam2 --square-mm 24.0
```

## What came out

| | cam1 | cam2 |
|---|---|---|
| fx / fy (px) | 922.30 / 917.97 | 923.98 / 919.42 |
| focal length | 2.767 mm | 2.772 mm |
| reprojection RMS | 0.557 px | 0.550 px |
| images dropped | 4 | 5 |

Baseline 79.83 mm against 80.00 from `Hardware/JetsonLM.step`. Relative
rotation: pitch 1.070°, yaw 0.756°, roll 0.925° — **superseded, see the note at
the top.** Recorded here in full because the post-springs numbers are only
interpretable against them: the point of the rebuild was to take pitch and yaw
out, and that claim can only be checked against what they were.

## Known weaknesses of this set

Hand-held at 20 ms in a dim room, so several frames carry motion blur — the
per-image reprojection errors run from 0.19 to 3.30 px and the analysis drops
the worst. A braced board and more light would tighten it.

Four of the twenty (`gs_10`, `gs_11`, `gs_14`, `gs_20`) are poor for the
intrinsics. Notably they are *not* the worst pairs for the stereo solve, which
ranks `gs_06`, `gs_14` and `gs_08` highest — the two measure different things,
one how well a view fits the lens model, the other how well the two views agree
with each other.

Nothing here spans much depth: 35–55 cm on a 80 mm baseline leaves the baseline
loosely constrained, which is why splitting the set in half gives 80.24 and
79.31 mm. A future set should reach further out.
