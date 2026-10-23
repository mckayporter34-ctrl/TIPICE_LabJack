"""Real Tk widgets with fake I/O; enable with LABJACK_GUI_TESTS=1."""

import csv
import faulthandler
import importlib
import os
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

from core.base_app import BaseAppFrame
from core.safety import SafetyManager, SafetyState
from ui_test_support import gui_root


CONFIGS = ["shell_tube_hx_1", "shell_tube_hx_2", "shell_tube_hx_3",
           "catalytic_methanation_1", "catalytic_methanation_2", "packed_columns", "pump_cart"]


class FakeDAQ:
    def __init__(self):
        self.safety = SafetyManager()
        self.is_connected = False
        self.writes = []
        self.value = 1.0

    def read(self, pin):
        return self.value

    def write(self, pin, value):
        self.writes.append((pin, value))


@unittest.skipUnless(os.environ.get("LABJACK_GUI_TESTS") == "1", "requires a window server")
class AppUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Aqua Tk uses one application/window-server connection per process.
        cls.root = gui_root()
        cls.root.withdraw()
        cls.root.tk.call("set", "scalef", 1)
        if "forest-light" not in ttk.Style(cls.root).theme_names():
            cls.root.tk.call("source", str(Path("assets/forest-light.tcl").resolve()))
        ttk.Style(cls.root).theme_use("forest-light")

    @classmethod
    def tearDownClass(cls):
        cls.root.withdraw()

    def setUp(self):
        faulthandler.dump_traceback_later(15)
        self.errors = []
        self.root.report_callback_exception = lambda *exc: self.errors.append(exc)
        self.temp = tempfile.TemporaryDirectory()
        self.dialog = patch("tkinter.messagebox.showerror")
        self.showerror = self.dialog.start()
        self.password = patch("tkinter.simpledialog.askstring", return_value="dietcoke")
        self.password.start()
        self.frames = []

    def tearDown(self):
        faulthandler.cancel_dump_traceback_later()
        for frame in self.frames:
            if frame.winfo_exists():
                self.close_frame(frame)
        for callback_id in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback_id)
        self.dialog.stop()
        self.password.stop()
        self.temp.cleanup()
        self.assertEqual(self.errors, [], "uncaught Tk callback errors")

    def close_frame(self, frame):
        # Isolate tests from the legacy animation/control schedulers.
        owners = {}
        def visit(widget):
            for command in widget._tclCommands or ():
                owners[command] = widget
            for child in widget.winfo_children():
                visit(child)
        visit(frame)
        for callback_id in self.root.tk.call("after", "info"):
            script = self.root.tk.call("after", "info", callback_id)[0]
            command = str(script).split()[0]
            if command in owners:
                owners[command].after_cancel(callback_id)
        frame.destroy()

    def frame(self, name):
        config = importlib.import_module("configs." + name)
        cls = getattr(config, "FrameClass", BaseAppFrame)
        frame = cls(self.root, config, FakeDAQ())
        frame.logger._folder = self.temp.name
        self.frames.append(frame)
        return frame

    def panels(self, frame):
        if hasattr(frame, "_simple_panel_widgets"):
            if "water_flow" in frame._simple_panel_widgets:
                return [(frame.loops["water_flow"], frame._simple_panel_widgets["water_flow"],
                         "sp", "mode"),
                        (frame.loops["column1_level"], frame._simple_panel_widgets["level"],
                         "sp", "mode")]
            return [(frame.loops[k], w, "sp", "mode")
                    for k, w in frame._simple_panel_widgets.items()]
        return [(frame.loops[k], w, "setpoint_spinbox", "mode_switch")
                for k, w in frame._loop_widgets.items()]

    def pump(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.005)

    def test_setpoints_manual_edit_auto_lock_power_cycle_all_systems(self):
        for name in CONFIGS:
            with self.subTest(system=name):
                frame = self.frame(name)
                for loop, widgets, sp_key, mode_key in self.panels(frame):
                    self.assertEqual(str(widgets[sp_key].cget("state")), "disabled")
                frame._main_power_on = True
                frame._enable_powered_controls()
                for loop, widgets, sp_key, mode_key in self.panels(frame):
                    if loop.key == "column1_level":
                        frame._col_select_var.set(True)
                        frame._on_column_select()
                    sp = widgets[sp_key]
                    self.assertEqual(str(sp.cget("state")), "normal")
                    sp.delete(0, "end")
                    sp.insert(0, "12.5")
                    self.assertEqual(loop.get_setpoint(), 12.5)
                    widgets[mode_key].invoke()
                    self.assertTrue(loop.is_auto)
                    self.assertEqual(str(sp.cget("state")), "disabled")
                    sp.delete(0, "end")
                    sp.insert(0, "99")
                    sp.event_generate("<<Increment>>")
                    sp.event_generate("<<Decrement>>")
                    self.assertEqual(loop.get_setpoint(), 12.5)
                    frame._disable_powered_controls()
                    frame._enable_powered_controls()
                    if loop.key == "column1_level":
                        frame._col_select_var.set(True)
                        frame._on_column_select()
                    self.assertEqual(str(sp.cget("state")), "disabled")
                    widgets[mode_key].invoke()
                    self.assertFalse(loop.is_auto)
                    self.assertEqual(str(sp.cget("state")), "normal")
                self.close_frame(frame)

    def test_switch_packed_column_preserves_each_setpoint_and_lock(self):
        frame = self.frame("packed_columns")
        frame._main_power_on = True
        frame._enable_powered_controls()
        widgets = frame._simple_panel_widgets["level"]
        sp = widgets["sp"]
        sp.set("15")
        widgets["mode"].invoke()
        frame._col_select_var.set(False)
        frame._on_column_select()
        self.assertEqual(str(sp.cget("state")), "normal")
        sp.set("27")
        widgets["mode"].invoke()
        self.assertEqual(str(sp.cget("state")), "disabled")
        frame._col_select_var.set(True)
        frame._on_column_select()
        self.assertEqual(sp.get(), "15")
        self.assertEqual(str(sp.cget("state")), "disabled")
        frame._col_select_var.set(False)
        frame._on_column_select()
        self.assertEqual(sp.get(), "27")
        self.assertEqual(str(sp.cget("state")), "disabled")
        widgets["mode"].invoke()
        sp.delete(0, "end")
        sp.insert(0, "x")
        self.root.update_idletasks()
        self.assertEqual(sp.get(), "")
        self.assertTrue(self.showerror.called)

    def test_all_numeric_boxes_reject_letters_pastes_and_nonfinite_values(self):
        count = 0
        for name in CONFIGS:
            frame = self.frame(name)
            def walk(parent):
                for widget in parent.winfo_children():
                    if isinstance(widget, ttk.Spinbox):
                        yield widget
                    yield from walk(widget)
            for widget in walk(frame):
                with self.subTest(system=name, widget=str(widget)):
                    widget.configure(state="normal")
                    for bad in ("x", "1.2x", "NaN", "inf", "1e999"):
                        widget.delete(0, "end")
                        before = self.showerror.call_count
                        widget.insert(0, bad)
                        self.root.update_idletasks()
                        self.assertEqual(widget.get(), "")
                        self.assertGreater(self.showerror.call_count, before)
                    widget.insert(0, "1")
                    self.assertEqual(widget.get(), "1")
                    self.assertEqual(str(widget.cget("validate")), "key")
                    count += 1
            self.close_frame(frame)
        self.assertGreater(count, 60)

    def test_partial_numeric_edits_and_empty_commit(self):
        frame = self.frame("shell_tube_hx_1")
        frame._main_power_on = True
        frame._enable_powered_controls()
        widget = frame._simple_panel_widgets["flowrate"]["pid_Kc"]
        widget.delete(0, "end")
        for char in "-1.5e-2":
            widget.insert("end", char)
        self.assertEqual(widget.get(), "-1.5e-2")
        self.assertFalse(self.showerror.called)
        widget.delete(0, "end")
        widget.event_generate("<FocusOut>")
        self.root.update_idletasks()
        self.assertEqual(widget.get(), "-1.5e-2")
        self.assertTrue(self.showerror.called)

    def test_logging_survives_actual_tk_bad_inputs_and_sensor_failure(self):
        frame = self.frame("shell_tube_hx_1")
        owner = threading.get_ident()
        for header, source in list(frame.logger._sources.items()):
            def read(fn=source):
                self.assertEqual(threading.get_ident(), owner)
                return fn()
            frame.logger._sources[header] = read
        frame._log_interval_var.set(0.1)
        frame._on_toggle_logging()
        self.pump(0.15)
        loop = frame.loops["flowrate"]
        loop.Kc_var.set("bad")
        frame.daq.value = float("nan")
        frame._update_all_sensors()
        frame._update_all_loops()
        self.pump(0.25)
        self.assertTrue(frame.logger.is_logging)
        self.assertGreaterEqual(frame._data_point_count.get(), 3)
        loop.Kc_var.set("0.74")
        frame.daq.value = 1.0
        frame._update_all_sensors()
        self.pump(0.15)
        frame.logger.stop()
        with open(frame.logger.filepath, newline="", encoding="utf-8") as file:
            rows = list(csv.DictReader(file))
        kc = next(header for header, (kind, key) in frame.config.LOG_COLUMNS.items()
                  if kind == "loop_kc" and key == "flowrate")
        self.assertTrue(any(row[kc] == "Error" for row in rows))
        self.assertEqual(rows[-1][kc], "0.74")
        self.assertEqual(frame.logger.last_error, None)

    def test_catalytic_text_columns_and_orange_cylinder_both_units(self):
        from apps.catalytic_methanation import HE_CYLINDER_COLOR
        for name in ("catalytic_methanation_1", "catalytic_methanation_2"):
            frame = self.frame(name)
            items = frame._pid.find_withtag("helium_cylinder")
            self.assertEqual(len(items), 3)
            for item in items[:2]:
                self.assertEqual(frame._pid.itemcget(item, "fill"), HE_CYLINDER_COLOR)
            frame.logger.start()
            frame.logger.stop()
            with open(frame.logger.filepath, newline="", encoding="utf-8") as file:
                row = next(csv.DictReader(file))
            self.assertEqual(row["GC Analysis Stream"], "Feed")
            self.assertEqual(row["Heater Power State"], "OFF")
            self.close_frame(frame)

    def test_invalid_logging_interval_shows_error_without_starting(self):
        frame = self.frame("packed_columns")
        self.root.globalsetvar(str(frame._log_interval_var), "bad")
        frame._on_toggle_logging()
        self.assertFalse(frame.logger.is_logging)
        self.assertEqual(frame._logging_text_var.get(), "Start Logging")
        self.assertTrue(self.showerror.called)

    def test_destroy_stops_logging_and_cancels_logger_callbacks(self):
        frame = self.frame("shell_tube_hx_1")
        frame.logger.start()
        frame.destroy()
        self.assertFalse(frame.logger.is_logging)
        self.assertFalse(frame.logger._thread.is_alive())
        self.assertIsNone(frame.logger._capture_id)
        self.assertIsNone(frame.logger._status_id)


if __name__ == "__main__":
    unittest.main()
