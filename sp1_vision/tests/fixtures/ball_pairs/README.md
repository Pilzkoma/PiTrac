# Real stereo pairs, kept because synthetic discs lied

Every detector decision made on 2026-08-10/11 was convincing against
synthetic discs and behaved differently against real golf balls. Twice a
test went green before the function it was meant to exercise had even been
wired in. These six frames exist so that never costs a capture session
again.

They are captured with the shipped rig, so they can be measured against
`sp1_vision/calibration_results/stereo_extrinsics.json` and the intrinsics
in `golf_sim_config.json`. Assertions live in
`sp1_vision/tests/test_real_frames.py`.

## `lit_from_one_side/` — the blocking case

From the aborted run of 2026-08-11, reading 300 mm. Clean scene, bare wall,
ball plainly visible in both cameras and **rejected**.

| | |
|---|---|
| cam1 detection | (504.5, 595.5) r 42.7 |
| cam2 detection | (682.5, 608.5) r 35.0 |
| triangulates to | (−59.2, +78.6, 409.2) mm — the height is right, so it *is* the ball |
| rejected on | reproj 2.71 px, radius ratio 1.220, size +24.4 % |

The ball is lit from one side; its shadow flank has almost no contrast
against the desk. `HOUGH_GRADIENT` votes along the gradient direction, so
each camera settles on a different part of the outline. 2.71 px is about
10 mm of depth where the whole error budget is 1.8 mm.

**Turning this pair into an accepted, correctly located ball is the
definition of done for the detector work.**

## `cluttered_ball/` — the positive control

2026-08-10, reading 500 mm, desk facing a full room: loudspeaker with woofer
and tweeter, a sphere on top of it, picture frames, plants. The ball must
come back at roughly **(−37, +83, 475) mm**, and nothing else may.

## `cluttered_decoy/` — why a small residual proves nothing

2026-08-10, reading 400 mm, same room. This pair once **passed** the 2 px
reprojection gate at 1.96 px — with both cameras locked onto the same
loudspeaker, 1295 mm away and 27 mm *above* the optical axis.

A small residual means the two cameras agree with each other. It has never
meant they are looking at a ball. Whatever this pair returns must be a
resting ball or nothing at all: below the optical axis, inside the
measurement volume, the right size for its own range.
