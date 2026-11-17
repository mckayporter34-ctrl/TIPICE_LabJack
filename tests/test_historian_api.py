"""Exercise the Pi's real routes without lab hardware or a database."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


@unittest.skipUnless(importlib.util.find_spec("flask"), "requires Flask from requirements.txt")
class HistorianAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "historian_api_test", Path(__file__).resolve().parents[1] / "Historian/Historian.py")
        cls.service = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"labjack": SimpleNamespace(ljm=Mock())}):
            spec.loader.exec_module(cls.service)

    def setUp(self):
        self.service.active_sessions.clear()
        self.writer = Mock()
        self.patch = patch.object(self.service, "write_api", self.writer)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.roster = patch.object(self.service, "is_valid_student", return_value=True)
        self.roster.start()
        self.addCleanup(self.roster.stop)
        self.client = self.service.app.test_client()

    def checkout(self, student="group1", force=False):
        return self.client.post("/checkout", json={
            "student_id": student, "unit_op": "STHX2", "force": force})

    def sample(self, **changes):
        data = {"student_id": "group1", "unit_op": "STHX2", "run_id": "run_a",
                "timestamp_ns": 1794938400000000000,
                "fields": {"water_inlet_temp": 23, "flowrate": 1.5}}
        data.update(changes)
        return self.client.post("/api/process-data", json=data)

    def test_owner_writes_numeric_fields_with_capture_time_and_tags(self):
        self.assertEqual(self.checkout().status_code, 200)
        seen = self.service.active_sessions["STHX2"]["last_seen"]
        self.assertEqual(self.sample().status_code, 200)
        point = self.writer.write.call_args.kwargs["record"]
        line = point.to_line_protocol()
        self.assertIn("run_id=run_a", line)
        self.assertIn("unit_op=STHX2", line)
        self.assertIn("water_inlet_temp=23", line)
        self.assertTrue(line.endswith("1794938400000000000"))
        self.assertEqual(self.service.active_sessions["STHX2"]["last_seen"], seen)

    def test_override_rejects_old_upload_and_old_release_preserves_new_owner(self):
        self.checkout()
        self.assertEqual(self.checkout("group2").status_code, 409)
        self.assertEqual(self.checkout("group2", True).status_code, 200)
        self.assertEqual(self.sample().status_code, 403)
        self.client.post("/release", json={"unit_op": "STHX2", "student_id": "group1"})
        response = self.client.post("/status", json={"unit_op": "STHX2", "student_id": "group2"})
        self.assertEqual(response.json["current_user"], "group2")
        self.writer.write.assert_not_called()

    def test_expired_and_missing_sessions_cannot_upload(self):
        self.assertEqual(self.sample().status_code, 403)
        self.checkout()
        self.service.active_sessions["STHX2"]["last_seen"] -= 16
        self.assertEqual(self.sample().status_code, 403)
        self.writer.write.assert_not_called()

    def test_malformed_payloads_and_nonfinite_fields_never_write(self):
        self.checkout()
        for fields in ({}, {"t": "23"}, {"t": True}, {"t": float("nan")},
                       {"t": float("inf")}, {"t": 10 ** 400}):
            with self.subTest(fields=str(fields)[:60]):
                self.assertEqual(self.sample(fields=fields).status_code, 400)
        self.assertEqual(self.sample(timestamp_ns=True).status_code, 400)
        for route in ("/checkout", "/release", "/status", "/api/process-data"):
            self.assertEqual(self.client.post(route, json=[]).status_code, 400)
        self.writer.write.assert_not_called()

    def test_database_failure_is_not_acknowledged_as_uploaded(self):
        self.checkout()
        self.writer.write.side_effect = OSError("offline")
        self.assertEqual(self.sample().status_code, 503)

    def test_clock_endpoint_returns_nanoseconds(self):
        with patch.object(self.service.time, "time_ns", return_value=123456):
            self.assertEqual(self.client.get("/api/time").json["server_time_ns"], 123456)

    def test_invalid_roster_login_cannot_take_over(self):
        with patch.object(self.service, "is_valid_student", return_value=False):
            self.assertEqual(self.checkout(force=True).status_code, 403)
        self.assertFalse(self.service.active_sessions)


if __name__ == "__main__":
    unittest.main()
