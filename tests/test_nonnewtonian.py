"""Non-Newtonian control, temperature, lifecycle and layout checks with fake I/O."""

import csv
import importlib
import math
import os
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from apps.nonnewtonian import NonNewtonianFrame
from core.base_app import BaseAppFrame
from configs import AVAILABLE_CONFIGS, nonnewtonian_1 as config, nonnewtonian_2 as config2
from core.control_loop import ControlLoop
from core.pid_controller import PIDController
from core.safety import SafetyManager, SafetyState
from ui_test_support import gui_root


class FakeDAQ:
    def __init__(self):
        self.is_connected = False
        self.writes = []
        self.reads = []
        self.values = {"AIN0": 1.0, "AIN1": 1.0, "AIN2": 1.0}
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
        return self.values[pin]

    def write(self, pin, value):
        if self.safety.can_write():
            self._force_write(pin, value)

    def _force_write(self, pin, value):
        self.writes.append((pin, value))


def assert_pump_indicator(test, frame, on):
    label = frame._pump_status_label
    test.assertIs(label.master, frame._pid)
    test.assertEqual(label.cget("text"), "Pump: ON" if on else "Pump: OFF")
    test.assertEqual(label.cget("bg"), "#2e7d32" if on else "#b71c1c")


def assert_diagram_alignment(test, frame):
    image_left, image_top = frame._pid.coords(frame._diagram_item)
    width, height = frame._diagram_image.size
    scale = min((frame._pid.winfo_width() - 64) / width,
                (frame._pid.winfo_height() - 110) / height)
    for key, _, x, _, _ in frame.config.DIAGRAM_READOUTS:
        if key in ("fluid_temperature", "flowrate"):
            entry = frame._readout_widgets[key]["entry"]
            center = entry.winfo_rootx() - frame._pid.winfo_rootx() + entry.winfo_width() / 2
            test.assertAlmostEqual(center, image_left + x * scale, delta=1.5)
    left, top, right, bottom = frame._pid.bbox(frame._pump_status_item)
    # Pump center/top landmarks in the current source exports.
    pump_center_x, pump_top_y = (350, 189) if frame.config is config else (868, 468)
    test.assertAlmostEqual((left + right) / 2, image_left + pump_center_x * scale, delta=1)
    test.assertLess(bottom, image_top + pump_top_y * scale)

    def labels(parent):
        for widget in parent.winfo_children():
            if isinstance(widget, (tk.Label, ttk.Label)):
                yield widget
            yield from labels(widget)
    panel = frame._loop_widgets["flowrate"]["frame"]
    for label in labels(panel):
        test.assertNotIn("0% =", label.cget("text"))
        test.assertNotEqual(str(label.cget("textvariable")), str(frame._control_message))


def check_controls_available_with_pump_off(test):
    frame, daq = test.frame, test.daq
    widgets = frame._loop_widgets["flowrate"]
    frame._connect("T7", "USB", "ANY")
    test.assertFalse(frame._switch_vars["pump"].get())
    assert_pump_indicator(test, frame, False)
    roles = ("setpoint_spinbox", "mode_switch", "scale", "manual_spinbox",
             "Kc_spinbox", "Ti_spinbox", "Td_spinbox")
    for role in roles:
        test.assertNotIn("disabled", widgets[role].state(), role)
    test.assertNotIn("disabled", frame._pump_switch.state())
    test.assertNotIn("disabled", frame._toggle_logging_btn.state())
    frame._experiment_id_var.set("")
    test.assertNotIn("disabled", frame._toggle_logging_btn.state())

    daq.writes.clear()
    frame.loops["flowrate"].setpoint_var.set("10")
    frame.loops["flowrate"].rounded_valve_position.set(50)
    frame._update_all_sensors()
    frame._update_all_loops()
    expected_writes = [("DAC0", 2.5)] if frame.config is config2 else []
    test.assertEqual(daq.writes, expected_writes)
    widgets["mode_switch"].invoke()
    test.assertTrue(frame.loops["flowrate"].is_auto)
    frame._update_all_loops()
    test.assertEqual(daq.writes, expected_writes, "AUTO must not run while the pump is off")
    widgets["mode_switch"].invoke()
    for role in roles:
        test.assertNotIn("disabled", widgets[role].state(), role)

    frame._toggle_logging_btn.invoke()
    test.assertTrue(frame.logger.is_logging)
    test.assertRegex(frame.logger._active_run_id, r"^Unnamed_Run_\d{6}$")
    frame._toggle_logging_btn.invoke()
    test.assertFalse(frame.logger.is_logging)
    frame._disconnect()
    for role in roles:
        test.assertIn("disabled", widgets[role].state(), role)
    test.assertIn("disabled", frame._toggle_logging_btn.state())
    assert_pump_indicator(test, frame, False)


class NonNewtonianControlTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tcl()
        self.loop = ControlLoop(
            "flowrate", "Flowrate", "GPM", "AIN1", "TDAC2", config._flowrate_gpm, 0, 30,
            PIDController(Kc=0.1, Ti=1, output_max=10),
            setpoint_var=tk.StringVar(self.root, "0"), measured_var=tk.StringVar(self.root),
            valve_position=tk.DoubleVar(self.root), rounded_valve_position=tk.IntVar(self.root),
            Kc_var=tk.StringVar(self.root), Ti_var=tk.StringVar(self.root), Td_var=tk.StringVar(self.root))
        self.daq = FakeDAQ()
        self.daq.connect()
        self.daq.safety.transition_to(SafetyState.ENABLED)
        self.app = SimpleNamespace(
            _polling=True, _main_power_on=True, config=config, loops={"flowrate": self.loop}, daq=self.daq,
            _switch_vars={"pump": tk.BooleanVar(self.root, True)},
            _control_message=tk.StringVar(self.root), after=Mock(), _fault=Mock())
        self.app._update_all_loops = self.update

    def update(self):
        NonNewtonianFrame._update_all_loops(self.app)

    def test_registry_and_legacy_mapping_and_calibrations(self):
        unit = AVAILABLE_CONFIGS["nonnewtonian"]["units"][0]
        self.assertIs(importlib.import_module(unit["module"]), config)
        self.assertEqual(config.ETHERNET_ADDRESS, "10.8.112.140")
        self.assertTrue(Path(config.PID_IMAGE).is_file())
        self.assertEqual(config.SENSOR_CONFIGS["fluid_temperature"]["pin"], "AIN0")
        self.assertEqual(config.SENSOR_CONFIGS["pressure_drop"]["pin"], "AIN2")
        for voltage in (0.472, 1.416, 2.360):
            self.assertEqual(round(config._temperature_c(voltage), 2), round(55.28745157 * voltage - 48.08422656, 2))
            self.assertEqual(round(config._flowrate_gpm(voltage), 2), round((53.2187707 * voltage - 25.35572892) * 0.264172, 2))
            self.assertEqual(round(config._pressure_drop_wc(voltage), 2), round(3.125 * 8.475 * voltage - 12.5, 2))

    def test_manual_mapping_clamps_typed_percent_and_preserves_other_system_range(self):
        for percent, voltage in ((0, 0), (25, 2.5), (50, 5), (100, 10), (150, 10), (-10, 0)):
            with self.subTest(percent=percent):
                self.loop.rounded_valve_position.set(percent)
                self.update()
                self.assertEqual(self.daq.writes[-1], ("TDAC2", voltage))
                self.assertEqual(self.loop.valve_position.get(), voltage * 10)
        self.loop.pid = PIDController()  # Existing apparatuses retain 0–5 V.
        self.loop.rounded_valve_position.set(100)
        self.assertEqual(self.loop.get_manual_voltage(), 5)
        self.loop.set_valve_display(2.5)
        self.assertEqual(self.loop.valve_position.get(), 50)

    def test_auto_increases_pump_speed_and_saturates_at_ten_volts(self):
        self.loop.is_auto = True
        self.loop.setpoint_var.set("20")
        self.update()
        low_output = self.daq.writes[-1][1]
        self.assertGreater(low_output, 0)
        self.daq.values["AIN1"] = 0.5  # Lower flow -> greater positive error.
        self.update()
        self.assertGreater(self.daq.writes[-1][1], low_output)
        self.loop.Kc_var.set("100")
        self.update()
        self.assertEqual(self.daq.writes[-1], ("TDAC2", 10))
        self.assertEqual(self.loop.valve_position.get(), 100)
        self.loop.setpoint_var.set("0")
        self.update()
        self.assertEqual(self.daq.writes[-1], ("TDAC2", 0))

    def test_invalid_edits_zero_output_and_failed_flow_or_write_faults(self):
        self.loop.is_auto = True
        for value in ("", "nan", "31", "-1"):
            self.loop.setpoint_var.set(value)
            self.update()
            self.assertEqual(self.daq.writes[-1], ("TDAC2", 0))
        self.loop.setpoint_var.set("10")
        self.loop.Ti_var.set("-1")
        self.update()
        self.assertEqual(self.daq.writes[-1], ("TDAC2", 0))
        self.loop.Ti_var.set("1")
        self.daq.values["AIN1"] = float("nan")
        self.update()
        self.app._fault.assert_called_once()
        self.assertEqual(self.loop.measured_var.get(), "Error")
        self.app._fault.reset_mock()
        self.daq.values["AIN1"] = 1
        with patch.object(self.daq, "write", side_effect=OSError("connection lost")):
            self.update()
        self.app._fault.assert_called_once()

    def test_off_disconnected_and_stopped_never_write(self):
        self.app._switch_vars["pump"].set(False)
        self.update()
        self.assertEqual(self.daq.writes, [])
        self.daq.is_connected = False
        self.daq.reads.clear()
        self.update()
        self.assertEqual(self.daq.reads, [])
        self.app._polling = False
        self.app.after.reset_mock()
        self.update()
        self.app.after.assert_not_called()


