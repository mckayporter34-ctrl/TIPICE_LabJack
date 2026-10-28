"""Optional temperature smoothing, using controlled elapsed sample times."""

import math
import tkinter as tk
import unittest
from unittest.mock import patch

from core.sensor import Sensor


class SensorFilterTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tcl()

    def sensor(self, tau=5.0):
        return Sensor("temperature", "Temperature", "°C", "AIN0", float,
                      value_var=tk.StringVar(self.root), filter_time_constant_s=tau)

    def test_irregular_intervals_follow_five_second_step_response(self):
        sensor = self.sensor()
        with patch("core.sensor.monotonic", side_effect=[100.0, 100.5, 105.0, 115.0]):
            sensor.set_value(20.0)
            self.assertEqual(sensor.value_var.get(), "20.00")
            for elapsed in (0.5, 5.0, 15.0):
                sensor.set_value(30.0)
                expected = 30.0 - 10.0 * math.exp(-elapsed / 5.0)
                self.assertEqual(sensor.value_var.get(), f"{expected:.2f}")
                self.assertEqual(sensor.get_raw_value(), 30.0)

    def test_filter_keeps_precision_between_display_updates(self):
        sensor = self.sensor()
        with patch("core.sensor.monotonic", side_effect=[0.0, 0.5, 1.0]):
            sensor.set_value(23.0)
            sensor.set_value(23.03)
            sensor.set_value(23.03)
        self.assertEqual(sensor.value_var.get(), "23.01")

    def test_error_and_reset_clear_raw_and_filtered_history(self):
        sensor = self.sensor()
        with patch("core.sensor.monotonic", side_effect=[0.0, 1.0, 2.0, 3.0]):
            sensor.set_value(20)
            sensor.set_value(30)
            sensor.set_error()
            self.assertEqual(sensor.value_var.get(), "Error")
            with self.assertRaises(ValueError):
                sensor.get_raw_value()
            sensor.set_value(40)
            self.assertEqual(sensor.value_var.get(), "40.00")
            sensor.reset()
            self.assertEqual(sensor.value_var.get(), "---")
            with self.assertRaises(ValueError):
                sensor.get_raw_value()
            sensor.set_value(10)
            self.assertEqual(sensor.value_var.get(), "10.00")

    def test_default_is_unfiltered_and_rejects_invalid_samples(self):
        sensor = self.sensor(tau=0)
        with patch("core.sensor.monotonic") as clock:
            for value in (20, 30, 10):
                sensor.set_value(value)
                self.assertEqual(sensor.value_var.get(), f"{value:.2f}")
                self.assertEqual(sensor.get_raw_value(), value)
            clock.assert_not_called()
        for value in (math.nan, math.inf, -math.inf, "invalid"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                sensor.set_value(value)

    def test_invalid_time_constants_are_rejected(self):
        for tau in (-1, math.nan, math.inf):
            with self.subTest(tau=tau), self.assertRaises(ValueError):
                self.sensor(tau)


if __name__ == "__main__":
    unittest.main()
