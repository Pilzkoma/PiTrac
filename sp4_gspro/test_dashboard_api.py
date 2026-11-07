#!/usr/bin/env python3
"""Tests for the dashboard's HTTP API against a throwaway database.

Needs Flask (and, through calibration_page, OpenCV), so it runs on the
Jetson. Run from sp4_gspro/:
    python3 -m unittest test_dashboard_api

The power-off is never real here: system_control.power_off is replaced for
every test that reaches it.
"""

import os
import tempfile
import unittest
from unittest import mock

import dashboard
import system_control
from shot_db import ShotDB


def ball(speed, vla=18.0, hla=0.0, spin=6000.0, carry=None):
    return {"Speed": speed, "VLA": vla, "HLA": hla, "TotalSpin": spin, "SpinAxis": 0.0,
            "CarryDistance": carry}


class DashboardApiTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(self.path)
        self.db = ShotDB(self.path)
        dashboard.db = self.db
        dashboard._shot_views.clear()
        self.client = dashboard.app.test_client()

        self.max = self.db.add_player("Max")
        self.kathi = self.db.add_player("Kathi")
        course = self.db.list_courses()[0]["id"]
        s1 = self.db.start_session(self.max, course, "OpenShotGolf", "127.0.0.1", 921)
        self.db.log_shot(s1, 1, "7I", ball(120, carry=150))
        self.db.log_shot(s1, 2, "7I", ball(122, carry=155))
        self.db.log_shot(s1, 3, "DR", ball(150, vla=12, spin=2500, carry=230))
        self.db.log_shot(s1, 4, "7I", ball(121, carry=152), response_code=501)   # rejected
        self.s2 = self.db.start_session(self.kathi, course, "OpenShotGolf", "127.0.0.1", 921)
        self.db.log_shot(self.s2, 1, "PW", ball(90, vla=28, spin=8500, carry=100))
        self.empty = self.db.start_session(self.kathi, course, "OpenShotGolf", "127.0.0.1", 921)
        self.s1 = s1

    def tearDown(self):
        self.db.close()
        os.remove(self.path)

    def test_default_is_newest_session_with_shots(self):
        d = self.client.get("/api/stats").get_json()
        # The empty session is newer but has nothing to show.
        self.assertEqual(d["player_id"], self.kathi)
        self.assertEqual(d["period"], "session")
        self.assertEqual(d["session_id"], self.s2)
        self.assertEqual([s["id"] for s in d["sessions"]], [self.s2])
        self.assertEqual(len(d["shots"]), 1)

    def test_player_session_and_rejected_shots(self):
        d = self.client.get("/api/stats?player_id={}".format(self.max)).get_json()
        self.assertEqual(d["session_id"], self.s1)
        self.assertEqual([s["shot_number"] for s in d["shots"]], [3, 2, 1])   # 4 was rejected
        self.assertEqual([c["club"] for c in d["clubs_in_period"]], ["DR", "7I"])
        seven = [a for a in d["averages"] if a["club"] == "7I"][0]
        self.assertEqual(seven["n"], 2)
        self.assertAlmostEqual(seven["carry_m"], 152.5 * 0.9144)

    def test_hidden_club_keeps_its_chip(self):
        d = self.client.get("/api/stats?player_id={}&hidden=DR".format(self.max)).get_json()
        self.assertEqual({s["club"] for s in d["shots"]}, {"7I"})
        self.assertEqual([c["club"] for c in d["clubs_in_period"]], ["DR", "7I"])

    def test_all_players_all_shots(self):
        d = self.client.get("/api/stats?player_id=0&period=all").get_json()
        self.assertEqual(len(d["shots"]), 4)

    def test_unknown_session_falls_back(self):
        d = self.client.get("/api/stats?player_id={}&session_id=9999".format(self.max)).get_json()
        self.assertEqual(d["session_id"], self.s1)

    def test_pages_render(self):
        for url in ("/", "/calibration"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            body = r.get_data(as_text=True)
            self.assertIn("Herunterfahren", body)
            self.assertIn("/api/system/shutdown", body)
            # The button asks first; the request is only sent from the dialog.
            self.assertIn("Herunterfahren?", body)
            self.assertIn('id="lm-off-cancel"', body)

    def test_player_filtered_exports(self):
        # These queries had a broken "s.(response_code ...)" clause before.
        for url in ("/api/export/all_shots", "/api/export/club_averages"):
            r = self.client.get(url + "?player_id={}".format(self.max))
            self.assertEqual(r.status_code, 200, url)
            self.assertIn("text/csv", r.content_type)

    def test_status(self):
        with mock.patch.object(system_control, "can_power_off", return_value=True):
            d = self.client.get("/api/system/status").get_json()
        self.assertEqual(d["device"], "JetsonLM")
        self.assertTrue(d["can_power_off"])

    def test_shutdown_needs_header(self):
        with mock.patch.object(system_control, "power_off") as off:
            r = self.client.post("/api/system/shutdown")
        self.assertEqual(r.status_code, 403)
        off.assert_not_called()

    def test_shutdown_get_not_allowed(self):
        with mock.patch.object(system_control, "power_off") as off:
            r = self.client.get("/api/system/shutdown", headers={"X-JetsonLM": "1"})
        self.assertEqual(r.status_code, 405)
        off.assert_not_called()

    def test_shutdown(self):
        with mock.patch.object(system_control, "power_off", return_value=(True, None)) as off:
            r = self.client.post("/api/system/shutdown", headers={"X-JetsonLM": "1"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        off.assert_called_once_with()

    def test_shutdown_without_permission(self):
        with mock.patch.object(system_control, "power_off", return_value=(False, "keine Berechtigung")):
            r = self.client.post("/api/system/shutdown", headers={"X-JetsonLM": "1"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.get_json()["error"], "keine Berechtigung")


class PowerOffTest(unittest.TestCase):
    def test_refuses_without_sudo_rule(self):
        with mock.patch.object(system_control, "can_power_off", return_value=False), \
             mock.patch.object(system_control.subprocess, "Popen") as popen:
            ok, err = system_control.power_off()
        self.assertFalse(ok)
        self.assertIn("install_system_permissions.sh", err)
        popen.assert_not_called()

    def test_starts_detached_delayed_poweroff(self):
        with mock.patch.object(system_control, "can_power_off", return_value=True), \
             mock.patch.object(system_control.subprocess, "Popen") as popen:
            ok, err = system_control.power_off()
        self.assertTrue(ok)
        args, kwargs = popen.call_args
        self.assertEqual(args[0][:2], ["sh", "-c"])
        self.assertIn("sleep 1; sudo -n /usr/bin/systemctl poweroff", args[0][2])
        self.assertTrue(kwargs["start_new_session"])


if __name__ == "__main__":
    unittest.main()
