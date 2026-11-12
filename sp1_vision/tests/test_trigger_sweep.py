"""trigger_sweep analysis: frames to shots, the held-back frame, the window."""

import unittest

import numpy as np

from sp1_vision import trigger_sweep as ts


class AssignFrames(unittest.TestCase):
    def test_each_frame_goes_to_the_last_shot_before_it(self):
        shots = [0.0, 0.1, 0.2]
        frames = [0.03, 0.12, 0.25]
        self.assertEqual(ts.assign_frames(shots, frames, spacing_s=0.1), [0, 1, 2])

    def test_a_shot_without_a_frame_gets_none(self):
        self.assertEqual(ts.assign_frames([0.0, 0.1, 0.2], [0.03, 0.24], 0.1),
                         [0, None, 1])

    def test_frames_before_the_first_shot_are_ignored(self):
        self.assertEqual(ts.assign_frames([1.0, 1.1], [0.5, 0.9, 1.02, 1.15], 0.1),
                         [2, 3])

    def test_a_second_frame_in_one_slot_keeps_the_first(self):
        self.assertEqual(ts.assign_frames([0.0, 0.1], [0.02, 0.05, 0.13], 0.1),
                         [0, 2])


class HeldBackShift(unittest.TestCase):
    def test_no_shift_when_flash_slots_are_bright(self):
        flash = [True, False] * 20
        lit = [50.0 if f else 1.0 for f in flash]
        self.assertEqual(ts.held_back_shift(flash, lit), 0)

    def test_one_shot_late_is_detected(self):
        flash = [True, False] * 20
        lit = [1.0] + [50.0 if f else 1.0 for f in flash[:-1]]   # everything one late
        self.assertEqual(ts.held_back_shift(flash, lit), 1)

    def test_missing_frames_are_skipped(self):
        flash = [True, False] * 20
        lit = [50.0 if f else 1.0 for f in flash]
        lit[4] = None
        self.assertEqual(ts.held_back_shift(flash, lit), 0)

    def test_apply_shift_moves_frames_back_one_shot(self):
        self.assertEqual(ts.apply_shift([None, 1, 2, 3], 1), [1, 2, 3, None])
        self.assertEqual(ts.apply_shift([0, 1], 0), [0, 1])


class ExposureWindow(unittest.TestCase):
    # Values model the paired mean-brightening metric as measured 2026-11-12:
    # flash-free pairs -0.3 .. +0.6, flashes +2.7 and up.
    def window(self, start, end, jitter=0.0, step=250, repeats=5, seed=1):
        rng = np.random.default_rng(seed)
        delays, lit = [], []
        for d in range(0, 20000, step):
            for _ in range(repeats):
                s = start + rng.uniform(-jitter, jitter)
                delays.append(d)
                lit.append(4.0 if s <= d < s + (end - start) else rng.uniform(-0.3, 0.6))
        return ts.exposure_window(delays, lit)

    def test_a_sharp_window_is_found_to_the_step(self):
        w = self.window(6000, 7000)
        self.assertAlmostEqual(w["start_us"], 6000, delta=250)
        self.assertAlmostEqual(w["end_us"], 7000, delta=250)
        self.assertAlmostEqual(w["width_us"], 1000, delta=500)
        self.assertLessEqual(w["start_spread_us"], 250)

    def test_jitter_shows_as_a_wide_edge(self):
        w = self.window(6000, 7000, jitter=600)
        self.assertGreaterEqual(w["start_spread_us"], 500)

    def test_a_fine_sweep_mostly_inside_the_window_with_outliers(self):
        # 2026-11-12 fine sweep: 0.6-2.2 ms, window ~0.8-2.0 ms, a few frames
        # at +108 against a typical +17 - the 99th-percentile threshold then
        # lost the whole window.
        rng = np.random.default_rng(5)
        delays, lit = [], []
        for d in range(600, 2201, 25):
            for r in range(5):
                inside = 800 <= d < 2000
                v = (3.4 + abs(rng.normal(0, 0.3))) if inside else rng.normal(0, 0.2)
                if inside and r == 0:
                    v = 7.0 if d % 100 else 22.0      # the brighter groups seen
                if inside and d < 900 and r == 1:
                    v = 108.0
                delays.append(d)
                lit.append(v)
        w = ts.exposure_window(delays, lit)
        self.assertEqual(w["start_us"], 800)
        self.assertEqual(w["end_us"], 2000)

    def test_no_flash_seen_gives_none(self):
        w = ts.exposure_window([0, 250, 500] * 3, [0.1, -0.2, 0.4] * 3)
        self.assertIsNone(w)


class PairedDifference(unittest.TestCase):
    def test_ambient_flicker_cancels_against_the_following_dark_shot(self):
        # Shots come in flash / dark pairs at one delay. Ambient flicker that
        # brightens both shots of a pair (seen 2026-11-12: dark shots as bright
        # as flash shots at random delays) must not count as a flash.
        rng = np.random.default_rng(3)
        shots, lit = [], []
        for d in list(range(0, 20000, 250)) * 5:
            amb = rng.choice([2.0, 12.0])            # flicker, shared by the pair
            seen = 1000 <= d < 2000
            shots += [{"delay_us": d, "flash": True, "warmup": False},
                      {"delay_us": d, "flash": False, "warmup": False}]
            lit += [amb + (18.0 if seen else 0.0), amb]
        delays, vals = ts.paired_flash_minus_dark(shots, lit)
        w = ts.exposure_window(delays, vals)
        self.assertEqual(w["start_us"], 1000)
        self.assertEqual(w["end_us"], 2000)
        self.assertEqual(w["start_spread_us"], 0)
        self.assertEqual(w["end_spread_us"], 0)

    def test_pairs_with_a_missing_frame_are_skipped(self):
        shots = [{"delay_us": 0, "flash": True, "warmup": False},
                 {"delay_us": 0, "flash": False, "warmup": False},
                 {"delay_us": 250, "flash": True, "warmup": False},
                 {"delay_us": 250, "flash": False, "warmup": False}]
        self.assertEqual(ts.paired_flash_minus_dark(shots, [5.0, 1.0, None, 1.0]),
                         ([0], [4.0]))


if __name__ == "__main__":
    unittest.main()
