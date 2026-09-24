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

* the run.json reading of 300 mm does not belong to this frame. It was
  logged here as an operator error; **it was not one** (corrected
  2026-09-23). This was the first shot of its session, and until commit
  `35ca2db` a grab after a pause returned the frame the driver had held
  back — here the one from when the cameras were opened, before the ball
  was put at 300. The frame is fine for detector work; it carries no
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

Checked against the stale-frame defect on 2026-09-23 and **consistent**:
it too predates the fix, but its Z of 330 sits where the 2026-09-23 run put
the 300 mm mark (316–320 mm on a different setup), not 50 mm off as a
one-shot-late frame would. The ball was evidently in place before the
cameras were opened.

## `cluttered_ball/` — the positive control

2026-08-10 (run 1, `gs_05`), desk facing a full room: loudspeaker with
woofer and tweeter, a sphere on top of it, picture frames, plants. The ball
must come back at roughly **(−37, +83, 475) mm**, and nothing else may.

Run 1 recorded this frame against a reading of 500 mm. It was captured with
the stale-frame defect (fixed in `35ca2db`), so every frame of that run
shows the ball at the PREVIOUS shot's mark: this one lay at 450, which is
what 475 corresponds to once the lens-plane offset and ball radius are
added. The decoy below lay at 350, not the recorded 400.

## `cluttered_decoy/` — why a small residual proves nothing

2026-08-10 (run 1, `gs_03`), same room. This pair once **passed** the 2 px
reprojection gate at 1.96 px — with both cameras locked onto the same
loudspeaker, 1295 mm away and 27 mm *above* the optical axis.

A small residual means the two cameras agree with each other. It has never
meant they are looking at a ball. Whatever this pair returns must be a
resting ball or nothing at all: below the optical axis, inside the
measurement volume, the right size for its own range.

## `far_ball_on_towel/` — a bright surround hides the outline from Canny

2026-09-24 (run 6, `gs_17`): the ball resting untouched at the 650 mm mark on
a black bath towel, lit by a lamp beside the unit. The towel is black to the
eye and **light grey to the cameras** (about 115 grey levels) — textile dyes
go transparent in the near infrared, and so will most "black" cloth under
the 850 nm strobe.

`refine_ball` takes its Canny thresholds from the ROI's median brightness
(0.66× / 1.33× of ~115, so ~75 / 150). This ball's silhouette gradient is
~50: the outline vanishes, only logo and highlights survive (a fit of
r ≈ 11 px), and the refinement refuses in both cameras. Every shot of run 6
beyond 550 mm fell back to raw Hough — here r 27.9 / 26.2 px, 6.5 % apart,
with circles up to 4 px off in one camera on neighbouring shots.

`refine_ball_by_contrast` measures it on the silhouette (r ≈ 26 / 27 px,
0.3 px residual). The test pins both halves: the default path still
returning the raw pair, so the fixture stops being evidence the day
`refine_ball` changes, and the contrast refiner finding the outline.

Why the contrast refiner is an **analysis option** and not a fallback:
applied per shot where Canny refused, it moved run 6's fitted scale from
0.961 to 0.931 — each method has its own small bias, and switching method
with distance turns that into a bias that grows with depth. And it cannot
replace Canny either: on `lit_from_one_side` the brightness-scaled
thresholds are what let only the lit arc through.
