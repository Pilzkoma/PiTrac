# Ball centre by cone fit - short design (approved 2026-11-21)

## Why
Part 2 of the ball-marks design (results:
`sp1_vision/strobe_runs/2026-11-21_orientation/results.txt`) found that the
ball centre, not the mark identification, limits the orientation: 1 px of
circle-centre error across the line of sight costs ~1.7 deg, typical tracked
centres scatter 0.66-1.29 mm across (median per putt), and only 13 of 49
rolling comparisons had a centre good enough for the plan's axis target.

## Today
`frame_analysis.refine_ball`: Canny edges (whole pixels) round the Hough
seed, outermost edge per 5-degree bin, MAD-trimmed algebraic circle fit in
the DISTORTED image; then only the circle centre is undistorted
(`cv2.undistortPoints`) and triangulated. Two systematic errors besides the
pixel noise, different in each camera:
- a sphere off the optical axis does not image as a circle centred on its
  centre: the outline's centre lies outward, ~0.4 px at 10 deg off axis and
  ~0.9 px at 20 deg (ball at 44 cm, f 916 px);
- lens distortion bends the outline itself.

## Approach (approved)
**Cone fit.** Subpixel outline points along rays from the seed (as
`refine_ball_by_contrast` already finds them: gradient peak, parabolic
interpolation), each point undistorted to a unit ray, then the cone of rays
tangent to the sphere is fitted: axis direction (2 parameters) + half-angle
(1). The axis is the direction to the ball centre; distance =
r_ball / sin(half-angle). Outliers trimmed as today (MAD).
Rejected: circle fit + analytic offset correction (simpler, but keeps the
distortion error and the whole-pixel edges); fitting a rendered ball to the
whole image (slow, sensitive to marks and shading).

## Order and yardsticks
1. Synthetic first (`sp1_vision/tests/render_ball.py`, known centre): how
   much each error contributes today (projection offset, distortion, pixel
   noise), so it is known what the fix can buy.
2. The cone fit, tested synthetically (centre error with and without marks,
   off-axis positions, near the image edge).
3. Real frames: the three putts of 2026-11-21 through `orientation_check`,
   before / after: across residual, cam1/cam2 agreement, axis error, signs.
The stereo pair keeps its existing gates; whether the triangulation then
uses the cone directions or the old circle centres is decided on the
measured numbers, not in advance (the old refiner's common-bias property
across cameras, `_trimmed_circle_fit`, must not get lost unnoticed).

## Non-goals
Live use in `pitrac_lm`; changing the Hough candidate search or the pair gates.
