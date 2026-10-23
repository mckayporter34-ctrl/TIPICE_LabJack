"""Non-Newtonian #1 control, lifecycle and layout checks using fake hardware."""

import csv
import importlib
import os
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from apps.nonnewtonian import NonNewtonianFrame
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
            _polling=True, _main_power_on=True, loops={"flowrate": self.loop}, daq=self.daq,
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

    def test_type_k_conversion_removes_confirmed_gain_offset_and_uses_cjc(self):
        converter = Mock(return_value=373.15)
        with patch.dict("sys.modules", {"labjack": SimpleNamespace(ljm=SimpleNamespace(tcVoltsToTemp=converter))}), \
                patch.object(config2, "_cj_temp_c", [25.0]):
            self.assertAlmostEqual(config2._temperature_c(1.25 + 51 * 0.003), 100)
        kind, voltage, cj = converter.call_args.args
        self.assertEqual(kind, 6004)
        self.assertAlmostEqual(voltage, 0.003)
        self.assertAlmostEqual(cj, 298.15)
        with patch.dict("sys.modules", {"labjack": SimpleNamespace(ljm=SimpleNamespace(tcVoltsToTemp=converter))}), \
                patch.object(config2, "_cj_temp_c", [float("nan")]):
            with self.assertRaises(ValueError):
                config2._temperature_c(1.25)

    def test_five_volt_valve_control_and_auto_action(self):
        harness = NonNewtonianControlTests()
        harness.setUp()
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

    def test_active_low_start_stop_auto_states_reconnect_and_shutdown(self):
        frame = self.frame
        self.daq.safety.register_safe_output("DAC1", 5)  # Another apparatus's stale map.
        self.start_pump()
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
        self.assertIn("disabled", widgets["scale"].state())
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
        self.daq.values.update({"AIN0": 1.25, "AIN2": 1.416, "AIN3": 1.416, "TEMPERATURE_DEVICE_K": 298.15})
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

    def test_active_high_pump_valve_auto_fault_and_reconnect(self):
        frame = self.frame
        frame._connect("T7", "USB", "ANY")
        self.assertEqual(self.daq.writes[:2], [("FIO0", 0), ("DAC0", 0)])
        frame._pump_switch.invoke()
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
            self.assertEqual(tuple(card._dropdown.cget("values")), ("Unit #1", "Unit #2"))
            for number in (1, 2):
                card._on_dropdown_select(f"Unit #{number}")
                card._launch_btn.invoke()
                launch.assert_called_with(f"configs.nonnewtonian_{number}")
        finally:
            card.destroy()


if __name__ == "__main__":
    unittest.main()
