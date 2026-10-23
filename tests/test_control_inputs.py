import math
import tkinter as tk
import unittest

from core.control_loop import ControlLoop
from core.pid_controller import PIDController
from core.sensor import Sensor


class ControlInputTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tcl()
        self.loop = ControlLoop(
            "flow", "Flow", "L/min", "AIN0", "DAC0", float, 0, 100, PIDController(),
            setpoint_var=tk.StringVar(self.root), measured_var=tk.StringVar(self.root),
            valve_position=tk.DoubleVar(self.root), rounded_valve_position=tk.IntVar(self.root),
            Kc_var=tk.StringVar(self.root), Ti_var=tk.StringVar(self.root),
            Td_var=tk.StringVar(self.root))

    def test_bad_setpoint_and_measurement_are_not_control_inputs(self):
        for bad in ("x", "", "nan", "inf", "1e999"):
            with self.subTest(value=bad):
                self.loop.setpoint_var.set(bad)
                self.loop.measured_var.set(bad)
                self.assertIsNone(self.loop.get_setpoint())
                self.assertIsNone(self.loop.get_measured())
        self.loop.setpoint_var.set("1.5")
        self.assertEqual(self.loop.get_setpoint(), 1.5)

    def test_invalid_tuning_never_partially_updates_controller(self):
        for field in ("Kc_var", "Ti_var", "Td_var"):
            for bad in ("x", "", "nan", "inf"):
                with self.subTest(field=field, value=bad):
                    self.loop.Kc_var.set("2")
                    self.loop.Ti_var.set("3")
                    self.loop.Td_var.set("4")
                    getattr(self.loop, field).set(bad)
                    with self.assertRaises(ValueError):
                        self.loop.sync_tuning_to_pid()
                    self.assertEqual((self.loop.pid.Kc, self.loop.pid.Ti, self.loop.pid.Td),
                                     (1, 1, 0))
        self.loop.Td_var.set("0")
        self.loop.sync_tuning_to_pid()
        self.assertEqual((self.loop.pid.Kc, self.loop.pid.Ti, self.loop.pid.Td), (2, 3, 0))

    def test_nonfinite_sensor_readings_rejected(self):
        sensor = Sensor("temp", "Temperature", "C", "AIN1", float,
                        value_var=tk.StringVar(self.root))
        for bad in (math.nan, math.inf, -math.inf, "broken"):
            with self.assertRaises(ValueError):
                sensor.set_value(bad)
            with self.assertRaises(ValueError):
                self.loop.set_measured(bad)
        sensor.set_value(25)
        self.assertEqual(sensor.value_var.get(), "25.00")


if __name__ == "__main__":
    unittest.main()
