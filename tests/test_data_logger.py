import csv
import math
from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
from queue import Queue
import tempfile
import threading
import requests
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from core.data_logger import DataLogger


class Scheduler:
    def __init__(self):
        self.callbacks = {}
        self.next_id = 0

    def after(self, delay, callback):
        self.next_id += 1
        self.callbacks[self.next_id] = callback
        return self.next_id

    def after_cancel(self, callback_id):
        self.callbacks.pop(callback_id, None)

    def run(self, callback_id):
        self.callbacks.pop(callback_id)()


class Count:
    def __init__(self):
        self.value = 0
        self.owner = threading.get_ident()

    def set(self, value):
        assert threading.get_ident() == self.owner, "worker accessed UI count"
        self.value = value


class DataLoggerTests(unittest.TestCase):
    def setUp(self):
        # Keep tests independent of the desktop's private transport setting.
        mode = patch("core.data_logger.HISTORIAN_WRITE_MODE", "direct")
        mode.start()
        self.addCleanup(mode.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.scheduler = Scheduler()
        self.count = Count()

    def logger(self, sources, numeric=(), on_error=None):
        logger = DataLogger(sources, self.temp.name, self.count, self.scheduler,
                            numeric, on_error)
        self.addCleanup(logger.stop)
        return logger

    def rows(self, logger):
        with open(logger.filepath, newline="", encoding="utf-8") as file:
            return list(csv.DictReader(file))

    def test_bad_pid_sensor_and_arbitrary_source_preserve_rows_and_recover(self):
        state = {"pid": "0.74", "sensor": "21.5", "broken": False}
        owner = threading.get_ident()

        def read(key):
            self.assertEqual(threading.get_ident(), owner)
            if key == "other" and state["broken"]:
                raise RuntimeError("sensor disconnected")
            return "healthy" if key == "other" else state[key]

        logger = self.logger({key: lambda k=key: read(k)
                              for key in ("pid", "sensor", "other")}, ("pid", "sensor"))
        logger.start()
        for bad in ("x", "", "NaN", "inf", "-inf", "1e999"):
            state.update(pid=bad, sensor=math.nan, broken=True)
            self.scheduler.run(logger._capture_id)
            self.assertTrue(logger.is_logging)
        state.update(pid="1.25", sensor="22.0", broken=False)
        self.scheduler.run(logger._capture_id)
        logger.stop()
        rows = self.rows(logger)
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[0]["pid"], "0.74")
        for row in rows[1:-1]:
            self.assertEqual([row[k] for k in ("pid", "sensor", "other")], ["Error"] * 3)
        self.assertEqual(rows[-1]["pid"], "1.25")
        self.assertEqual(rows[-1]["other"], "healthy")
        self.assertEqual(self.count.value, 8)
        self.assertEqual(logger.source_errors, {})
        self.assertEqual(self.scheduler.callbacks, {})

    def test_tcl_conversion_failure_is_isolated_and_text_columns_survive(self):
        import tkinter as tk
        root = tk.Tcl()
        pid = tk.DoubleVar(root, value=1.0)
        root.globalsetvar(str(pid), "invalid")
        logger = self.logger({"Kc": pid.get, "Temperature": lambda: 25,
                              "GC Stream": lambda: "Feed", "Heater": lambda: "ON"},
                             ("Kc", "Temperature"))
        logger.start()
        self.scheduler.run(logger._capture_id)
        logger.stop()
        self.assertEqual(len(self.rows(logger)), 2)
        self.assertEqual(self.rows(logger)[0]["Kc"], "Error")
        self.assertEqual(self.rows(logger)[0]["GC Stream"], "Feed")
        self.assertEqual(self.rows(logger)[0]["Heater"], "ON")

    def test_restart_uses_unique_files_and_never_duplicates_rows(self):
        logger = self.logger({"Value": lambda: 1}, ("Value",))
        files = []
        with redirect_stdout(StringIO()) as terminal:
            for _ in range(5):
                logger.start()
                logger.start()
                files.append(logger.filepath)
                logger.stop()
                logger.stop()
                self.assertEqual(len(self.rows(logger)), 1)
                self.assertFalse(logger._thread.is_alive())
        self.assertEqual(len(set(files)), 5)
        self.assertEqual(terminal.getvalue().splitlines(), [f"Data saved to {path}" for path in files])

    def test_stop_callback_runs_once_after_the_csv_is_closed(self):
        logger = self.logger({"Value": lambda: 1})
        real_writer = csv.writer
        streams = []
        saved = []

        def record_stream(stream):
            streams.append(stream)
            return real_writer(stream)

        def on_saved(path):
            saved.append((path, streams[0].closed, self.rows(logger)))

        with patch("core.data_logger.csv.writer", side_effect=record_stream):
            logger.start()
        self.scheduler.run(logger._capture_id)
        logger.stop(on_saved=on_saved)
        logger.stop(on_saved=on_saved)

        self.assertEqual(len(saved), 1)
        path, closed, rows = saved[0]
        self.assertEqual(path, logger.filepath)
        self.assertTrue(closed)
        self.assertEqual([row["Value"] for row in rows], ["1", "1"])

    def test_interval_validation(self):
        logger = self.logger({})
        for bad in ("bad", "", math.nan, math.inf, 0, -1):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                logger.set_interval(bad)
        logger.set_interval(0.01)
        self.assertEqual(logger._interval, 0.1)

    def test_runs_started_in_same_second_have_distinct_ids(self):
        logger = self.logger({"Value": lambda: 1})
        logger._run_id_var = SimpleNamespace(get=lambda: "Group1_Run1")
        with patch("core.data_logger.datetime") as clock, patch.object(
                logger, "_make_filepath", side_effect=[
                    f"{self.temp.name}/first.csv", f"{self.temp.name}/second.csv"]):
            clock.now.return_value = datetime(2026, 11, 17, 14, 0, 0)
            logger.start()
            first_id = logger._active_run_id
            logger.stop()
            logger.start()
            second_id = logger._active_run_id
            logger.stop()
        self.assertNotEqual(first_id, second_id)
        self.assertTrue(first_id.startswith("Group1_Run1_20261117_140000_"))
        self.assertTrue(second_id.startswith("Group1_Run1_20261117_140000_"))

    def test_historian_snapshots_keep_run_label_and_skip_invalid_fields(self):
        owner = threading.get_ident()
        state = {"run": " Group_A ", "value": "21.5"}

        def read(key):
            self.assertEqual(threading.get_ident(), owner, "worker accessed a UI source")
            return state[key]

        logger = self.logger({"Temperature": lambda: read("value")}, ("Temperature",))
        logger._influx_sources = {"temperature": lambda: read("value"),
                                 "invalid": lambda: "NaN",
                                 "broken": lambda: 1 / 0}
        logger._unit_op = "STHX1"
        logger._run_id_var = SimpleNamespace(get=lambda: read("run"))
        client = Mock()
        point = Mock()
        point.tag.return_value = point
        with patch.multiple("core.data_logger", INFLUX_AVAILABLE=True, INFLUX_TOKEN="test",
                            InfluxDBClient=Mock(return_value=client), Point=Mock(return_value=point),
                            WritePrecision=SimpleNamespace(NS="ns"), SYNCHRONOUS=object(), create=True), \
                patch("core.data_logger.datetime") as clock:
            clock.now.return_value = datetime(2026, 10, 28, 14, 30, 15)
            logger.start()
            state.update(run="Group_B", value="22")
            self.scheduler.run(logger._capture_id)
            logger.stop()
            logger._influx_thread.join(timeout=1)
        self.assertFalse(logger._influx_thread.is_alive())
        self.assertEqual(len(self.rows(logger)), 2)
        self.assertEqual(client.write_api.return_value.write.call_count, 2)
        self.assertEqual(logger.influx_uploaded, 2)
        self.assertEqual(logger.last_influx_success, "14:30:15")
        self.assertIn("2 uploaded", logger.influx_status)
        self.assertIn("Logging stopped", logger.influx_status)
        self.assertEqual(point.field.call_args_list[0].args, ("temperature", 21.5))
        self.assertEqual(point.field.call_args_list[1].args, ("temperature", 22.0))
        run_tags = [call.args for call in point.tag.call_args_list if call.args[0] == "run_id"]
        self.assertEqual(len(run_tags), 2)
        self.assertEqual(run_tags[0], run_tags[1])
        self.assertRegex(run_tags[0][1], r"^Group_A_20261028_143015_[0-9a-f]{32}$")
        point.tag.assert_any_call("unit_op", "STHX1")
        client.close.assert_called_once()

    def test_disabled_database_explains_reason_and_preserves_csv(self):
        for available, token, reason in (
                (False, "test", "not installed"),
                (True, "", "INFLUX_TOKEN is missing")):
            with self.subTest(reason=reason), patch.multiple(
                    "core.data_logger", INFLUX_AVAILABLE=available, INFLUX_TOKEN=token):
                logger = self.logger({"Value": lambda: 1})
                logger._influx_sources = {"value": lambda: 1}
                logger.start()
                logger.stop()
                self.assertIn(reason, logger.influx_status)
                self.assertIn("CSV only", logger.influx_status)
                self.assertEqual(len(self.rows(logger)), 1)

    def test_upload_failure_and_recovery_retain_failed_count(self):
        logger = self.logger({})
        logger._influx_started = True
        queue = Queue()
        queue.put(({"temperature": 20.0}, 1))
        queue.put(None)
        client = Mock()
        client.write_api.return_value.write.side_effect = OSError("unavailable secret-token")
        point = Mock()
        point.tag.return_value = point
        with patch.multiple("core.data_logger", INFLUX_TOKEN="secret-token",
                            InfluxDBClient=Mock(return_value=client), Point=Mock(return_value=point),
                            WritePrecision=SimpleNamespace(NS="ns"), SYNCHRONOUS=object(), create=True):
            logger._run_influx(queue, "run")
            self.assertIn("Upload error", logger.influx_status)
            self.assertNotIn("secret-token", logger.influx_status)
            self.assertEqual(logger.influx_uploaded, 0)
            client.write_api.return_value.write.side_effect = None
            queue.put(({"temperature": 21.0}, 2))
            queue.put(None)
            logger._run_influx(queue, "run")
        self.assertEqual(logger.influx_uploaded, 1)
        self.assertEqual(logger.influx_failed, 1)
        self.assertIsNone(logger.last_influx_error)
        self.assertIn("1 failed", logger.influx_status)
        self.assertIn("Last upload", logger.influx_status)

    def test_relay_needs_no_influx_token_and_corrects_clock(self):
        logger = self.logger({"Value": lambda: 23})
        logger._influx_sources = {"temperature": lambda: 23}
        logger._write_mode = "relay"
        owner_thread = threading.get_ident()

        def student():
            self.assertEqual(threading.get_ident(), owner_thread)
            return "group1"

        logger._student_id_var = SimpleNamespace(get=student)
        session = Mock()
        session.get.return_value.json.return_value = {"server_time_ns": 100_000_000_000}
        with patch("core.data_logger.requests.Session") as session_class, patch.multiple(
                "core.data_logger", INFLUX_AVAILABLE=False, INFLUX_TOKEN=""), patch(
                    "core.data_logger.time_ns", return_value=10_000_000_000):
            session_class.return_value.__enter__.return_value = session
            logger.start()
            logger.stop()
            logger._influx_thread.join(timeout=1)
        self.assertEqual(logger.influx_uploaded, 1)
        self.assertEqual(logger.clock_offset_seconds, 90)
        payload = session.post.call_args.kwargs["json"]
        self.assertEqual(payload["student_id"], "group1")
        self.assertEqual(payload["timestamp_ns"], 100_000_000_000)
        self.assertEqual(payload["fields"], {"temperature": 23.0})
        self.assertIn("timestamps corrected", logger.influx_status)

    def test_relay_rejection_preserves_csv_without_direct_fallback(self):
        logger = self.logger({"Value": lambda: 1})
        logger._influx_sources = {"value": lambda: 1}
        logger._write_mode = "relay"
        logger._student_id_var = SimpleNamespace(get=lambda: "group1")
        session = Mock()
        session.get.return_value.json.return_value = {"server_time_ns": 100}
        session.post.return_value.raise_for_status.side_effect = requests.HTTPError("403 denied")
        with patch("core.data_logger.requests.Session") as session_class, patch.object(
                logger, "_run_influx") as direct:
            session_class.return_value.__enter__.return_value = session
            logger.start()
            logger.stop()
            logger._influx_thread.join(timeout=1)
        direct.assert_not_called()
        self.assertEqual(logger.influx_failed, 1)
        self.assertEqual(logger.influx_uploaded, 0)
        self.assertIn("403", logger.influx_status)
        self.assertEqual(len(self.rows(logger)), 1)

    def test_slow_failed_historian_does_not_block_csv_or_stop(self):
        entered = threading.Event()
        release = threading.Event()
        client = Mock()

        def blocked_write(**kwargs):
            entered.set()
            release.wait(timeout=3)
            raise OSError("historian unavailable")

        client.write_api.return_value.write.side_effect = blocked_write
        point = Mock()
        point.tag.return_value = point
        logger = self.logger({"Value": lambda: 1}, ("Value",))
        logger._influx_sources = {"value": lambda: 1}
        with patch.multiple("core.data_logger", INFLUX_AVAILABLE=True, INFLUX_TOKEN="test",
                            InfluxDBClient=Mock(return_value=client), Point=Mock(return_value=point),
                            WritePrecision=SimpleNamespace(NS="ns"), SYNCHRONOUS=object(), create=True):
            try:
                logger.start()
                self.assertTrue(entered.wait(timeout=1))
                self.scheduler.run(logger._capture_id)
                logger.stop()
                self.assertFalse(logger._thread.is_alive())
                self.assertEqual(len(self.rows(logger)), 2)
                self.assertTrue(logger._influx_thread.is_alive())
                self.assertIsNone(logger.last_error)
            finally:
                release.set()
                logger._influx_thread.join(timeout=1)
        self.assertIn("historian unavailable", logger.last_influx_error)
        client.close.assert_called_once()

    def test_open_failure_is_visible_and_does_not_claim_logging_started(self):
        logger = self.logger({})
        with patch("builtins.open", side_effect=OSError("disk unavailable")):
            with self.assertRaisesRegex(OSError, "disk unavailable"):
                logger.start()
        self.assertFalse(logger.is_logging)
        self.assertEqual(self.scheduler.callbacks, {})

    def test_write_failure_reports_to_ui_and_can_restart(self):
        errors = []
        logger = self.logger({"Value": lambda: 1}, ("Value",), errors.append)
        real_writer = csv.writer

        class FailingWriter:
            def __init__(self, file):
                self.writer = real_writer(file)
                self.calls = 0

            def writerow(self, row):
                self.calls += 1
                if self.calls > 1:
                    raise OSError("disk full")
                self.writer.writerow(row)

        with patch("core.data_logger.csv.writer", FailingWriter):
            logger.start()
            logger._thread.join(timeout=1)
        # A fast worker failure may already have been reported during start.
        if logger._status_id is not None:
            self.scheduler.run(logger._status_id)
        self.assertFalse(logger.is_logging)
        self.assertEqual(len(errors), 1)
        self.assertIn("disk full", errors[0])
        on_saved = Mock()
        logger.stop(on_saved=on_saved)
        on_saved.assert_not_called()
        logger.start()
        logger.stop()
        self.assertEqual(len(self.rows(logger)), 1)
        self.assertIsNone(logger.last_error)


if __name__ == "__main__":
    unittest.main()
