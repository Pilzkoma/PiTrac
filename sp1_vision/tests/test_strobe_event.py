"""find_impacts: when a rest ball left, found without rescanning the recording.

The presence measure is replaced by a stand-in so the tests need no JPEGs:
each frame "buffer" is a dict {(u, v): brightness} and presence() reads the
entry for the ball position asked about.
"""

import types
import unittest
from unittest import mock

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


if __name__ == "__main__":
    unittest.main()
