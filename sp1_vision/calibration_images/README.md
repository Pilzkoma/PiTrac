# Calibration capture set — 2026-08-06

The raw evidence behind every optical constant in `golf_sim_config.json`. Kept
so the calibration can be recomputed without recapturing: the numbers took an
hour of standing in front of the cameras holding a board, and a better analysis
later should not have to repeat that.

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

```bash
cd Software/CalibrateCameraDistortions
python3 CameraCalibration.py --images ../../sp1_vision/calibration_images/cam1 \
    --label 1 --save-npz /tmp/cam1.npz --undistort-check /tmp/undistort_cam1.png
python3 CameraCalibration.py --images ../../sp1_vision/calibration_images/cam2 \
    --label 2 --save-npz /tmp/cam2.npz --undistort-check /tmp/undistort_cam2.png
python3 StereoCalibration.py --cam1-npz /tmp/cam1.npz --cam2-npz /tmp/cam2.npz \
    --cam1-images ../../sp1_vision/calibration_images/cam1 \
    --cam2-images ../../sp1_vision/calibration_images/cam2 \
    --square-mm 24.0 --save-json ../../sp1_vision/calibration_results/stereo_extrinsics.json
```

## What came out

| | cam1 | cam2 |
|---|---|---|
| fx / fy (px) | 922.30 / 917.97 | 923.98 / 919.42 |
| focal length | 2.767 mm | 2.772 mm |
| reprojection RMS | 0.557 px | 0.550 px |
| images dropped | 4 | 5 |

Baseline 79.83 mm against 80.00 from `Hardware/JetsonLM.step`. Relative
rotation: pitch 1.070°, yaw 0.756°, roll 0.925°.

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
