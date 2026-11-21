"""strobe_shot: the Teensy lines that start a triggered recording."""

import unittest

from sp1_vision import strobe_shot as ss


class TriggerRunCommands(unittest.TestCase):
    def test_without_offset_trig_run_as_before(self):
        self.assertEqual(ss.trigger_run_commands(10.0, 900, 100, 17000, None),
                         ["TRIG_RUN,10000,900,100,17000"])

    def test_with_offset_each_camera_its_own_edge_and_flash(self):
        self.assertEqual(ss.trigger_run_commands(10.0, 900, 100, 17000, 1000),
                         ["SEQ,0:E1,900:F100,1000:E2,1900:F100", "SEQ_RUN,10000,17000"])


class TriggerInfo(unittest.TestCase):
    def test_records_what_part_4_needs_for_frame_times(self):
        info = ss.trigger_info(10.0, 900, 100, 5, 1000)
        self.assertEqual(info, {"period_us": 10000, "delay_us": 900, "pulse_us": 100,
                                "exposure_units": 5, "offset_us": 1000,
                                "cam_edge_us": {"1": 0, "2": 1000},
                                "cam_flash_us": {"1": 900, "2": 1900}})

    def test_no_offset_means_both_cameras_on_one_edge(self):
        info = ss.trigger_info(10.0, 900, 100, 5, None)
        self.assertEqual(info["cam_edge_us"], {"1": 0, "2": 0})
        self.assertEqual(info["cam_flash_us"], {"1": 900, "2": 900})


if __name__ == "__main__":
    unittest.main()
