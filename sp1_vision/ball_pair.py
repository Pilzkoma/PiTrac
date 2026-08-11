#!/usr/bin/env python3
"""Which of the circles in the two images is the golf ball.

A single image cannot answer that. A golf ball and a loudspeaker cone are
both bright discs, and on 2026-08-10 the loudspeaker won a whole 24-shot
run: the detector returned the strongest circle in each image, and in 17 of
24 frames that was the same background object at the same pixel while the
ball moved across the table. The reprojection residual did not save it
either - in one frame both cameras had locked onto the same loudspeaker, so
the two rays met at 1295 mm with a residual of 1.96 px and the shot was
accepted. A small residual means the cameras agree with each other, not that
they are looking at a ball.

The stereo pair CAN answer it, from three facts that are stated in advance
rather than fitted:

  * a golf ball is 42.67 mm across, so its apparent radius in each image is
    determined by that image's own range to it. An object twice as far away
    must look half as big, and a loudspeaker does not;
  * the ball is somewhere in the declared measurement volume - a depth band
    and a lateral cone the capture protocol names before anything is
    measured;
  * the two rays must actually meet.

None of the three refers to where the answer would be convenient, which is
the property that keeps this from being a way of assuming the result.

The detector upstream is deliberately permissive and this is deliberately
strict. Recall belongs where the pixels are, precision belongs where the
geometry is.
"""

import numpy as np

from sp1_vision import frame_analysis, triangulate
from sp1_vision.ground_plane import GOLF_BALL_RADIUS_M

# The measurement volume, from the capture protocol rather than from the
# data. The protocol asks for 340-700 mm of depth and no more than 0.43 of
# the depth sideways; the bounds below carry margin so that a ball placed
# slightly outside is still found and reported, and it is the analysis - not
# this - that decides whether to keep it.
MIN_DEPTH_M = 0.25
MAX_DEPTH_M = 0.95
MAX_LATERAL_FRACTION = 0.55

# The ball rests on the SAME SURFACE the unit stands on. Its centre is one
# ball radius above that surface and the optical centre is somewhere between
# 40 and 220 mm above it - a property of the housing, known to that accuracy
# from the CAD without measuring anything. So Y, which is positive DOWNWARD,
# is always positive and lands in a narrow band.
#
# This replaces a symmetric +-350 mm bound that was no constraint at all. On
# the 2026-08-11 frames EVERY spurious survivor sat at Y = -216 to -278 mm:
# objects on the wall and the monitor, a quarter of a metre ABOVE the axis,
# which had cleared the volume, the residual and the size gate. Nothing but
# the height distinguishes them, and the height is not a tolerance on the
# answer - a ball above the optical axis is not resting on the table.
MIN_BALL_HEIGHT_M = 0.020
MAX_BALL_HEIGHT_M = 0.200

# A residual above this means the two rays did not really meet. Necessary
# and nowhere near sufficient - see the module docstring.
MAX_REPROJECTION_PX = 2.0

# How far the apparent radius may sit from the size the triangulated range
# implies, as a fraction, in EITHER image.
#
# Hough quantises the radius to about a pixel, which is 2.5% at the 40 px a
# ball shows at half a metre, and a soft silhouette edge adds a little more.
# On the 2026-08-10 frames the correctly located ball came in at +4 to +7%
# every time, while two background objects that survived every other gate sat
# at +22 and +28% - so 20% keeps a threefold margin over the real thing and
# still refuses those. Wider was tried first and let both through.
MAX_RADIUS_ERROR = 0.20

# How far the two apparent radii may differ FROM EACH OTHER, as a fraction.
#
# Not implied by the per-camera check above. 78 mm of baseline against
# 300-700 mm of range makes the ball almost equidistant from both cameras -
# their ranges differ by under 2.5% at the near end - so its two radii agree
# to a few percent whatever the range is. But a pair running +18% in one
# image and -18% in the other passes both per-camera tests while disagreeing
# by 40% with itself, and that is what a pairing of two unrelated circles
# looks like. Observed on real frames: the ball came in at ratios of 0.973,
# 0.981 and 1.071; the junk at 0.739 and 0.795.
MAX_RADIUS_RATIO_ERROR = 0.20