class NonNewtonian2ConfigTests(unittest.TestCase):
    def test_workbook_channels_and_confirmed_scaling_at_three_points(self):
        self.assertEqual(config2.SENSOR_CONFIGS["fluid_temperature"]["pin"], "AIN0")
        self.assertEqual(config2.SENSOR_CONFIGS["pressure_drop"]["pin"], "AIN3")
        flow = config2.CONTROL_LOOP_CONFIGS["flowrate"]
        self.assertEqual((flow["input_pin"], flow["output_pin"]), ("AIN2", "DAC0"))
        self.assertEqual((flow["output_min"], flow["output_max"]), (0, 5))
        self.assertEqual((flow["setpoint_min"], flow["setpoint_max"]), (0, 45))
        for voltage, fraction in ((0.472, 0), (1.416, 0.5), (2.360, 1)):
            self.assertAlmostEqual(flow["calibration"](voltage), 45 * fraction)
            self.assertAlmostEqual(config2._pressure_drop_wc(voltage), 50 * fraction)
        self.assertEqual(config2.ETHERNET_ADDRESS, "")
        sw = config2.SYSTEM_SWITCHES[0]
        self.assertEqual((sw["pin"], sw["active_value"], sw["inactive_value"]), ("FIO0", 1, 0))
        self.assertTrue(Path(config2.PID_IMAGE).is_file())

    def test_connection_configures_differential_thermocouple_and_transmitter_inputs(self):
        daq = FakeDAQ()
        app = Mock(config=config2, daq=daq, loops={}, sensors={})
        NonNewtonianFrame._connect(app, "T7", "USB", "ANY")
        app._disconnect.assert_not_called()
        self.assertIn(("AIN0_NEGATIVE_CH", 1), daq.writes)
        self.assertIn(("AIN0_RANGE", 0.1), daq.writes)
        self.assertIn(("AIN0_RESOLUTION_INDEX", 8), daq.writes)
        self.assertFalse(any(pin.startswith("AIN1_") for pin, _ in daq.writes))
        for pin in ("AIN2", "AIN3"):
            self.assertIn((f"{pin}_NEGATIVE_CH", 199), daq.writes)
            self.assertIn((f"{pin}_RANGE", 10), daq.writes)
        self.assertEqual(daq.safety.state, SafetyState.ENABLED)

    def test_type_k_conversion_uses_direct_differential_voltage_and_cjc(self):
        converter = Mock(return_value=373.15)
        with patch.dict("sys.modules", {"labjack": SimpleNamespace(ljm=SimpleNamespace(tcVoltsToTemp=converter))}), \
                patch.object(config2, "_cj_temp_c", [25.0]):
            for voltage in (-0.003, 0.0, 0.003):
                with self.subTest(voltage=voltage):
                    self.assertAlmostEqual(config2._temperature_c(voltage), 100)
                    converter.assert_called_with(6004, voltage, 298.15)
            for voltage in (float("nan"), float("inf")):
                with self.subTest(voltage=voltage), self.assertRaises(ValueError):
                    config2._temperature_c(voltage)
        with patch.dict("sys.modules", {"labjack": SimpleNamespace(ljm=SimpleNamespace(tcVoltsToTemp=converter))}), \
                patch.object(config2, "_cj_temp_c", [float("nan")]):
            with self.assertRaises(ValueError):
                config2._temperature_c(0.0)

    def test_five_volt_valve_control_and_auto_action(self):
        harness = NonNewtonianControlTests()
        harness.setUp()
        harness.app.config = config2
        loop, daq = harness.loop, harness.daq
        loop.input_pin = "AIN2"
        loop.output_pin = "DAC0"
        loop.calibration = config2._flowrate
        loop.setpoint_max = 45
        loop.pid.output_max = 5
        daq.values["AIN2"] = 1.416
        for percent, volts in ((0, 0), (50, 2.5), (100, 5), (150, 5), (-10, 0)):
            loop.rounded_valve_position.set(percent)
            harness.update()
            self.assertEqual(daq.writes[-1], ("DAC0", volts))
        loop.is_auto = True
        loop.setpoint_var.set("40")
        harness.update()
        self.assertGreater(daq.writes[-1][1], 0)
        loop.Kc_var.set("100")
        harness.update()
        self.assertEqual(daq.writes[-1], ("DAC0", 5))
        loop.setpoint_var.set("0")
        harness.update()
        self.assertEqual(daq.writes[-1], ("DAC0", 0))
        self.assertFalse(any(pin == "TDAC2" for pin, _ in daq.writes))

    def test_manual_valve_works_with_pump_off_and_failed_flow_sensor(self):
        harness = NonNewtonianControlTests()
        harness.setUp()
        harness.app.config = config2
        harness.app._switch_vars["pump"].set(False)
        loop, daq = harness.loop, harness.daq
        loop.input_pin, loop.output_pin = "AIN2", "DAC0"
        loop.pid.output_max = 5
        loop.calibration = config2._flowrate
        for raw in (1.416, float("nan")):
            daq.values["AIN2"] = raw
            for percent, volts in ((0, 0), (50, 2.5), (100, 5), (150, 5), (-10, 0)):
                with self.subTest(raw=raw, percent=percent):
                    loop.rounded_valve_position.set(percent)
                    harness.update()
                    self.assertEqual(daq.writes[-1], ("DAC0", volts))
        self.assertEqual(loop.measured_var.get(), "Error")
        harness.app._fault.assert_not_called()
        self.assertTrue(all(pin == "DAC0" for pin, _ in daq.writes))
        with patch.object(daq, "read", side_effect=OSError("flow sensor unavailable")):
            loop.rounded_valve_position.set(40)
            harness.update()
        self.assertEqual(daq.writes[-1], ("DAC0", 2))
        harness.app._fault.assert_not_called()

    def test_pump_off_pauses_auto_and_disabled_states_block_manual_valve(self):
        harness = NonNewtonianControlTests()
        harness.setUp()
        harness.app.config = config2
        harness.app._switch_vars["pump"].set(False)
        loop, daq = harness.loop, harness.daq
        loop.input_pin, loop.output_pin = "AIN2", "DAC0"
        loop.pid.output_max = 5
        loop.calibration = config2._flowrate
        loop.is_auto = True
        with patch.object(loop.pid, "compute") as compute:
            harness.update()
        compute.assert_not_called()
        self.assertEqual(daq.writes, [])
        self.assertIn("paused", harness.app._control_message.get())
        loop.is_auto = False
        loop.rounded_valve_position.set(100)
        harness.app._main_power_on = False
        harness.update()
        self.assertEqual(daq.writes, [])
        daq.is_connected = False
        daq.reads.clear()
        harness.update()
        self.assertEqual(daq.reads, [])
        harness.app._polling = False
        harness.app.after.reset_mock()
        harness.update()
        harness.app.after.assert_not_called()


