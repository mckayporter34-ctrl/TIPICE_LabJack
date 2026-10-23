"""Airflow mapping, conversion, layout and output checks without real hardware."""

import csv
import os
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from tkinter import ttk
from unittest.mock import Mock, patch

from configs import airflow
from core.safety import SafetyManager, SafetyState
from ui_test_support import gui_root


class AirflowConfigTests(unittest.TestCase):
    def test_current_channels_match_workbook_ranges_at_three_points(self):
        expected = {
            "pitot_delta_p": ("AIN4", 2.5), "pitot_entrance_pressure": ("AIN5", 2),
            "nozzle_delta_p": ("AIN6", 10), "nozzle_entrance_pressure": ("AIN7", 2),
            "orifice_delta_p": ("AIN8", 1), "orifice_entrance_pressure": ("AIN9", 2),
            "rotameter_entrance_pressure": ("AIN10", 2),
            "venturi_delta_p": ("AIN12", 2), "venturi_entrance_pressure": ("AIN13", 2),
        }
        for key, (pin, full_scale) in expected.items():
            with self.subTest(sensor=key):
                cfg = airflow.SENSOR_CONFIGS[key]
                self.assertEqual(cfg["pin"], pin)
                for voltage, fraction in ((0.472, 0), (1.416, 0.5), (2.360, 1)):
                    self.assertAlmostEqual(cfg["calibration"](voltage), fraction * full_scale)
        flow = airflow.CONTROL_LOOP_CONFIGS["flowrate"]
        self.assertEqual((flow["input_pin"], flow["output_pin"]), ("AIN11", "DAC0"))
        for voltage, value in ((0.472, 0), (1.416, 175), (2.360, 350)):
            self.assertAlmostEqual(flow["calibration"](voltage), value)
        self.assertEqual(airflow.SENSOR_CONFIGS["nozzle_delta_p"]["unit"], "in WC")

    def test_type_t_removes_amplifier_offset_and_gain_and_passes_cjc(self):
        convert = Mock(return_value=373.15)
        with patch.dict("sys.modules", {"labjack": SimpleNamespace(ljm=SimpleNamespace(tcVoltsToTemp=convert))}), \
                patch.object(airflow, "_cj_temp_c", [25.0]):
            self.assertAlmostEqual(airflow._type_t_temp(1.25 + 51 * 0.003), 100.0)
        tc_type, volts, cj_k = convert.call_args.args
        self.assertEqual(tc_type, 6008)
        self.assertAlmostEqual(volts, 0.003)
        self.assertAlmostEqual(cj_k, 298.15)

    def test_logging_covers_every_planned_input_once(self):
        pins = [cfg["pin"] for cfg in airflow.SENSOR_CONFIGS.values()]
        pins.append(airflow.CONTROL_LOOP_CONFIGS["flowrate"]["input_pin"])
        self.assertCountEqual(pins, [f"AIN{i}" for i in range(14)])
        sensor_columns = [key for kind, key in airflow.LOG_COLUMNS.values() if kind == "sensor"]
        self.assertCountEqual(sensor_columns, airflow.SENSOR_CONFIGS.keys())


class FakeAirflowDAQ:
    def __init__(self):
        self.is_connected = False
        self.writes = []
        self.reads = []
        self.safety = SafetyManager(self._force_write)

    def connect(self, *args):
        self.is_connected = True
        self.safety.transition_to(SafetyState.CONNECTED_SAFE)

    def disconnect(self):
        self.safety.transition_to(SafetyState.SHUTTING_DOWN)
        self.is_connected = False
        self.safety.transition_to(SafetyState.DISCONNECTED)

    def read(self, pin):
        self.reads.append(pin)
        if pin == "TEMPERATURE_DEVICE_K":
            return 298.15
        if pin in ("AIN0", "AIN1", "AIN2", "AIN3"):
            return 1.25
        return 1.416

    def write(self, pin, value):
        if self.safety.can_write():
            self._force_write(pin, value)

    def _force_write(self, pin, value):
        self.writes.append((pin, value))


