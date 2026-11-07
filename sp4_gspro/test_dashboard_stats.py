#!/usr/bin/env python3
"""Tests for dashboard_stats: the numbers must mean what Golfinator's mean.

Plain Python, no Flask. Run from sp4_gspro/:
    python -m unittest test_dashboard_stats
"""

import math
import statistics
import unittest
from datetime import datetime

import dashboard_stats as ds


def shot(sid, num, club="7I", carry=150.0, side=0.0, t="2026-11-07 12:00:00", **kw):
    """A shot_view-shaped dict, metric already."""
    d = {"id": sid * 100 + num, "session_id": sid, "shot_number": num, "timestamp": t,
         "club": club, "club_name": ds.club_name(club), "color": ds.club_color(club),
         "ball_kmh": 180.0, "vla": 17.0, "hla": 0.0, "spin": 6000.0, "spin_axis": 0.0,
         "carry_m": carry, "side_m": side, "apex_m": 25.0}
    d.update(kw)
    return d


class MomentsTest(unittest.TestCase):
    def test_sample_standard_deviation(self):
        vals = [140.0, 151.0, 148.5, 155.0]
        mean, sd = ds.moments(vals)
        self.assertAlmostEqual(mean, statistics.mean(vals))
        self.assertAlmostEqual(sd, statistics.stdev(vals))   # n - 1, as Golfinator

    def test_no_spread_below_two(self):
        self.assertEqual(ds.moments([150.0]), (150.0, None))
        self.assertEqual(ds.moments([]), (None, None))

    def test_ignores_missing_values(self):
        self.assertEqual(ds.moments([None, 10.0, None, 20.0])[0], 15.0)


class EllipseTest(unittest.TestCase):
    def test_needs_three_points(self):
        self.assertIsNone(ds.covariance_ellipse([(100, 0), (110, 2)]))

    def test_axis_aligned_spread(self):
        # Spread only in length: major axis along length, angle 0.
        pts = [(140, 0), (150, 0), (160, 0)]
        e = ds.covariance_ellipse(pts)
        self.assertAlmostEqual(e["length_m"], 150)
        self.assertAlmostEqual(e["side_m"], 0)
        self.assertAlmostEqual(e["semi_major_m"], ds.ELLIPSE_SCALE_68 * 10.0)
        self.assertAlmostEqual(e["semi_minor_m"], 0.0)
        self.assertAlmostEqual(e["angle_deg"], 0.0)

    def test_diagonal_spread_turns_toward_side(self):
        # Longer shots also further right: the major axis turns +45 deg.
        pts = [(140, -10), (150, 0), (160, 10)]
        e = ds.covariance_ellipse(pts)
        self.assertAlmostEqual(e["angle_deg"], 45.0)
        self.assertAlmostEqual(e["semi_major_m"], ds.ELLIPSE_SCALE_68 * math.sqrt(200.0))

    def test_scale_holds_68_percent(self):
        # sqrt(-2 ln(1 - 0.68))
        self.assertAlmostEqual(ds.ELLIPSE_SCALE_68, math.sqrt(-2 * math.log(0.32)))


class ShotViewTest(unittest.TestCase):
    ROW = {"id": 1, "session_id": 3, "shot_number": 2, "club": "7i",
           "timestamp": "2026-11-07 12:00:00", "ball_speed": 100.0, "vla": 18.0,
           "hla": 3.0, "total_spin": 6500.0, "spin_axis": 0.0, "carry_distance": 200.0}

    def test_metric_units(self):
        v = ds.shot_view(self.ROW)
        self.assertAlmostEqual(v["ball_kmh"], 160.9344)
        self.assertAlmostEqual(v["carry_m"], 182.88)       # the stored carry, in metres

    def test_club_id_normalised(self):
        v = ds.shot_view(self.ROW)
        self.assertEqual(v["club"], "7I")
        self.assertEqual(v["club_name"], "7i")
        self.assertEqual(v["color"], "#A9A7DC")             # Golfinator's lavender

    def test_right_is_positive(self):
        self.assertGreater(ds.shot_view(self.ROW)["side_m"], 0)
        left = dict(self.ROW, hla=-3.0)
        self.assertLess(ds.shot_view(left)["side_m"], 0)

    def test_carry_from_physics_when_not_stored(self):
        v = ds.shot_view(dict(self.ROW, carry_distance=None))
        self.assertIsNotNone(v["carry_m"])
        self.assertGreater(v["carry_m"], 0)

    def test_missing_speed_has_no_flight(self):
        v = ds.shot_view(dict(self.ROW, ball_speed=None, carry_distance=None))
        self.assertIsNone(v["ball_kmh"])
        self.assertIsNone(v["carry_m"])
        self.assertIsNone(v["side_m"])

    def test_missing_club(self):
        v = ds.shot_view(dict(self.ROW, club=None))
        self.assertEqual(v["club"], ds.UNKNOWN_CLUB)
        self.assertEqual(v["club_name"], "Ohne Schläger")