class NonNewtonian2TemperatureTests(unittest.TestCase):
    """Exercise real sensor updates and CSV logging without building widgets."""

    def setUp(self):
        self.root = tk.Tcl()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.daq = FakeDAQ()
        self.daq.values.update({"AIN0": 0.0, "AIN3": 1.416, "TEMPERATURE_DEVICE_K": 298.15})
        self.app = NonNewtonianFrame.__new__(NonNewtonianFrame)
        self.app.config, self.app.daq = config2, self.daq
        with patch("tkinter._default_root", self.root):
            self.app.sensors = self.app._build_sensors()
        self.app.loops = {}
        self.app._polling = True
        self.app.after = Mock()
        self.app.after_cancel = Mock()
        self.app._data_point_count = tk.IntVar(self.root)
        self.app._experiment_id_var = tk.StringVar(self.root, "filter_test")
        self.app._unit_op = "NNF2"
        self.app._on_logging_error = Mock()
        self.app._reset_loop = Mock()
        self.app._enable_powered_controls = Mock()
        self.app._main_power_var = tk.BooleanVar(self.root)
        self.app._connection_status, self.app._status_lbl = Mock(), Mock()
        self.app._connect("T7", "USB", "ANY")
        self.converter = Mock(side_effect=lambda kind, volts, cj: cj + volts * 1000)
        driver = patch.dict("sys.modules", {"labjack": SimpleNamespace(
            ljm=SimpleNamespace(tcVoltsToTemp=self.converter))})
        driver.start()
        self.addCleanup(driver.stop)

    def test_same_sample_drives_filtered_display_and_both_csv_columns(self):
        with patch("core.sensor.monotonic", side_effect=[100.0, 105.0]):
            self.app._update_all_sensors()
            self.daq.values["AIN0"] = 0.010
            self.app._update_all_sensors()
        temperature = self.app.sensors["fluid_temperature"]
        expected = 35 - 10 * math.exp(-1)
        self.assertEqual(temperature.value_var.get(), f"{expected:.2f}")
        self.assertAlmostEqual(temperature.get_raw_value(), 35)
        self.assertEqual(self.daq.reads.count("AIN0"), 2)
        self.assertEqual(self.converter.call_count, 2)
        with patch("core.data_logger.INFLUX_TOKEN", ""):
            self.app._build_logger()
            logger = self.app.logger
            self.addCleanup(logger.stop)
            logger._folder = self.temp.name
            logger.start()
            logger.stop()
        with open(logger.filepath, newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Fluid Temperature Filtered (C)"], f"{expected:.2f}")
        self.assertAlmostEqual(float(rows[0]["Fluid Temperature Raw (C)"]), 35)
        self.assertEqual(self.daq.reads.count("AIN0"), 2, "Logging must use the cached sample")

    def test_failed_cold_junction_or_thermocouple_clears_both_values_and_recovers(self):
        temperature = self.app.sensors["fluid_temperature"]
        for pin in ("TEMPERATURE_DEVICE_K", "AIN0"):
            with self.subTest(pin=pin), patch("core.sensor.monotonic", return_value=100.0):
                self.app._update_all_sensors()
                original_read = self.daq.read

                def fail_read(channel):
                    if channel == pin:
                        raise OSError("unavailable")
                    return original_read(channel)

                with patch.object(self.daq, "read", side_effect=fail_read):
                    self.app._update_all_sensors()
                self.assertEqual(temperature.value_var.get(), "Error")
                with self.assertRaises(ValueError):
                    temperature.get_raw_value()
                self.daq.values["AIN0"] = 0.005
                self.app._update_all_sensors()
                self.assertEqual(temperature.value_var.get(), "30.00")
                self.assertAlmostEqual(temperature.get_raw_value(), 30)

    def test_disconnect_and_next_connection_reset_filter_history(self):
        temperature = self.app.sensors["fluid_temperature"]
        with patch("core.sensor.monotonic", return_value=100.0):
            self.app._update_all_sensors()
        self.app.loops["flowrate"] = SimpleNamespace(measured_var=tk.StringVar(self.root))
        with patch.object(BaseAppFrame, "_disconnect", side_effect=self.daq.disconnect):
            self.app._disconnect()
        self.assertEqual(temperature.value_var.get(), "---")
        with self.assertRaises(ValueError):
            temperature.get_raw_value()
        self.app.loops.clear()
        self.app._connect("T7", "USB", "ANY")
        self.daq.values["AIN0"] = 0.015
        with patch("core.sensor.monotonic", return_value=100.5):
            self.app._update_all_sensors()
        self.assertEqual(temperature.value_var.get(), "40.00")


@unittest.skipUnless(os.environ.get("LABJACK_GUI_TESTS") == "1", "requires a window server")
class NonNewtonianUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = gui_root()
        cls.root.tk.call("set", "scalef", 1)
        for theme in ("light", "dark"):
            if f"forest-{theme}" not in ttk.Style(cls.root).theme_names():
                cls.root.tk.call("source", str(Path(f"assets/forest-{theme}.tcl").resolve()))
        ttk.Style(cls.root).theme_use("forest-light")

    def setUp(self):
        self.errors = []
        self.root.report_callback_exception = lambda *exc: self.errors.append(exc)
        self.temp = tempfile.TemporaryDirectory()
        self.daq = FakeDAQ()
        self.frame = config.FrameClass(self.root, config, self.daq)
        self.frame.logger._folder = self.temp.name
        self.frame.pack(fill="both", expand=True)

    def tearDown(self):
        self.frame.destroy()
        self.root.withdraw()
        self.root.update()
        self.temp.cleanup()
        self.assertEqual(self.errors, [])

    def start_pump(self):
        self.frame._connect("T7", "USB", "ANY")
        self.assertFalse(self.frame._switch_vars["pump"].get())
        self.frame._pump_switch.invoke()
        self.assertEqual(self.daq.writes[-1], ("FIO0", 0))

    def test_standard_layout_all_overlays_fit_without_overlapping_and_theme_changes(self):
        frame = self.frame
        for size in ("1450x800", "1200x720"):
            self.root.geometry(size + "+0+40")
            self.root.deiconify()
            self.root.update()
            assert_diagram_alignment(self, frame)
            bounds = [frame._pid.bbox(item) for _, _, item in frame._overlays]
            for left, top, right, bottom in bounds:
                self.assertGreaterEqual(left, 0)
                self.assertGreaterEqual(top, 0)
                self.assertLessEqual(right, frame._pid.winfo_width())
                self.assertLessEqual(bottom, frame._pid.winfo_height())
            for index, a in enumerate(bounds):
                for b in bounds[index + 1:]:
                    self.assertTrue(a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])
            panel = frame._loop_widgets["flowrate"]["frame"]
            self.assertGreater(panel.winfo_rooty(), frame._pid.winfo_rooty() + frame._pid.winfo_height())
        frame._toggle_theme()
        self.assertEqual(ttk.Style(self.root).theme_use(), "forest-dark")
        frame._toggle_theme()

    def test_controls_and_logging_are_available_with_pump_off_after_connection(self):
        check_controls_available_with_pump_off(self)

    def test_active_low_start_stop_auto_states_reconnect_and_shutdown(self):
        frame = self.frame
        self.daq.safety.register_safe_output("DAC1", 5)  # Another apparatus's stale map.
        self.start_pump()
        assert_pump_indicator(self, frame, True)
        self.assertEqual(self.daq.writes[:2], [("FIO0", 1), ("TDAC2", 0)])
        loop = frame.loops["flowrate"]
        self.assertEqual(loop.pid.output_max, 10)
        loop.rounded_valve_position.set(100)
        frame._update_all_loops()
        self.assertEqual(self.daq.writes[-1], ("TDAC2", 10))
        widgets = frame._loop_widgets["flowrate"]
        widgets["mode_switch"].invoke()
        self.assertTrue(loop.is_auto)
        self.assertEqual(str(widgets["setpoint_spinbox"].cget("state")), "disabled")
        frame._pump_switch.invoke()
        self.assertEqual(self.daq.writes[-2:], [("FIO0", 1), ("TDAC2", 0)])
        self.assertFalse(loop.is_auto)
        self.assertEqual(loop.valve_position.get(), 0)
        self.assertNotIn("disabled", widgets["scale"].state())
        assert_pump_indicator(self, frame, False)
        frame._connect("T7", "ETHERNET", config.ETHERNET_ADDRESS)
        self.assertFalse(frame._switch_vars["pump"].get())
        self.assertFalse(any(pin in ("DAC0", "DAC1", "FIO2", "FIO3") for pin, _ in self.daq.writes))
        self.daq.writes.clear()
        frame._disconnect()
        self.assertEqual(self.daq.writes[-2:], [("FIO0", 1), ("TDAC2", 0)])
        self.assertEqual(self.daq.safety.safe_outputs, {})

    def test_logging_inputs_setpoint_speed_and_tuning_then_auto_sensor_failure_stops_pump(self):
        frame = self.frame
        self.start_pump()
        frame._update_all_sensors()
        frame._update_all_loops()
        frame._on_toggle_logging()
        path = frame.logger.filepath
        frame.logger.stop()
        with open(path, newline="") as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(rows[1]), 1 + len(config.LOG_COLUMNS))
        self.assertNotIn("Error", rows[1])
        frame._loop_widgets["flowrate"]["mode_switch"].invoke()
        self.daq.values["AIN1"] = float("nan")
        frame._update_all_loops()
        self.assertEqual(self.daq.safety.state, SafetyState.FAULTED)
        self.assertEqual(self.daq.writes[-2:], [("FIO0", 1), ("TDAC2", 0)])
        self.assertFalse(frame._switch_vars["pump"].get())
        self.assertFalse(frame.loops["flowrate"].is_auto)
        assert_pump_indicator(self, frame, False)

    def test_connection_configuration_failure_leaves_pump_off(self):
        original = self.daq._force_write
        def fail_configuration(pin, value):
            if pin.endswith("_RANGE"):
                raise OSError("configuration failed")
            original(pin, value)
        with patch.object(self.daq, "_force_write", side_effect=fail_configuration), \
                patch("apps.nonnewtonian.messagebox.showerror"):
            self.frame._connect("T7", "USB", "ANY")
        self.assertFalse(self.daq.is_connected)
        self.assertFalse(self.frame._main_power_on)
        self.assertEqual(self.daq.writes[-2:], [("FIO0", 1), ("TDAC2", 0)])


