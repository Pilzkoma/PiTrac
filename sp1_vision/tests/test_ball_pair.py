"""Which of the circles in the two images is the golf ball.

Every test here renders the ball where and how large it would really appear
- the apparent radius comes from that camera's own range to the ball centre,
not from a constant - so the size check the selector depends on is exercised
for real rather than asserted into place.

The failure this module exists for is on record. On 2026-08-10 a 24-shot run
returned a loudspeaker in 17 frames: it was the stronger circle, the detector
returned the strongest, and nothing in a single image could have said
otherwise. One shot even passed the 2 px reprojection gate - both cameras had
locked onto the same loudspeaker, so the two rays met beautifully at 1295 mm.
A small residual means the cameras agree, not that they are looking at a ball.
"""

import unittest
from unittest import mock

import cv2
import numpy as np

from sp1_vision import ball_pair, stereo_geometry
from sp1_vision.tests.test_triangulate import make_rig, project

BALL_R = 0.021335


def _blank():
    return np.zeros((800, 1280), dtype=np.uint8)


# cv2.circle takes fixed-point coordinates when given a shift, so 4 bits of
# fraction puts the disc within 1/16 px of where it belongs.
_SUBPIXEL_BITS = 4
_SUBPIXEL = 1 << _SUBPIXEL_BITS


def _draw(frame, u, v, r):
    """Draw the disc at its true SUB-PIXEL centre, with a soft edge.

    Rounding the centre to whole pixels sounds harmless and is not. The
    truth these tests compare against is fractional, so integer drawing puts
    up to half a pixel of error into each camera independently - which at
    400 mm is 2.3 mm of depth before the detector has done anything at all.
    Measured over ten depths it left an rms of 3.0 mm and, worse, a +1.45 mm
    MEAN: a systematic offset is indistinguishable from a scale error, which
    is the one thing these fixtures must not fake. Sub-pixel drawing takes
    that to 1.8 mm rms and -0.4 mm mean.

    What remains is the detector's own accumulator quantisation, and it is
    the floor for every numeric tolerance in this file.
    """
    cv2.circle(frame,
               (int(round(u * _SUBPIXEL)), int(round(v * _SUBPIXEL))),
               int(round(r * _SUBPIXEL)), 255, -1, cv2.LINE_AA,
               _SUBPIXEL_BITS)
    return frame


def frame_with_disc(u, v, r):
    """A single blurred disc on a dark frame - the whole rendering path."""
    return _blur(_draw(_blank(), u, v, r))


def _blur(frame):
    return cv2.GaussianBlur(frame, (5, 5), 0)


def _apparent_radius_px(f, range_m):
    """Silhouette radius of a sphere: f * tan(asin(R / d))."""
    return f * BALL_R / np.sqrt(range_m ** 2 - BALL_R ** 2)


def ball_discs(rig, xyz):
    """Where and how big the ball appears in each camera, truthfully.

    The two radii differ - camera 2 is 78.7 mm further away along X and sees
    the ball at its own range - which is exactly the asymmetry the selector
    must tolerate while still rejecting an object of the wrong size.
    """
    xyz = np.asarray(xyz, dtype=float)
    uv1, uv2 = project(rig, xyz)
    d1 = float(np.linalg.norm(xyz))
    d2 = float(np.linalg.norm(rig.r @ xyz + rig.t_m))
    return ((uv1[0], uv1[1], _apparent_radius_px(float(rig.k1[0, 0]), d1)),
            (uv2[0], uv2[1], _apparent_radius_px(float(rig.k2[0, 0]), d2)))


def frames_with(rig, balls=(), extra1=(), extra2=()):
    """A stereo pair containing the given balls plus per-camera extras."""
    f1, f2 = _blank(), _blank()
    for xyz in balls:
        d1, d2 = ball_discs(rig, xyz)
        _draw(f1, *d1)
        _draw(f2, *d2)
    for disc in extra1:
        _draw(f1, *disc)
    for disc in extra2:
        _draw(f2, *disc)
    return _blur(f1), _blur(f2)


