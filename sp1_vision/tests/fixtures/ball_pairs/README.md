# Real stereo pairs, kept because synthetic discs lied

Every detector decision made on 2026-08-10/11 was convincing against
synthetic discs and behaved differently against real golf balls. Twice a
test went green before the function it was meant to exercise had even been
wired in. These eight frames exist so that never costs a capture session
again.

They are captured with the shipped rig, so they can be measured against
`sp1_vision/calibration_results/stereo_extrinsics.json` and the intrinsics
in `golf_sim_config.json`. Assertions live in
`sp1_vision/tests/test_real_frames.py`.

## `lit_from_one_side/` — the formerly blocking case, now the rescue's pin

From the aborted run of 2026-08-11. Clean scene, bare wall, ball plainly
visible in both cameras — and rejected by Hough alone.

| | |
|---|---|
| cam1 Hough | (504.5, 595.5) r 42.7 |
| cam2 Hough | (682.5, 608.5) r 35.0 |
| Hough pair | (−59.2, +78.6, 409.2) mm, **rejected**: reproj 2.71 px, ratio 1.220, size +24.4 % |
| outline rescue | (−59.7, +80.6, 423.9) mm, reproj **0.45 px**, ratio 1.015, size +15.7 % |

The ball is lit from one side; its shadow flank has almost no contrast
against the desk. `HOUGH_GRADIENT` votes along the gradient direction, so
each camera settles on a different part of the outline. 2.71 px is about
10 mm of depth where the whole error budget is 1.8 mm. The outline rescue
in `find_ball_pair` (outermost Canny edge per angular direction, MAD-trimmed
circle fit, seed guards) recovers it; the test pins the rescued position.

Two records set straight on 2026-08-11, both measured rather than assumed:

* the run.json reading of 300 mm for this shot is an **operator error** of
  the run-2 kind — a ball at ~280 mm would subtend ~65 px, and the per-angle
  radial-gradient sweep shows nothing circular between 28 and 60 px except
  the ball at ~38–45 px. The frame is fine for detector work; it carries no
  absolute depth truth. That is what `measured_300mm/` is for.
* the rescued height (+80.6 mm) matches the camera height measured by that
  session's attitude probe shots (100.5 mm − 21.3 mm ball radius = 79.2 mm),
  which the Hough pair's +78.6 also did — height never discriminated
  between them; the residual and the radius consistency do.

## `measured_300mm/` — the only pair with independent ground truth

Captured 2026-08-11 with a tape measure on the desk: ball front edge
**300 mm from the cameras**, optical axes ~115 mm above the surface. Centre
depth is therefore 321 mm plus a small unmeasured camera-front-to-z=0
offset; the test asserts Z ∈ (305, 355) and Y ∈ (65, 105) mm.

Every other fixture's "expected" position is some detector's own output. A
detector that drifts can keep agreeing with itself; it cannot keep agreeing
with the tape.

For the record: raw selection finds it at (−52.4, +86.2, 330.1) mm,
reproj 0.76 px, size +7.6 %, r 58.9/60.8 px (expected ~57 at that range).
This pair is also the frame where outermost-edge collection without a
radius guard exploded onto the cast shadow's rim (60.8 → 87.3 px), which is
why `REFINE_MAX_RADIUS_CHANGE` exists.

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