# A pixel of residual and a 5% size error are treated as comparable evidence.
RADIUS_ERROR_WEIGHT_PX = 20.0

# Two surviving solutions further apart than this are different objects, not
# two Hough circles on one ball. Hough routinely returns several concentric
# circles for a single disc and those land within a millimetre or two.
#
# The comparison is a distance and nothing else. An earlier version also
# required the rival's score to be within a factor of the best, which made
# the guard evaporate exactly when it was needed: on clean synthetic data
# two perfectly good solutions scored 0.05 and 0.30, a ratio of six, and the
# guard read that as "no real rival" when both were excellent. Every
# survivor has already passed the volume, residual and size gates, so being
# somewhere else is the whole of what makes it a rival.
AMBIGUITY_SEPARATION_M = 0.03

# What fraction of the pairings that solved at all must have solved behind
# the cameras before that is worth calling a swap. Chance alone puts about
# half of them there, so only a near-sweep is evidence.
MOSTLY_BEHIND_FRACTION = 0.9


class BallPair:
    """The ball, located in both images and in space, with its evidence."""

    def __init__(self, xyz_m, uv1, uv2, radius1_px, radius2_px,
                 reprojection_px, radius_error):
        self.xyz_m = np.asarray(xyz_m, dtype=np.float64)
        self.uv1 = tuple(float(x) for x in uv1)
        self.uv2 = tuple(float(x) for x in uv2)
        self.radius1_px = float(radius1_px)
        self.radius2_px = float(radius2_px)
        self.reprojection_px = float(reprojection_px)
        self.radius_error = float(radius_error)

    @property
    def depth_mm(self):
        return float(self.xyz_m[2] * 1000.0)


def apparent_radius_px(focal_px, range_m):
    """Silhouette radius of the ball at a given range, in pixels.

    A sphere's outline is where the line of sight grazes it, so the angular
    radius is asin(R / d) and the pixel radius f * tan of that. At our
    ranges the difference from the naive f * R / d is under a tenth of a
    pixel, but the exact form costs one square root and cannot drift.
    """
    range_m = float(range_m)
    if range_m <= GOLF_BALL_RADIUS_M:
        raise ValueError(
            "range {:.4f} m is inside the ball itself".format(range_m))
    return float(focal_px) * GOLF_BALL_RADIUS_M / np.sqrt(
        range_m ** 2 - GOLF_BALL_RADIUS_M ** 2)


def _radius_error(rig, xyz, radius1_px, radius2_px):
    """Worst relative disagreement between apparent size and range."""
    range1 = float(np.linalg.norm(xyz))
    range2 = float(np.linalg.norm(rig.r @ xyz + rig.t_m))
    if range1 <= GOLF_BALL_RADIUS_M or range2 <= GOLF_BALL_RADIUS_M:
        return float("inf")
    expected1 = apparent_radius_px(rig.k1[0, 0], range1)
    expected2 = apparent_radius_px(rig.k2[0, 0], range2)
    return max(abs(radius1_px / expected1 - 1.0),
               abs(radius2_px / expected2 - 1.0))


def _in_measurement_volume(xyz):
    depth = float(xyz[2])
    if not MIN_DEPTH_M <= depth <= MAX_DEPTH_M:
        return False
    if abs(float(xyz[0])) > MAX_LATERAL_FRACTION * depth:
        return False
    return MIN_BALL_HEIGHT_M <= float(xyz[1]) <= MAX_BALL_HEIGHT_M


