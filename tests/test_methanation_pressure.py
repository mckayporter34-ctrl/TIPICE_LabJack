"""Exercise both catalytic configurations with Tcl variables and fake I/O."""

import importlib
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from apps.catalytic_methanation import CatalyticMethanationRedesignFrame, _PressurePID
from core.base_app import DT_MINUTES
from core.pid_controller import PIDController


class FakeDAQ:
    is_connected = True

    def __init__(self):
        self.writes = []
        self.value = 1.5
        self.fail_read = False
        self.fail_pin = None

    def read(self, pin):
        if self.fail_read and pin == "AIN2":
            raise OSError("pressure sensor unavailable")
        return self.value

    def write(self, pin, value):
        if pin == self.fail_pin:
            raise OSError("selector write failed")
        self.writes.append((pin, value))


class MethanationPressureTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tcl()
        self.default_root = tk._default_root
        tk._default_root = self.root

    def tearDown(self):
        tk._default_root = self.default_root

    def frame(self, unit):
        # No window or LabJack is constructed. Use the production loop builder
        # and update callback, with its recurring scheduler replaced by a mock.
        frame = object.__new__(CatalyticMethanationRedesignFrame)
        frame.config = importlib.import_module("configs.catalytic_methanation_" + str(unit))
        frame.daq = FakeDAQ()
        frame._main_power_on = True
        frame._polling = True
        frame._gc_stream_var = tk.StringVar(self.root, value="Feed")
        frame._pressure_gate_var = tk.BooleanVar(self.root, value=False)
        frame._pressure_stream = None
        frame._switch_vars = {
            "pressure_enabled": frame._pressure_gate_var,
            "heater_power": tk.BooleanVar(self.root, value=False),
        }
        frame.loops = frame._build_control_loops()
        frame.loops["pressure"].is_auto = True
        frame.after = Mock()
        return frame

    def select(self, frame, stream):
        frame._gc_stream_var.set(stream)
        frame._on_gc_stream_change()

    def pressure_writes(self, frame):
        return [voltage for pin, voltage in frame.daq.writes if pin == "DAC0"]

    def test_feed_clears_windup_and_never_computes_or_writes_auto_pressure(self):
        for unit in (1, 2):
            with self.subTest(unit=unit):
                frame = self.frame(unit)
                pid = frame.loops["pressure"].pid
                pid._integral = -100
                pid._e_prev = 50
                pid.last_output = 2.37
                frame.loops["pressure"].set_valve_display(2.37)
                self.select(frame, "Feed")
                self.assertEqual(frame.daq.writes, [("FIO5", 5), ("FIO6", 5)])
                with patch.object(pid, "compute", wraps=pid.compute) as compute:
                    for _ in range(200):
                        frame._update_all_loops()
                    compute.assert_not_called()
                self.assertEqual((pid._integral, pid._e_prev), (0, 0))
                self.assertEqual(pid.last_output, 2.37)
                self.assertEqual(self.pressure_writes(frame), [])
                self.assertNotEqual(frame.loops["pressure"].measured_var.get(), "---")

    def test_exhaust_first_sample_holds_output_then_pressure_regulates(self):
        for unit in (1, 2):
            with self.subTest(unit=unit):
                frame = self.frame(unit)
                loop = frame.loops["pressure"]
                loop.pid.last_output = 2.37
                loop.pid._integral = -1000
                self.select(frame, "Feed")
                self.select(frame, "Exhaust")
                self.assertEqual(frame.daq.writes[-2:], [("FIO5", 0), ("FIO6", 0)])
                frame.daq.value = 1.8  # Fresh reading differs from the Feed path.
                loop.Kc_var.set(-0.7)  # Apply tuning at the first resumed sample.
                loop.Td_var.set(0.2)
                frame._update_all_loops()
                self.assertEqual(self.pressure_writes(frame), [2.37])
                error = loop.get_setpoint() - loop.get_measured()
                self.assertAlmostEqual(loop.pid._integral, 2.37 - (-0.7 * error))
                self.assertEqual(loop.pid._e_prev, error)
                frame._update_all_loops()
                expected = max(0, min(5, 2.37 + (-0.7 / 0.1) * error * DT_MINUTES))
                self.assertAlmostEqual(self.pressure_writes(frame)[-1], expected)
                self.assertNotEqual(expected, 2.37)

    def test_invalid_pressure_and_tuning_delay_initialization_until_valid(self):
        frame = self.frame(1)
        loop = frame.loops["pressure"]
        loop.pid.last_output = 1.75
        self.select(frame, "Exhaust")
        frame.daq.fail_read = True
        frame._update_all_loops()
        self.assertEqual(self.pressure_writes(frame), [])
        self.assertEqual(loop.pid._resume_output, 1.75)
        frame.daq.fail_read = False
        loop.Kc_var.set("bad")
        with patch("builtins.print"):
            frame._update_all_loops()
        self.assertEqual(self.pressure_writes(frame), [])
        self.assertEqual(loop.pid._resume_output, 1.75)
        loop.Kc_var.set(-0.5)
        loop.setpoint_var.set(20)
        frame._update_all_loops()
        self.assertEqual(self.pressure_writes(frame), [1.75])

    def test_failed_selector_write_keeps_auto_suspended_until_retry(self):
        for failing_pin in ("FIO5", "FIO6"):
            with self.subTest(pin=failing_pin):
                frame = self.frame(2)
                frame.daq.fail_pin = failing_pin
                with patch("builtins.print"):
                    self.select(frame, "Exhaust")
                frame._update_all_loops()
                self.assertFalse(frame._pressure_gate_var.get())
                self.assertEqual(self.pressure_writes(frame), [])
                frame.daq.fail_pin = None
                self.select(frame, "Exhaust")
                frame._update_all_loops()
                self.assertEqual(self.pressure_writes(frame), [0])

    def test_reselecting_exhaust_does_not_reinitialize_running_pid(self):
        frame = self.frame(1)
        self.select(frame, "Exhaust")
        frame._update_all_loops()
        frame._update_all_loops()
        pid = frame.loops["pressure"].pid
        state = (pid._integral, pid._e_prev)
        self.select(frame, "Exhaust")
        self.assertEqual((pid._integral, pid._e_prev), state)
        self.assertIsNone(pid._resume_output)

    def test_pressure_manual_control_is_preserved_in_both_streams(self):
        frame = self.frame(2)
        loop = frame.loops["pressure"]
        loop.is_auto = False
        loop.set_valve_display(1.5)
        for stream in ("Feed", "Exhaust"):
            self.select(frame, stream)
            with patch.object(loop.pid, "compute") as compute:
                frame._update_all_loops()
                compute.assert_not_called()
            self.assertFalse(loop.is_auto)
            self.assertEqual(self.pressure_writes(frame)[-1], 1.5)
        # The existing mode callback calls initialize before AUTO takes over.
        loop.pid.initialize(loop.get_manual_voltage())
        loop.is_auto = True
        frame._update_all_loops()
        self.assertEqual(self.pressure_writes(frame)[-1], 1.5)

    def test_power_off_and_disconnect_suspend_computation(self):
        for disconnected in (False, True):
            with self.subTest(disconnected=disconnected):
                frame = self.frame(1)
                self.select(frame, "Exhaust")
                frame._update_all_loops()
                frame.daq.writes.clear()
                if disconnected:
                    frame.daq.is_connected = False
                else:
                    frame._main_power_on = False
                with patch.object(frame.loops["pressure"].pid, "compute") as compute:
                    frame._update_all_loops()
                    compute.assert_not_called()
                self.assertEqual(self.pressure_writes(frame), [])
                self.assertEqual(frame.loops["pressure"].pid._integral, 0)

    def test_temperature_pid_and_heater_gate_are_unchanged(self):
        frame = self.frame(1)
        temperature = frame.loops["temperature"]
        self.assertIs(type(temperature.pid), PIDController)
        temperature.is_auto = True
        frame._switch_vars["heater_power"].set(True)
        with patch.object(temperature.pid, "compute", return_value=0.8) as compute:
            for stream in ("Feed", "Exhaust"):
                self.select(frame, stream)
                frame._update_all_loops()
            self.assertEqual(compute.call_count, 2)
            self.assertEqual([v for pin, v in frame.daq.writes if pin == "DAC1"], [0.8, 0.8])
            frame._switch_vars["heater_power"].set(False)
            frame._update_all_loops()
            self.assertEqual(compute.call_count, 2)

    def test_stopped_polling_never_schedules_or_controls(self):
        frame = self.frame(1)
        frame._polling = False
        frame._update_all_loops()
        self.assertEqual(frame.daq.writes, [])
        frame.after.assert_not_called()

    def test_transfer_at_limits_and_without_integral_has_no_first_sample_kick(self):
        for voltage in (0, 2.37, 5):
            for Ti in (0, 0.1):
                with self.subTest(voltage=voltage, Ti=Ti):
                    pid = _PressurePID(Kc=-0.5, Ti=Ti, Td=0.2)
                    pid._integral = -100
                    pid.initialize(voltage)
                    self.assertEqual(pid.compute(18.4, 22, DT_MINUTES), voltage)
                    self.assertEqual(pid._e_prev, 18.4 - 22)


if __name__ == "__main__":
    unittest.main()
