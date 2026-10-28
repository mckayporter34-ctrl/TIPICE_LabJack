import csv
import math
from datetime import datetime
import tempfile
import threading
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
        for _ in range(5):
            logger.start()
            logger.start()
            files.append(logger.filepath)
            logger.stop()
            self.assertEqual(len(self.rows(logger)), 1)
            self.assertFalse(logger._thread.is_alive())
        self.assertEqual(len(set(files)), 5)

    def test_interval_validation(self):
        logger = self.logger({})
        for bad in ("bad", "", math.nan, math.inf, 0, -1):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                logger.set_interval(bad)
        logger.set_interval(0.01)
        self.assertEqual(logger._interval, 0.1)

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
        self.assertEqual(point.field.call_args_list[0].args, ("temperature", 21.5))
        self.assertEqual(point.field.call_args_list[1].args, ("temperature", 22.0))
        run_tags = [call.args for call in point.tag.call_args_list if call.args[0] == "run_id"]
        self.assertEqual(run_tags, [("run_id", "Group_A_143015")] * 2)
        point.tag.assert_any_call("unit_op", "STHX1")
        client.close.assert_called_once()

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
        logger.stop()
        logger.start()
        logger.stop()
        self.assertEqual(len(self.rows(logger)), 1)
        self.assertIsNone(logger.last_error)


if __name__ == "__main__":
    unittest.main()