class FindBallPairTest(unittest.TestCase):
    def setUp(self):
        # The real mount's pitch, so nothing here accidentally depends on a
        # perfectly rectified rig.
        self.rig = make_rig(pitch_deg=-0.94)

    def test_finds_a_lone_ball_where_it_really_is(self):
        truth = np.array([0.03, 0.0937, 0.500])
        f1, f2 = frames_with(self.rig, balls=[truth])
        pair, reason = ball_pair.find_ball_pair(self.rig, f1, f2)
        self.assertIsNotNone(pair, reason)
        np.testing.assert_allclose(pair.xyz_m, truth, atol=0.004)

    def test_the_radius_window_covers_the_whole_declared_volume(self):
        # The bug this exists for: the volume said 0.25 m and the detector's
        # radius window stopped at 70 px, which is a ball at 0.276 m. Any
        # ball nearer than that was invisible to a tool that claimed to be
        # looking for it, and the two numbers lived in different modules
        # with nothing comparing them.
        low, high = ball_pair.radius_bounds_px(self.rig)
        for depth, focal in ((ball_pair.MIN_DEPTH_M, self.rig.k1[0, 0]),
                             (ball_pair.MAX_DEPTH_M, self.rig.k2[0, 0])):
            radius = ball_pair.apparent_radius_px(focal, depth)
            self.assertGreater(radius, low,
                               "a ball at {} m is smaller than the window".format(depth))
            self.assertLess(radius, high,
                            "a ball at {} m is larger than the window".format(depth))

    def test_finds_a_ball_at_the_near_edge_of_the_volume(self):
        # 0.26 m shows a 74 px radius - beyond the old 70 px bound, and the
        # first position of a real run landed there.
        truth = np.array([0.0, 0.0937, 0.260])
        f1, f2 = frames_with(self.rig, balls=[truth])
        pair, reason = ball_pair.find_ball_pair(self.rig, f1, f2)
        self.assertIsNotNone(pair, reason)
        self.assertAlmostEqual(pair.xyz_m[2], 0.260, delta=0.006)

    def test_finds_the_ball_at_both_ends_of_the_working_range(self):
        for depth in (0.350, 0.700):
            truth = np.array([0.0, 0.0937, depth])
            f1, f2 = frames_with(self.rig, balls=[truth])
            pair, reason = ball_pair.find_ball_pair(self.rig, f1, f2)
            self.assertIsNotNone(pair, "{} m: {}".format(depth, reason))
            self.assertAlmostEqual(pair.xyz_m[2], depth, delta=0.006)

    def test_a_stronger_background_object_does_not_win(self):
        # The loudspeaker, reproduced: a big bright disc at the SAME pixel in
        # both images. Equal pixels mean near-zero disparity, which is what
        # being far away looks like - it triangulates way outside the
        # measurement volume. It is also the stronger circle, so the old
        # strongest-wins detector returned exactly this.
        truth = np.array([0.03, 0.0937, 0.500])
        speaker = (880.0, 180.0, 66.0)
        f1, f2 = frames_with(self.rig, balls=[truth],
                             extra1=[speaker], extra2=[speaker])
        pair, reason = ball_pair.find_ball_pair(self.rig, f1, f2)
        self.assertIsNotNone(pair, reason)
        np.testing.assert_allclose(pair.xyz_m, truth, atol=0.004)

    def test_an_object_the_wrong_size_for_its_distance_is_refused(self):
        # A disc pair whose disparity puts it squarely inside the working
        # volume, but far too large to be a 42.67 mm ball at that range: a
        # ball at 850 mm shows a 22 px radius, and this is 62. Depth alone
        # cannot reject it; only the size can.
        truth = np.array([0.0, 0.09, 0.850])
        (u1, v1, _), (u2, v2, _) = ball_discs(self.rig, truth)
        f1 = _blur(_draw(_blank(), u1, v1, 62))
        f2 = _blur(_draw(_blank(), u2, v2, 62))
        pair, reason = ball_pair.find_ball_pair(self.rig, f1, f2)
        self.assertIsNone(pair)
        self.assertIn("size", reason.lower())

    def test_a_quarter_too_large_is_already_refused(self):
        # Not a factor of two - a quarter. Two background objects in the
        # 2026-08-10 run passed the volume and residual gates and sat at
        # +22% and +28%, so the size gate has to bite well before the
        # obvious cases. A correctly located ball measured +4 to +7%.
        truth = np.array([0.0, 0.09, 0.500])
        (u1, v1, r1), (u2, v2, r2) = ball_discs(self.rig, truth)
        f1 = _blur(_draw(_blank(), u1, v1, r1 * 1.25))
        f2 = _blur(_draw(_blank(), u2, v2, r2 * 1.25))
        pair, reason = ball_pair.find_ball_pair(self.rig, f1, f2)
        self.assertIsNone(pair)
        self.assertIn("size", reason.lower())

    def test_a_ball_measured_a_few_percent_large_is_still_a_ball(self):
        # The counter-case, so the gate above cannot be tightened into
        # uselessness: a real detection carries a few percent of positive
        # bias from the soft silhouette edge and must survive.
        truth = np.array([0.0, 0.09, 0.500])
        (u1, v1, r1), (u2, v2, r2) = ball_discs(self.rig, truth)
        f1 = _blur(_draw(_blank(), u1, v1, r1 * 1.07))
        f2 = _blur(_draw(_blank(), u2, v2, r2 * 1.07))
        pair, reason = ball_pair.find_ball_pair(self.rig, f1, f2)
        self.assertIsNotNone(pair, reason)

    def test_an_object_above_the_optical_axis_is_not_a_resting_ball(self):
        # The ball rests on the same surface the unit stands on, so its centre
        # is always BELOW the optical axis - Y positive, since Y is down. On
        # the 2026-08-11 frames every spurious survivor sat at Y = -216 to
        # -278 mm: things on the wall and the monitor, a quarter of a metre
        # above the axis. They cleared the volume, the residual and the size
        # gate; only the height says what they are.
        truth = np.array([0.0, -0.220, 0.500])       # 220 mm ABOVE the axis
        f1, f2 = frames_with(self.rig, balls=[truth])
        pair, reason = ball_pair.find_ball_pair(self.rig, f1, f2)
        self.assertIsNone(pair, "accepted a point 220 mm above the axis")

    def test_a_ball_on_the_surface_is_still_accepted(self):
        # The counter-case, so the height band cannot be tightened into
        # uselessness: the real thing sits at +76 to +86 mm across every
        # verified shot, and the band has to hold the whole plausible range
        # of mounting heights rather than the one we happen to have measured.
        for height in (0.045, 0.0937, 0.150):
            truth = np.array([0.0, height, 0.500])
            f1, f2 = frames_with(self.rig, balls=[truth])
            pair, reason = ball_pair.find_ball_pair(self.rig, f1, f2)
            self.assertIsNotNone(pair, "{} m: {}".format(height, reason))

    def test_two_circles_of_very_different_size_are_not_one_ball(self):
        # 78 mm of baseline against half a metre of range: the ball is almost
        # equidistant from both cameras, so its two apparent radii agree to a
        # few percent whatever the range. Checking each radius against its own
        # predicted size does NOT cover this - one may run +18% and the other
        # -18%, both inside their own tolerance while disagreeing by 40%.
        truth = np.array([0.0, 0.0937, 0.500])
        (u1, v1, r1), (u2, v2, r2) = ball_discs(self.rig, truth)
        f1 = _blur(_draw(_blank(), u1, v1, r1 * 1.18))
        f2 = _blur(_draw(_blank(), u2, v2, r2 * 0.83))
        pair, reason = ball_pair.find_ball_pair(self.rig, f1, f2)
        self.assertIsNone(pair)
        self.assertIn("size", reason.lower())

    def test_nothing_consistent_is_a_reason_not_a_guess(self):
        speaker = (880.0, 180.0, 66.0)
        f1, f2 = frames_with(self.rig, extra1=[speaker], extra2=[speaker])
        pair, reason = ball_pair.find_ball_pair(self.rig, f1, f2)
        self.assertIsNone(pair)
        self.assertIsInstance(reason, str)

    def test_the_reason_counts_the_candidates_that_were_on_offer(self):
        # An operator reading "no ball" needs to know whether the detector
        # saw nothing at all or saw plenty and rejected all of it - those
        # call for opposite responses at the device.
        speaker = (880.0, 180.0, 66.0)
        f1, f2 = frames_with(self.rig, extra1=[speaker], extra2=[speaker])
        _, reason = ball_pair.find_ball_pair(self.rig, f1, f2)
        self.assertRegex(reason, r"\d+")

    def test_an_empty_camera_is_named(self):
        truth = np.array([0.0, 0.09, 0.5])
        f1, _ = frames_with(self.rig, balls=[truth])
        pair, reason = ball_pair.find_ball_pair(self.rig, f1, _blank())
        self.assertIsNone(pair)
        self.assertIn("cam2", reason)

    def test_two_equally_good_balls_are_refused_rather_than_picked(self):
        # Two real balls in the volume, far apart. Choosing one silently
        # would put an arbitrary 200 mm into the series, so this reports
        # instead. The protocol says one ball in frame; this is how the
        # analysis notices that it was not.
        f1, f2 = frames_with(self.rig, balls=[np.array([-0.18, 0.0937, 0.45]),
                                              np.array([0.18, 0.0937, 0.62])])
        pair, reason = ball_pair.find_ball_pair(self.rig, f1, f2)
        self.assertIsNone(pair)
        self.assertIn("ambiguous", reason.lower())

    def test_two_hough_circles_on_one_ball_are_not_ambiguous(self):
        # Hough routinely returns several concentric-ish circles for one
        # disc. Those land within millimetres of each other in 3D and must
        # NOT trip the ambiguity guard, or every real shot would fail.
        truth = np.array([0.0, 0.0937, 0.500])
        (u1, v1, r1), (u2, v2, r2) = ball_discs(self.rig, truth)
        f1 = _blank(); _draw(f1, u1, v1, r1); _draw(f1, u1 + 2, v1 - 1, r1 * 0.9)
        f2 = _blank(); _draw(f2, u2, v2, r2); _draw(f2, u2 - 2, v2 + 1, r2 * 0.9)
        pair, reason = ball_pair.find_ball_pair(self.rig, _blur(f1), _blur(f2))
        self.assertIsNotNone(pair, reason)
        np.testing.assert_allclose(pair.xyz_m, truth, atol=0.006)

    def test_the_result_carries_what_the_operator_and_the_analysis_need(self):
        truth = np.array([0.03, 0.0937, 0.500])
        f1, f2 = frames_with(self.rig, balls=[truth])
        pair, _ = ball_pair.find_ball_pair(self.rig, f1, f2)
        self.assertEqual(len(pair.uv1), 2)
        self.assertEqual(len(pair.uv2), 2)
        self.assertLess(pair.reprojection_px, ball_pair.MAX_REPROJECTION_PX)
        self.assertLess(pair.radius_error, ball_pair.MAX_RADIUS_ERROR)
        self.assertGreater(pair.xyz_m[2], 0.0)

    def test_a_ball_behind_the_cameras_is_never_returned(self):
        # Swapped images: on this pitched rig the swap solves to negative
        # depth. The volume bound is stated in positive metres, so this is
        # structural rather than a threshold that could be tuned away.
        truth = np.array([0.03, 0.0937, 0.500])
        f1, f2 = frames_with(self.rig, balls=[truth])
        pair, reason = ball_pair.find_ball_pair(self.rig, f2, f1)
        self.assertIsNone(pair, "swapped pair returned {}".format(
            None if pair is None else pair.xyz_m))

    def test_a_cluttered_scene_is_not_accused_of_being_a_swap(self):
        # Half of all RANDOM pairings solve behind the cameras - it only
        # takes camera 2's circle to sit left of camera 1's. On the real
        # 2026-08-10 frames that was 1391 pairs out of 2450, and reported as
        # a count it read as a wiring fault in a scene that had none. The
        # swap signature is that essentially EVERY pairing solves behind,
        # not that many do.
        f1, f2 = _blank(), _blank()
        for u in (300, 500, 700, 900):
            _draw(f1, u, 400, 30)
        for u in (200, 400, 600, 800):
            _draw(f2, u, 400, 30)
        pair, reason = ball_pair.find_ball_pair(
            self.rig, _blur(f1), _blur(f2))
        self.assertIsNone(pair)
        self.assertNotIn("swap", reason.lower())

    def _truth_refiner(self, *truths):
        """A stand-in refine_ball that returns the exact rendered circle.

        find_ball_pair calls refine_ball once per camera; the stand-in
        answers with whichever camera's true disc lies nearest the seed it
        was handed, which distinguishes the two views by their disparity.
        """
        discs = [d for t in truths for d in ball_discs(self.rig, t)]

        def fake(frame, u, v, r):
            nearest = min(discs, key=lambda d: abs(d[0] - u))
            return (float(nearest[0]), float(nearest[1]), float(nearest[2]))

        return fake

    def test_a_refinement_that_improves_the_pair_is_adopted(self):
        # The precision half of the two-phase wiring: once the selection has
        # decided WHICH circles are the ball, the outline refinement gets to
        # improve WHERE they are - and its answer must actually be the one
        # returned, or the wiring is decoration.
        truth = np.array([0.03, 0.0937, 0.500])
        f1, f2 = frames_with(self.rig, balls=[truth])
        d1, d2 = ball_discs(self.rig, truth)
        with mock.patch.object(ball_pair.frame_analysis, "refine_ball",
                               side_effect=self._truth_refiner(truth)) as spy:
            pair, reason = ball_pair.find_ball_pair(self.rig, f1, f2)
        self.assertIsNotNone(pair, reason)
        self.assertTrue(spy.called)
        np.testing.assert_allclose(pair.uv1, d1[:2], atol=1e-9,
                                   err_msg="the adopted centre is not the "
                                           "refined one")
        np.testing.assert_allclose(pair.uv2, d2[:2], atol=1e-9)
        np.testing.assert_allclose(pair.xyz_m, truth, atol=0.002)

    def test_a_refinement_that_degrades_the_pair_is_ignored(self):
        # The fallback half: a refinement that pulls the two views apart -
        # opposite vertical shifts violate the epipolar constraint - must
        # lose to the raw selection, not replace it. This is the exact
        # failure the 2026-08-11 wiring attempt shipped: refined circles
        # were adopted unconditionally and ruined pairs Hough had right.
        truth = np.array([0.03, 0.0937, 0.500])
        f1, f2 = frames_with(self.rig, balls=[truth])
        # The comparison baseline is the SELECTION's answer, so refinement
        # is switched off entirely for it - the normal path would adopt a
        # genuine (if small) improvement and the baseline would drift.
        with mock.patch.object(ball_pair.frame_analysis, "refine_ball",
                               return_value=None):
            raw_pair, _ = ball_pair.find_ball_pair(self.rig, f1, f2)
        d1, _ = ball_discs(self.rig, truth)

        def sabotage(frame, u, v, r):
            up = abs(u - d1[0]) < 60.0  # cam1's seed sits near cam1's disc
            return (float(u), float(v) + (3.0 if up else -3.0), float(r))

        with mock.patch.object(ball_pair.frame_analysis, "refine_ball",
                               side_effect=sabotage) as spy:
            pair, reason = ball_pair.find_ball_pair(self.rig, f1, f2)
        self.assertIsNotNone(pair, reason)
        self.assertTrue(spy.called,
                        "the precision step never ran, so this test "
                        "exercised nothing")
        np.testing.assert_allclose(pair.uv1, raw_pair.uv1, atol=1e-9,
                                   err_msg="a pair-degrading refinement was "
                                           "adopted")
        np.testing.assert_allclose(pair.uv2, raw_pair.uv2, atol=1e-9)

    def test_ambiguity_is_not_adjudicated_by_the_refinement(self):
        # Constraint pin, green by construction before and after the wiring:
        # when two ball-shaped objects are genuinely in frame, refinement
        # precision must not be the thing that picks one. The refusal to
        # guess is the protocol's, not the detector's, to give up.
        balls = [np.array([-0.18, 0.0937, 0.45]),
                 np.array([0.18, 0.0937, 0.62])]
        f1, f2 = frames_with(self.rig, balls=balls)
        with mock.patch.object(ball_pair.frame_analysis, "refine_ball",
                               side_effect=self._truth_refiner(*balls)) as spy:
            pair, reason = ball_pair.find_ball_pair(self.rig, f1, f2)
        self.assertIsNone(pair)
        self.assertIn("ambiguous", reason.lower())
        self.assertFalse(spy.called,
                         "refinement ran on an ambiguous scene - it must "
                         "neither adjudicate nor waste the time")

    def test_a_swap_is_named_rather_than_lumped_in_with_every_other_miss(self):
        # A swapped pair of cables rejects EVERY shot, and it rejects them
        # for a reason the operator can fix in ten seconds - but only if the
        # message says so. Reported as a plain "no consistent pair" it looks
        # like a lighting problem and reads as twenty-four separate bad
        # shots.
        truth = np.array([0.03, 0.0937, 0.500])
        f1, f2 = frames_with(self.rig, balls=[truth])
        _, reason = ball_pair.find_ball_pair(self.rig, f2, f1)
        self.assertIn("behind", reason.lower())
        self.assertIn("swap", reason.lower())


if __name__ == "__main__":
    unittest.main()
