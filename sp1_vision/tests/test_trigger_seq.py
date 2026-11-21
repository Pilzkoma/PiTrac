"""trigger_seq: the SEQ schedule strings for firmware v0.4."""

import unittest

from sp1_vision import trigger_seq as tq


class SeqCommand(unittest.TestCase):
    def test_events_are_sorted_by_time(self):
        self.assertEqual(tq.seq_command([(1000, "E2"), (0, "E1")]), "SEQ,0:E1,1000:E2")

    def test_an_empty_schedule_is_refused(self):
        with self.assertRaises(ValueError):
            tq.seq_command([])

    def test_an_unknown_event_is_refused(self):
        with self.assertRaises(ValueError):
            tq.seq_command([(0, "E3")])


class OffsetSchedule(unittest.TestCase):
    def test_default_is_cam2_one_ms_late_each_with_its_own_flash(self):
        self.assertEqual(tq.seq_command(tq.offset_schedule()),
                         "SEQ,0:E1,900:F100,1000:E2,1900:F100")

    def test_no_pulse_means_no_flash(self):
        self.assertEqual(tq.seq_command(tq.offset_schedule(pulse_us=0)),
                         "SEQ,0:E1,1000:E2")

    def test_flash_after_cam2_edge_keeps_time_order(self):
        # delay longer than the offset: cam1's flash comes after cam2's edge
        self.assertEqual(tq.seq_command(tq.offset_schedule(500, 900, 50)),
                         "SEQ,0:E1,500:E2,900:F50,1400:F50")


class SweepSchedule(unittest.TestCase):
    def test_both_edges_and_one_flash(self):
        self.assertEqual(tq.seq_command(tq.sweep_schedule(1000, 1500, 50)),
                         "SEQ,0:E1,1000:E2,1500:F50")

    def test_dark_shot_has_edges_only(self):
        self.assertEqual(tq.seq_command(tq.sweep_schedule(1000, 1500, 0)),
                         "SEQ,0:E1,1000:E2")


if __name__ == "__main__":
    unittest.main()