class SelectTest(unittest.TestCase):
    NOW = datetime(2026, 11, 7, 18, 0, 0)
    SHOTS = [shot(1, 1, t="2026-09-01 10:00:00"), shot(1, 2, t="2026-09-01 10:01:00"),
             shot(2, 1, "DR", t="2026-11-06 10:00:00"), shot(2, 2, t="2026-11-06 10:02:00"),
             shot(2, 3, "PW", t=None)]

    def ids(self, picked):
        return [(s["session_id"], s["shot_number"]) for s in picked]

    def test_session_newest_first(self):
        self.assertEqual(self.ids(ds.select(self.SHOTS, "session", 2)), [(2, 3), (2, 2), (2, 1)])

    def test_thirty_days_drops_old_and_undated(self):
        self.assertEqual(self.ids(ds.select(self.SHOTS, "30d", now=self.NOW)), [(2, 2), (2, 1)])

    def test_all(self):
        self.assertEqual(len(ds.select(self.SHOTS, "all")), 5)

    def test_hidden_clubs(self):
        self.assertEqual(self.ids(ds.select(self.SHOTS, "session", 2, hidden_clubs=["7I", "PW"])), [(2, 1)])


class AveragesTest(unittest.TestCase):
    def test_bag_order_unknown_last(self):
        shots = [shot(1, 1, "PW"), shot(1, 2, "ZZ"), shot(1, 3, "DR"), shot(1, 4, ds.UNKNOWN_CLUB),
                 shot(1, 5, "7I")]
        self.assertEqual([a["club"] for a in ds.averages_by_club(shots)],
                         ["DR", "7I", "PW", "?", "ZZ"])

    def test_spreads_and_ellipse_thresholds(self):
        two = [shot(1, 1, carry=140, side=-2), shot(1, 2, carry=150, side=2)]
        a = ds.averages_by_club(two)[0]
        self.assertEqual(a["n"], 2)
        self.assertAlmostEqual(a["carry_m"], 145)
        self.assertAlmostEqual(a["spread_length_m"], statistics.stdev([140, 150]))
        self.assertAlmostEqual(a["spread_side_m"], statistics.stdev([-2, 2]))
        self.assertIsNone(a["ellipse"])                      # needs three
        three = two + [shot(1, 3, carry=160, side=0)]
        self.assertIsNotNone(ds.averages_by_club(three)[0]["ellipse"])

    def test_per_player_rows_sit_together(self):
        shots = [shot(1, 1, "7I", player_id=1, player_name="Max"),
                 shot(2, 1, "7I", player_id=2, player_name="Lasse"),
                 shot(2, 2, "DR", player_id=2, player_name="Lasse")]
        rows = ds.averages_by_club(shots, player_order=[2, 1])
        self.assertEqual([(a["club"], a["player_name"]) for a in rows],
                         [("DR", "Lasse"), ("7I", "Lasse"), ("7I", "Max")])   # no "DR, Max" row

    def test_without_order_one_row_per_club(self):
        shots = [shot(1, 1, "7I", player_id=1, player_name="Max"),
                 shot(2, 1, "7I", player_id=2, player_name="Lasse")]
        rows = ds.averages_by_club(shots)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["n"], 2)
        self.assertIsNone(rows[0]["player_id"])

    def test_single_shot_has_no_spread(self):
        a = ds.averages_by_club([shot(1, 1)])[0]
        self.assertIsNone(a["spread_length_m"])
        self.assertIsNone(a["spread_side_m"])


class SessionTimeTest(unittest.TestCase):
    def test_unsynced_clock_falls_back_to_first_shot(self):
        sess = {"started_at": "2000-01-01 01:00:59", "ended_at": None}
        self.assertEqual(ds.session_label_time(sess, "2026-11-07 15:00:00"),
                         datetime(2026, 11, 7, 15, 0, 0))

    def test_then_end_then_nothing(self):
        sess = {"started_at": "2000-01-01 01:00:59", "ended_at": "2026-11-07 16:50:46"}
        self.assertEqual(ds.session_label_time(sess, None), datetime(2026, 11, 7, 16, 50, 46))
        self.assertIsNone(ds.session_label_time({"started_at": "2000-01-01 01:00:59"}, None))


if __name__ == "__main__":
    unittest.main()
