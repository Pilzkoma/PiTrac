"""find_impacts: when a rest ball left, found without rescanning the recording.

The presence measure is replaced by a stand-in so the tests need no JPEGs:
each frame "buffer" is a dict {(u, v): brightness} and presence() reads the
entry for the ball position asked about.
"""

import types
import unittest
from unittest import mock

import cv2
import numpy as np

from sp1_vision import strobe_event as se

FPS = 120.0


def ball(u, v, r=10.0):
    return types.SimpleNamespace(uv1=(u, v), radius1_px=r)


def frames(duration_s, present):
    """[(t, buf)]; present(t) -> {(u, v): brightness} for that frame."""
    n = int(duration_s * FPS)
    return [(i / FPS, present(i / FPS)) for i in range(n)]


def rest_samples(t_from, t_to, b, step=se.REST_STEP_S):
    out, t = [], t_from
    while t < t_to:
        out.append((t, b))
        t += step
    return out


class Counter:
    def __init__(self):
        self.calls = 0

    def __call__(self, buf, u, v, r):
        self.calls += 1
        return float(buf.get((u, v), 0.0))


class FindImpacts(unittest.TestCase):
    def run_find(self, got1, rest):
        counter = Counter()
        with mock.patch.object(se, "presence", counter):
            impacts = se.find_impacts({1: got1}, rest)
        return impacts, counter.calls

    def test_impact_time_is_when_the_ball_went(self):
        a = ball(100, 100)
        got1 = frames(5.0, lambda t: {(100, 100): 80.0 if t < 2.1 else 0.0})
        impacts, _ = self.run_find(got1, rest_samples(0.5, 2.1, a))
        self.assertEqual(len(impacts), 1)
        t_imp, b = impacts[0]
        self.assertIs(b, a)
        self.assertAlmostEqual(t_imp, 2.1, delta=1.5 / FPS)

    def test_a_ball_that_never_leaves_costs_linear_time(self):
        # A ball lying still for a whole 45 s recording, found at every rest
        # sample: each sample must not rescan to the end (that was 180 x 5400
        # presence decodes and over half an hour on the Jetson, 2026-11-12).
        a = ball(100, 100)
        got1 = frames(45.0, lambda t: {(100, 100): 80.0})
        impacts, calls = self.run_find(got1, rest_samples(0.5, 45.0, a))
        self.assertEqual(impacts, [])
        self.assertLess(calls, 3 * len(got1))

    def test_another_ball_found_in_between_does_not_cut_the_search_short(self):
        # Rest samples alternate between the ball about to be hit (A) and a
        # ball lying elsewhere (B). A's search must run on past B's samples.
        a, b = ball(100, 100), ball(300, 300)
        got1 = frames(5.0, lambda t: {(100, 100): 80.0 if t < 3.0 else 0.0,
                                      (300, 300): 80.0})
        rest = sorted(rest_samples(0.5, 1.0, a) + rest_samples(0.6, 5.0, b, step=0.25),
                      key=lambda s: s[0])
        impacts, _ = self.run_find(got1, rest)
        times = [t for t, bb in impacts if bb is a]
        self.assertEqual(len(times), 1)
        self.assertAlmostEqual(times[0], 3.0, delta=1.5 / FPS)

    def test_two_shots_from_the_same_spot(self):
        a1, a2 = ball(100, 100), ball(100, 100)
        def present(t):
            here = t < 1.5 or 3.0 <= t < 4.0
            return {(100, 100): 80.0 if here else 0.0}
        got1 = frames(6.0, present)
        rest = rest_samples(0.25, 1.5, a1) + rest_samples(3.1, 4.0, a2)
        impacts, _ = self.run_find(got1, rest)
        self.assertEqual([round(t, 2) for t, _ in impacts], [1.5, 4.0])


class PositiveImage(unittest.TestCase):
    """The ball-only difference image must not blow noise up into circles."""

    def setUp(self):
        rng = np.random.default_rng(0)
        self.still = rng.uniform(10, 30, (200, 300)).astype(np.uint8)
        self.ref = se.PositiveReference([(0.0, self.still), (0.01, self.still)])
        self.rng = rng

    def test_a_ball_free_frame_stays_dark(self):
        # Triggered frames, 2026-11-12: with no ball the brightest residue is
        # noise of ~9 grey levels; scaled to 220 it gave 1768 Hough circles.
        noisy = np.clip(self.still.astype(int) + self.rng.integers(-9, 10, self.still.shape),
                        0, 255).astype(np.uint8)
        _, d = self.ref.positive(noisy)
        self.assertLess(int(d.max()), 40)

    def test_a_ball_still_comes_out_bright(self):
        frame = self.still.copy()
        cv2.circle(frame, (150, 100), 30, 120, -1)
        _, d = self.ref.positive(frame)
        self.assertGreater(int(d[100, 150]), 150)


class RestSearchOnDarkFrames(unittest.TestCase):
    """find_rest_balls brightens triggered (dark) frames before the search."""

    def seen_maxima(self, level):
        frame = np.full((80, 80), level, np.uint8)
        frame[30:50, 30:50] = min(255, level + 50)
        got = {1: [(0.5, frame)], 2: [(0.5, frame)]}
        seen = []

        def fake_find(rig, f1, f2):
            seen.append(int(f1.max()))
            return None, "stub"

        with mock.patch.object(se.ball_pair, "find_ball_pair", fake_find), \
             mock.patch.object(se.ss, "REFERENCE_SKIP_S", 0.0):
            se.find_rest_balls(None, got)
        return seen

    def test_a_dark_frame_is_brightened(self):
        # 2026-11-12 triggered chips: rest ball 78 on 24, median ~17; the
        # circle search found it in 0 of 17 moments as is, 16 of 17 at x2.5.
        self.assertEqual(set(self.seen_maxima(17)), {int(67 * se.DARK_FRAME_GAIN)})

    def test_a_normal_frame_is_left_alone(self):
        self.assertEqual(set(self.seen_maxima(100)), {150})


if __name__ == "__main__":
    unittest.main()