@unittest.skipUnless(os.environ.get("LABJACK_GUI_TESTS") == "1", "requires a window server")
class AirflowUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = gui_root()
        cls.root.withdraw()
        cls.root.tk.call("set", "scalef", 1)
        for mode in ("light", "dark"):
            if f"forest-{mode}" not in ttk.Style(cls.root).theme_names():
                cls.root.tk.call("source", str(Path(f"assets/forest-{mode}.tcl").resolve()))
        ttk.Style(cls.root).theme_use("forest-light")

    @classmethod
    def tearDownClass(cls):
        cls.root.withdraw()

    def setUp(self):
        self.errors = []
        self.root.report_callback_exception = lambda *exc: self.errors.append(exc)
        self.temp = tempfile.TemporaryDirectory()
        self.daq = FakeAirflowDAQ()
        self.ljm_patch = patch.dict("sys.modules", {
            "labjack": SimpleNamespace(ljm=SimpleNamespace(tcVoltsToTemp=lambda kind, v, cj: cj))
        })
        self.ljm_patch.start()
        self.frame = airflow.FrameClass(self.root, airflow, self.daq)
        self.frame.logger._folder = self.temp.name
        self.frame.pack(fill="both", expand=True)

    def tearDown(self):
        if self.frame.winfo_exists():
            self.frame.destroy()
        self.root.withdraw()
        self.root.update()
        self.ljm_patch.stop()
        self.temp.cleanup()
        self.assertEqual(self.errors, [])

    def connect_and_enable(self):
        self.frame._connect("T7", "USB", "ANY")
        self.assertTrue(self.frame._main_power_on)
        self.assertEqual(self.daq.safety.state, SafetyState.ENABLED)
        self.assertFalse(hasattr(self.frame, "_power_switch"))

    def test_canvas_readouts_and_pressures_are_below_at_shared_size(self):
        self.root.geometry("1450x800+0+40")
        self.root.deiconify()
        self.root.update()
        frame = self.frame
        self.assertEqual(len(frame._overlay_cards), 11)
        self.assertTrue(frame._logo_label.cget("image"))
        self.assertEqual(str(frame._flow_entry.cget("textvariable")), str(frame.loops["flowrate"].measured_var))
        self.assertEqual(str(frame._valve_entry.cget("textvariable")),
                         str(frame.loops["flowrate"].rounded_valve_position))
        for key in airflow.DELTA_P_KEYS:
            entry = frame._sensor_widgets[key]["entry"]
            self.assertEqual(entry.master.master, frame._pid)
        for key in airflow.ENTRANCE_PRESSURE_KEYS:
            self.assertEqual(frame._sensor_widgets[key]["entry"].master, frame._entrance_panel)
        self.assertGreater(frame._entrance_panel.winfo_rooty(), frame._pid.winfo_rooty() + frame._pid.winfo_height())
        self.assertLessEqual(frame._sf.winfo_height(), frame._canvas.winfo_height())
        # All overlay windows must remain separated and inside the drawing canvas.
        readout_items = [frame._delta_overlays[0][1], frame._flow_overlay,
                         *(item for _, item in frame._delta_overlays[1:]), frame._rotameter_overlay]
        bounds = [frame._pid.bbox(item) for item in readout_items]
        for left, top, right, bottom in bounds:
            self.assertGreaterEqual(left, 0)
            self.assertLessEqual(right, frame._pid.winfo_width())
            self.assertLessEqual(bottom, frame._pid.winfo_height())
        for a, b in zip(bounds, bounds[1:]):
            self.assertLess(a[2], b[0])
        image_left, image_top, image_right, _ = frame._pid.bbox(frame._diagram_item)
        scale = (image_right - image_left) / frame._diagram_image.width
        for _, item in frame._delta_overlays:
            self.assertAlmostEqual(frame._pid.bbox(item)[1], image_top + 294 * scale, delta=1)
        valve_left, valve_top, valve_right, _ = frame._pid.bbox(frame._valve_overlay)
        self.assertGreaterEqual(valve_left, 0)
        self.assertGreaterEqual(valve_top, 0)
        self.assertLess(valve_right, image_left + 239 * scale)
        for number, (x, item) in enumerate(frame._temperature_overlays, start=1):
            key = f"temperature_{number}"
            entry = frame._temperature_entries[key]
            self.assertEqual(str(entry.cget("textvariable")), str(frame.sensors[key].value_var))
            left, top, right, bottom = frame._pid.bbox(item)
            entry_center = left + entry.winfo_x() + entry.winfo_width() / 2
            if number < 4:
                self.assertAlmostEqual(entry_center, image_left + x * scale, delta=1)
            else:
                self.assertLessEqual(right, image_left + 1105 * scale - 7)
            self.assertGreaterEqual(top, 0)
            self.assertLess(bottom, image_top + 177 * scale)  # Above the matching TI circle.
            self.assertLessEqual(right, frame._pid.winfo_width())
        panels = [widget for widget in frame._sf.winfo_children() if isinstance(widget, ttk.LabelFrame)]
        self.assertCountEqual([str(panel.cget("text")) for panel in panels],
                              ["Piping and Instrumentation Diagram", "Entrance Pressures (psi)"])
        self.assertAlmostEqual(frame._sf.winfo_height(), frame._canvas.winfo_height(), delta=1)
        frame._toggle_theme()
        self.assertEqual(ttk.Style().theme_use(), "forest-dark")
        frame._toggle_theme()

    def test_connection_failure_and_reconnect_keep_outputs_safe(self):
        frame = self.frame
        with patch.object(self.daq, "_force_write", side_effect=OSError("configuration failed")), \
                patch("core.base_app.messagebox.showerror"):
            frame._connect("T7", "USB", "ANY")
        self.assertFalse(frame._main_power_on)
        self.assertFalse(self.daq.is_connected)
        self.assertIn("disabled", frame._loop_widgets["flowrate"]["scale"].state())
        self.connect_and_enable()
        frame.loops["flowrate"].set_valve_display(60)
        frame._update_all_loops()
        frame._connect("T7", "USB", "ANY")
        self.assertTrue(frame._main_power_on)
        self.assertEqual(frame.loops["flowrate"].rounded_valve_position.get(), 0)
        self.assertIn(("DAC0", 0.0), self.daq.writes)

    def test_manual_auto_bounds_and_shutdown_never_touch_a_guessed_relay(self):
        frame = self.frame
        self.assertEqual(self.daq.reads, [])
        frame._update_all_sensors()
        frame._update_all_loops()
        self.assertEqual(self.daq.reads, [])
        self.connect_and_enable()
        loop = frame.loops["flowrate"]
        widgets = frame._loop_widgets["flowrate"]
        for percent, voltage in ((50, 2.5), (150, 5.0), (-5, 0.0)):
            loop.rounded_valve_position.set(percent)
            frame._update_all_loops()
            self.assertEqual(self.daq.writes[-1], ("DAC0", voltage))
        widgets["mode_switch"].invoke()
        self.assertTrue(loop.is_auto)
        self.assertEqual(str(widgets["setpoint_spinbox"].cget("state")), "disabled")
        frame._disconnect()
        self.assertEqual(self.daq.writes[-1], ("DAC0", 0.0))
        self.assertFalse(loop.is_auto)
        self.assertEqual(loop.rounded_valve_position.get(), 0)
        self.assertFalse(any(pin.startswith(("DIO", "FIO", "EIO")) for pin, _ in self.daq.writes))

    def test_all_inputs_update_log_and_cjc_failures_are_visible(self):
        frame = self.frame
        self.connect_and_enable()
        frame._update_all_sensors()
        frame._update_all_loops()
        for i in range(4):
            self.assertEqual(frame.sensors[f"temperature_{i + 1}"].value_var.get(), "25.00")
        self.assertEqual(frame.sensors["pitot_delta_p"].value_var.get(), "1.25")
        self.assertEqual(frame.loops["flowrate"].measured_var.get(), "175.00")
        self.assertIn("AIN13", self.daq.reads)
        frame._on_toggle_logging()
        filepath = frame.logger.filepath
        frame.logger.stop()
        with open(filepath, newline="") as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(len(rows), 2)
        self.assertNotIn("Error", rows[1])
        self.assertEqual(len(rows[1]), 20)
        original_read = self.daq.read
        def fail_cjc(pin):
            if pin == "TEMPERATURE_DEVICE_K":
                raise OSError("cold junction unavailable")
            return original_read(pin)
        with patch.object(self.daq, "read", side_effect=fail_cjc):
            frame._update_all_sensors()
        self.assertEqual(frame.sensors["temperature_1"].value_var.get(), "Error")
        self.assertEqual(frame.sensors["pitot_delta_p"].value_var.get(), "1.25")
        frame._disconnect()
        self.assertTrue(all(s.value_var.get() == "---" for s in frame.sensors.values()))


if __name__ == "__main__":
    unittest.main()