@unittest.skipUnless(os.environ.get("LABJACK_GUI_TESTS") == "1", "requires a window server")
class NonNewtonian2UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = gui_root()
        cls.root.tk.call("set", "scalef", 1)
        if "forest-light" not in ttk.Style(cls.root).theme_names():
            cls.root.tk.call("source", str(Path("assets/forest-light.tcl").resolve()))
        ttk.Style(cls.root).theme_use("forest-light")

    def setUp(self):
        self.errors = []
        self.root.report_callback_exception = lambda *exc: self.errors.append(exc)
        self.temp = tempfile.TemporaryDirectory()
        self.daq = FakeDAQ()
        self.daq.values.update({"AIN0": 0.0, "AIN2": 1.416, "AIN3": 1.416, "TEMPERATURE_DEVICE_K": 298.15})
        self.driver = patch.dict("sys.modules", {"labjack": SimpleNamespace(
            ljm=SimpleNamespace(tcVoltsToTemp=lambda kind, voltage, cj: cj))})
        self.driver.start()
        self.frame = config2.FrameClass(self.root, config2, self.daq)
        self.frame.logger._folder = self.temp.name
        self.frame.pack(fill="both", expand=True)

    def tearDown(self):
        self.frame.destroy()
        self.root.withdraw()
        self.root.update()
        self.driver.stop()
        self.temp.cleanup()
        self.assertEqual(self.errors, [])

    def test_canvas_and_valve_controls_fit_at_standard_sizes(self):
        frame = self.frame
        self.assertEqual(frame._output_label, "Valve")
        self.assertEqual(Path(frame.config.PID_IMAGE).name, "NonNewtonaion_2_V1.png")
        for size in ("1450x800", "1200x720"):
            self.root.geometry(size + "+0+40")
            self.root.deiconify()
            self.root.update()
            assert_diagram_alignment(self, frame)
            bounds = [frame._pid.bbox(item) for _, _, item in frame._overlays]
            for left, top, right, bottom in bounds:
                self.assertGreaterEqual(left, 0)
                self.assertGreaterEqual(top, 0)
                self.assertLessEqual(right, frame._pid.winfo_width())
                self.assertLessEqual(bottom, frame._pid.winfo_height())
            for index, a in enumerate(bounds):
                for b in bounds[index + 1:]:
                    self.assertTrue(a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])
            panel = frame._loop_widgets["flowrate"]["frame"]
            self.assertGreater(panel.winfo_rooty(), frame._pid.winfo_rooty() + frame._pid.winfo_height())

    def test_controls_and_logging_are_available_with_pump_off_after_connection(self):
        check_controls_available_with_pump_off(self)

    def test_manual_valve_survives_pump_cycles_and_auto_pauses_while_stopped(self):
        frame = self.frame
        frame._connect("T7", "USB", "ANY")
        loop = frame.loops["flowrate"]
        loop.valve_position.set(40)
        frame._update_all_loops()
        self.assertEqual(self.daq.writes[-1], ("DAC0", 2))
        assert_pump_indicator(self, frame, False)

        self.daq.writes.clear()
        frame._pump_switch.invoke()
        self.assertEqual(self.daq.writes, [("FIO0", 1)])
        self.assertEqual(loop.get_manual_voltage(), 2)
        loop.setpoint_var.set("22.5")
        frame._loop_widgets["flowrate"]["mode_switch"].invoke()
        frame._update_all_loops()
        held_command = loop.valve_position.get()

        self.daq.writes.clear()
        frame._pump_switch.invoke()
        self.assertEqual(self.daq.writes, [("FIO0", 0)])
        self.assertTrue(loop.is_auto)
        self.assertEqual(loop.valve_position.get(), held_command)
        self.assertEqual(loop.pid._integral, 0)
        assert_pump_indicator(self, frame, False)
        self.daq.writes.clear()
        with patch.object(loop.pid, "compute") as compute:
            frame._update_all_loops()
        compute.assert_not_called()
        self.assertEqual(self.daq.writes, [])
        self.assertIn("paused", frame._control_message.get())

        frame._loop_widgets["flowrate"]["mode_switch"].invoke()
        loop.valve_position.set(80)
        frame._update_all_loops()
        self.assertEqual(self.daq.writes[-1], ("DAC0", 4))
        self.daq.writes.clear()
        frame._pump_switch.invoke()
        self.assertEqual(self.daq.writes, [("FIO0", 1)])
        self.assertEqual(loop.get_manual_voltage(), 4)
        frame._disconnect()
        self.assertEqual(self.daq.writes[-2:], [("FIO0", 0), ("DAC0", 0)])
        self.assertEqual(loop.valve_position.get(), 0)

    def test_manual_valve_write_failure_with_pump_off_closes_and_disables(self):
        frame = self.frame
        frame._connect("T7", "USB", "ANY")
        frame.loops["flowrate"].valve_position.set(40)
        original_write = self.daq.write

        def fail_command(pin, value):
            if pin == "DAC0" and value:
                raise OSError("valve write failed")
            original_write(pin, value)

        with patch.object(self.daq, "write", side_effect=fail_command):
            frame._update_all_loops()
        self.assertEqual(self.daq.safety.state, SafetyState.FAULTED)
        self.assertFalse(frame._main_power_on)
        self.assertEqual(self.daq.writes[-2:], [("FIO0", 0), ("DAC0", 0)])
        self.assertIn("disabled", frame._loop_widgets["flowrate"]["manual_spinbox"].state())
        assert_pump_indicator(self, frame, False)

    def test_active_high_pump_valve_auto_fault_and_reconnect(self):
        frame = self.frame
        frame._connect("T7", "USB", "ANY")
        self.assertEqual(self.daq.writes[:2], [("FIO0", 0), ("DAC0", 0)])
        frame._pump_switch.invoke()
        assert_pump_indicator(self, frame, True)
        self.assertEqual(self.daq.writes[-1], ("FIO0", 1))
        loop = frame.loops["flowrate"]
        loop.rounded_valve_position.set(100)
        frame._update_all_loops()
        self.assertEqual(self.daq.writes[-1], ("DAC0", 5))
        frame._loop_widgets["flowrate"]["mode_switch"].invoke()
        self.assertTrue(loop.is_auto)
        self.daq.values["AIN2"] = float("nan")
        frame._update_all_loops()
        self.assertEqual(self.daq.safety.state, SafetyState.FAULTED)
        self.assertEqual(self.daq.writes[-2:], [("FIO0", 0), ("DAC0", 0)])
        self.assertFalse(loop.is_auto)
        self.assertFalse(frame._switch_vars["pump"].get())
        assert_pump_indicator(self, frame, False)
        frame._connect("T7", "USB", "ANY")
        self.assertFalse(frame._switch_vars["pump"].get())
        frame._disconnect()
        self.assertEqual(self.daq.writes[-2:], [("FIO0", 0), ("DAC0", 0)])
        self.assertEqual(self.daq.safety.safe_outputs, {})
        self.assertFalse(any(pin == "TDAC2" for pin, _ in self.daq.writes))

    def test_live_scaling_logging_and_failed_cold_junction_compensation(self):
        frame = self.frame
        frame._connect("T7", "USB", "ANY")
        frame._update_all_sensors()
        frame._update_all_loops()
        self.assertEqual(frame.sensors["fluid_temperature"].value_var.get(), "25.00")
        self.assertEqual(frame.sensors["pressure_drop"].value_var.get(), "25.00")
        self.assertEqual(frame.loops["flowrate"].measured_var.get(), "22.50")
        frame._on_toggle_logging()
        frame.logger.stop()
        with open(frame.logger.filepath, newline="") as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(len(rows), 2)
        self.assertNotIn("Error", rows[1])
        self.assertIn("Valve Command (%)", rows[0])
        original_read = self.daq.read
        def fail_cjc(pin):
            if pin == "TEMPERATURE_DEVICE_K":
                raise OSError("unavailable")
            return original_read(pin)
        with patch.object(self.daq, "read", side_effect=fail_cjc):
            frame._update_all_sensors()
        self.assertEqual(frame.sensors["fluid_temperature"].value_var.get(), "Error")
        self.assertEqual(frame.sensors["pressure_drop"].value_var.get(), "25.00")

    def test_ethernet_prompts_for_an_address_and_cancel_does_not_connect(self):
        with patch("apps.nonnewtonian.simpledialog.askstring", return_value=None), \
                patch.object(self.frame, "_connect") as connect:
            self.frame._on_connection_choice("Ethernet")
            connect.assert_not_called()
        with patch("apps.nonnewtonian.simpledialog.askstring", return_value=" 192.0.2.2 "), \
                patch.object(self.frame, "_connect") as connect:
            self.frame._on_connection_choice("Ethernet")
            connect.assert_called_once_with("T7", "ETHERNET", "192.0.2.2")

    def test_dashboard_dropdown_launches_both_units(self):
        from main import EquipmentCard

        group = AVAILABLE_CONFIGS["nonnewtonian"]
        launch = Mock()
        card = EquipmentCard(self.root, group["title"], group["subtitle"], group["image"],
                             group["units"], on_click=launch)
        try:
            self.assertIsNotNone(card._photo, "The selector apparatus image must load")
            labels = ("Unit #1 (Small Pipe)", "Unit #2 (Large Pipe)")
            self.assertEqual(tuple(card._dropdown.cget("values")), labels)
            for number, label in enumerate(labels, start=1):
                card._on_dropdown_select(label)
                card._launch_btn.invoke()
                launch.assert_called_with(f"configs.nonnewtonian_{number}")
        finally:
            card.destroy()


if __name__ == "__main__":
    unittest.main()