def find_ball_pair(rig, frame1, frame2):
    """Return (BallPair, None), or (None, reason) saying why not.

    The reason is written for whoever is standing at the device holding a
    ball, because that is who has to act on it. "no ball" and "23 circles,
    none of them ball-shaped at a plausible distance" call for opposite
    responses, and the old message could not tell them apart.
    """
    candidates1 = frame_analysis.ball_candidates(frame1)
    candidates2 = frame_analysis.ball_candidates(frame2)
    if not candidates1 or not candidates2:
        empty = " and ".join(
            name for name, found in (("cam1", candidates1), ("cam2", candidates2))
            if not found)
        return None, "no circle at all in {} ({} / {} candidates)".format(
            empty, len(candidates1), len(candidates2))

    survivors = []
    rejected_on_size = 0
    solved_behind = 0
    solved_at_all = 0
    for u1, v1, r1 in candidates1:
        for u2, v2, r2 in candidates2:
            try:
                xyz = triangulate.triangulate_point(rig, (u1, v1), (u2, v2))
            except triangulate.TriangulationError:
                # Parallel rays: the same pixel in both images, which is what
                # a distant background object looks like. Not an error here,
                # just a pairing that is not the ball.
                continue
            solved_at_all += 1
            if xyz[2] <= 0.0:
                # Counted separately from the rest of the volume test
                # because a swap rejects every shot in a session and is
                # fixable in ten seconds - but only as a FRACTION. Roughly
                # half of all random pairings solve behind the cameras
                # anyway, since it only takes camera 2's circle to sit left
                # of camera 1's, so a raw count means nothing. On the real
                # 2026-08-10 frames it was 1391 of 2450 in a scene with no
                # swap at all.
                solved_behind += 1
                continue
            if not _in_measurement_volume(xyz):
                continue
            e1, e2 = triangulate.reprojection_error(
                rig, xyz, (u1, v1), (u2, v2))
            worst = max(e1, e2)
            if worst > MAX_REPROJECTION_PX:
                continue
            error = _radius_error(rig, xyz, r1, r2)
            if abs(r1 / r2 - 1.0) > MAX_RADIUS_RATIO_ERROR:
                rejected_on_size += 1
                continue
            if error > MAX_RADIUS_ERROR:
                # Counted rather than dropped silently: an operator whose
                # every candidate fails on size has a ball-sized problem
                # (wrong ball, wrong distance) and should hear about it.
                rejected_on_size += 1
                continue
            survivors.append((worst + RADIUS_ERROR_WEIGHT_PX * error, xyz,
                              (u1, v1), (u2, v2), r1, r2, worst, error))

    if not survivors:
        detail = ""
        if rejected_on_size:
            detail += ("; {} pair(s) were the right distance but the wrong "
                       "size for it".format(rejected_on_size))
        if solved_at_all and solved_behind >= MOSTLY_BEHIND_FRACTION * solved_at_all:
            detail += ("; {} of {} pairs solved BEHIND the cameras, which is "
                       "what a left/right image swap looks like - check which "
                       "device is cam1".format(solved_behind, solved_at_all))
        return None, ("no ball-consistent pair among {} x {} circles{}".format(
            len(candidates1), len(candidates2), detail))

    survivors.sort(key=lambda s: s[0])
    best = survivors[0]

    # Only refuse when a rival is BOTH somewhere else and about as well
    # evidenced. Several Hough circles on one ball are neither.
    for rival in survivors[1:]:
        far = float(np.linalg.norm(rival[1] - best[1]))
        if far > AMBIGUITY_SEPARATION_M:
            return None, (
                "ambiguous: two ball-shaped objects {:.0f} mm apart, at "
                "Z {:.0f} mm and Z {:.0f} mm. The protocol asks for one ball "
                "in frame".format(far * 1000.0, best[1][2] * 1000.0,
                                  rival[1][2] * 1000.0))

    _, xyz, uv1, uv2, r1, r2, worst, error = best
    return BallPair(xyz_m=xyz, uv1=uv1, uv2=uv2, radius1_px=r1,
                    radius2_px=r2, reprojection_px=worst,
                    radius_error=error), None
