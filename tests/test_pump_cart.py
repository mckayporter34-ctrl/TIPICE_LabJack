"""Unit #1 pump-cart mapping, screen fit, flow routing and fake-I/O checks."""

import math
import csv
import os
import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from apps.pump_cart import FlowParticle
from configs import AVAILABLE_CONFIGS, pump_cart
from core.safety import SafetyState
from test_airflow import FakeAirflowDAQ
from ui_test_support import gui_root


class PumpCartConfigTests(unittest.TestCase):
    def test_unit_one_development_only_and_single_main_flow_pid(self):
        group = AVAILABLE_CONFIGS["pump_cart"]
        self.assertTrue(group["active"] and group["development"])
        self.assertEqual(group["units"], [{"name": "Unit #1", "module": "configs.pump_cart"}])
        self.assertEqual(list(pump_cart.CONTROL_LOOP_CONFIGS), ["flowrate"])
        loop = pump_cart.CONTROL_LOOP_CONFIGS["flowrate"]
        self.assertEqual((loop["input_pin"], loop["output_pin"]), ("AIN3", "DAC0"))
        self.assertEqual(pump_cart.MANUAL_ANALOG_OUTPUTS["pump_speed"]["pin"], "DAC1")
        self.assertEqual(pump_cart.SYSTEM_SWITCHES[0]["pin"], "FIO2")

    def test_workbook_pressure_channels_and_zero_twenty_milliamp_scaling(self):
        expected = {"pump_dp": 4, "pipe_dp": 6, "control_valve_dp": 7, "bypass_dp": 8,
                    "tee_dp": 9, "u_dp": 10, "el_dp": 11, "globe_valve_dp": 12, "ball_valve_dp": 13}
        for key, channel in expected.items():
            sensor = pump_cart.SENSOR_CONFIGS[key]
            self.assertEqual(sensor["pin"], f"AIN{channel}")
            self.assertEqual(sensor["unit"], "psid")
            if key != "pump_dp":
                for voltage, pressure in ((0, 0), (1.180, 25), (2.360, 50)):
                    self.assertAlmostEqual(sensor["calibration"](voltage), pressure)

    def test_missing_scaling_cannot_be_misreported_as_engineering_units(self):
        for key in pump_cart.pending_inputs() - {"flowrate", "fluid_temperature"}:
            with self.subTest(key=key), self.assertRaises(ValueError):
                pump_cart.SENSOR_CONFIGS[key]["calibration"](1.0)
        with self.assertRaises(ValueError):
            pump_cart._main_flow(1.0)
        with patch.object(pump_cart, "MAIN_FLOW_SIGNAL_V", (0.472, 2.360)):
            for v, expected in ((0.472, 0.79), (1.416, 39.895), (2.360, 79)):
                self.assertAlmostEqual(pump_cart._main_flow(v), expected)
        with patch.object(pump_cart, "BYPASS_PULSES_PER_GALLON", 600):
            self.assertAlmostEqual(pump_cart._bypass_flow(0.01), 10)
            for bad in (0, -1, float("nan")):
                with self.assertRaises(ValueError):
                    pump_cart._bypass_flow(bad)

    def test_readout_coverage_and_open_animation_paths_follow_the_branches(self):
        readouts = {key: (card, tap) for key, _, card, tap in pump_cart.DIAGRAM_READOUTS}
        self.assertEqual(set(readouts), set(pump_cart.PRESSURE_CHANNELS) |
                         {"valve", "flowrate", "bypass_flowrate", "fluid_temperature"})
        self.assertEqual(readouts["fluid_temperature"][1], (378, 170))
        self.assertEqual(readouts["bypass_flowrate"][1], (311, 273))
        for name, path in pump_cart.FLOW_PATHS.items():
            particle = FlowParticle(Mock(), path, "blue", 0)
            self.assertEqual(particle.at(0), path[0])
            self.assertEqual(particle.at(particle.length), path[0])
            # Every sample is on one of the explicitly drawn pipe segments.
            for i in range(100):
                p = particle.at(i / 100 * particle.length)
                self.assertTrue(any(abs(math.dist(a, p) + math.dist(p, b) - math.dist(a, b)) < 1e-7
                                    for a, b in zip(path, path[1:])), (name, p))

    def test_type_k_uses_confirmed_ain0_and_amplifier_cold_junction_compensation(self):
        from types import SimpleNamespace
        convert = Mock(return_value=373.15)
        self.assertEqual(pump_cart.SENSOR_CONFIGS["fluid_temperature"]["pin"], "AIN0")
        self.assertEqual(pump_cart.AIN_CONFIGS["AIN0"]["NEGATIVE_CH"], 199)
        with patch.dict("sys.modules", {"labjack": SimpleNamespace(ljm=SimpleNamespace(tcVoltsToTemp=convert))}), \
                patch.object(pump_cart, "_cj_temp_c", [25.0]):
            self.assertAlmostEqual(pump_cart._temperature(1.25 + 51 * 0.003), 100)
        kind, voltage, cj = convert.call_args.args
        self.assertEqual(kind, 6004)
        self.assertAlmostEqual(voltage, 0.003)
        self.assertAlmostEqual(cj, 298.15)


class PumpDAQ(FakeAirflowDAQ):
    def read(self, pin):
        self.reads.append(pin)
        if pin == "DIO0_EF_READ_A_F":
            return 0.01
        return 1.416


@unittest.skipUnless(os.environ.get("LABJACK_GUI_TESTS") == "1", "requires a window server")
class PumpCartUITests(unittest.TestCase):
    def setUp(self):
        self.root = gui_root()
        self.root.tk.call("set", "scalef", 1)
        for mode in ("light", "dark"):
            if f"forest-{mode}" not in ttk.Style(self.root).theme_names():
                self.root.tk.call("source", str(Path(f"assets/forest-{mode}.tcl").resolve()))
        ttk.Style(self.root).theme_use("forest-light")
        self.errors = []
        self.root.report_callback_exception = lambda *e: self.errors.append(e)
        self.temp = tempfile.TemporaryDirectory()
        self.daq = PumpDAQ()
        self.frame = pump_cart.FrameClass(self.root, pump_cart, self.daq)
        self.frame.logger._folder = self.temp.name
        self.frame.pack(fill="both", expand=True)

    def tearDown(self):
        self.frame.destroy()
        self.root.withdraw()
        self.root.update()
        self.temp.cleanup()
        self.assertEqual(self.errors, [])

    def test_complete_panel_and_readouts_fit_without_scrolling(self):
        for theme in ("forest-light", "forest-dark", "clam"):
            ttk.Style(self.root).theme_use(theme)
            for size in ("1366x768", "1320x700"):
                with self.subTest(theme=theme, size=size):
                    self.root.geometry(size + "+0+40")
                    self.root.deiconify()
                    self.root.update()
                    # No scrollbars anywhere on this screen.
                    def widgets(parent):
                        for child in parent.winfo_children():
                            yield child
                            yield from widgets(child)
                    self.assertFalse(any(isinstance(w, ttk.Scrollbar) for w in widgets(self.frame)))
                    for w in widgets(self.frame):
                        if isinstance(w, (ttk.Entry, ttk.Spinbox, ttk.Checkbutton, ttk.Menubutton)):
                            self.assertTrue(w.winfo_ismapped())
                            self.assertGreaterEqual(w.winfo_rootx(), self.frame.winfo_rootx())
                            self.assertGreaterEqual(w.winfo_rooty(), self.frame.winfo_rooty())
                            self.assertLessEqual(w.winfo_rootx() + w.winfo_width(),
                                                 self.frame.winfo_rootx() + self.frame.winfo_width())
                            self.assertLessEqual(w.winfo_rooty() + w.winfo_height(),
                                                 self.frame.winfo_rooty() + self.frame.winfo_height())
                            self.assertGreaterEqual(w.winfo_width(), w.winfo_reqwidth(), str(w))
                    log = self.frame._logging_panel
                    flow = self.frame._loop_widgets["flowrate"]["frame"]
                    self.assertEqual(log.master, self.frame._sidebar)
                    self.assertGreaterEqual(log.winfo_y(), flow.winfo_y() + flow.winfo_height())
                    self.assertEqual(self.frame._loop_widgets["flowrate"]["mode_switch"].cget("style"), "Switch")
                    bounds = [self.frame._pid.bbox(r["item"]) for r in self.frame._readouts.values()]
                    for readout in self.frame._readouts.values():
                        self.assertEqual(str(readout["entry"].cget("state")), "readonly")
                        self.assertEqual(readout["entry"].cget("style"), "")
                        self.assertEqual(str(readout["entry"].cget("textvariable")), str(readout["variable"]))
                        self.assertGreaterEqual(float(self.frame._pid.itemcget(readout["line"], "width")), 2)
                    elbow = self.frame._readouts["el_dp"]
                    self.assertEqual(tuple(self.frame._pid.coords(elbow["line"])[:2]),
                                     self.frame._point((8, 296)))
                    for a in bounds:
                        self.assertGreaterEqual(min(a[:2]), 0)
                        self.assertLessEqual(a[2], self.frame._pid.winfo_width())
                        self.assertLessEqual(a[3], self.frame._pid.winfo_height())
                    for i, a in enumerate(bounds):
                        for b in bounds[i+1:]:
                            self.assertTrue(a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (a, b))
        self.assertEqual(self.daq.reads, [])

    def test_connection_manual_speed_valve_bounds_and_shutdown(self):
        f = self.frame
        f._connect("T7", "USB", "ANY")
        self.assertEqual(self.daq.safety.safe_outputs, {"FIO2": 0, "DAC0": 0, "DAC1": 0})
        self.assertEqual(self.daq.writes[:3], [("FIO2", 0), ("DAC0", 0), ("DAC1", 0)])
        self.assertFalse(f._switch_vars["pump"].get())
        f._pump_speed_var.set("50")
        f._update_manual_analog_outputs()
        self.assertEqual(self.daq.writes[-1], ("DAC1", 0))
        f._pump_switch.invoke()
        f._pump_speed_var.set("150")
        f._update_manual_analog_outputs()
        self.assertEqual(self.daq.writes[-1], ("DAC1", 5))
        f.loops["flowrate"].rounded_valve_position.set(200)
        f._update_all_loops()
        self.assertEqual(self.daq.writes[-1], ("DAC0", 5))
        self.assertEqual(f.loops["flowrate"].measured_var.get(), "TODO")
        f._pump_switch.invoke()
        self.assertEqual(self.daq.writes[-1], ("DAC1", 0))
        f._disconnect()
        self.assertEqual(self.daq.safety.state, SafetyState.DISCONNECTED)
        self.assertEqual(dict(self.daq.writes[-3:]), {"FIO2": 0, "DAC0": 0, "DAC1": 0})
        self.assertEqual(f.loops["flowrate"].measured_var.get(), "---")
        self.assertEqual(f._pump_speed_var.get(), "0")

    def test_main_flow_pid_bypass_is_monitor_only_and_animation_stops(self):
        f = self.frame
        with patch.object(pump_cart, "MAIN_FLOW_SIGNAL_V", (0.472, 2.360)), \
                patch.object(pump_cart, "BYPASS_PULSES_PER_GALLON", 600):
            f._connect("T7", "USB", "ANY")
            f._pump_switch.invoke()
            f._update_all_sensors()
            f.loops["flowrate"].setpoint_var.set("45")
            f._loop_widgets["flowrate"]["mode_switch"].invoke()
            with patch.object(f.loops["flowrate"].pid, "compute", return_value=2.5) as compute:
                f._update_all_loops()
            self.assertAlmostEqual(compute.call_args.args[1], 39.895)
            self.assertEqual(f.sensors["bypass_flowrate"].value_var.get(), "10.00")
            self.assertEqual(self.daq.writes[-1], ("DAC0", 2.5))
            f.after_cancel(f._animation_id)
            f._animate()
            for particles in f._particles.values():
                self.assertTrue(all(f._pid.itemcget(p.item, "state") == "normal" for p in particles))
            f._pump_switch.invoke()
            self.assertTrue(all(f._pid.itemcget(p.item, "state") == "hidden"
                                for ps in f._particles.values() for p in ps))
            self.daq.read = Mock(side_effect=OSError("sensor unplugged"))
            f._pump_switch.invoke()
            f._update_all_loops()
            self.assertEqual(self.daq.safety.state, SafetyState.FAULTED)
            self.assertFalse(f._main_power_on)
            self.assertEqual(dict(self.daq.writes[-3:]), {"FIO2": 0, "DAC0": 0, "DAC1": 0})

    def test_csv_records_main_and_bypass_separately_with_manual_speed(self):
        f = self.frame
        f._connect("T7", "USB", "ANY")
        f.loops["flowrate"].set_measured(40)
        f.sensors["bypass_flowrate"].set_value(10)
        f._pump_speed_var.set("60")
        f._on_toggle_logging()
        f.logger.stop()
        with open(f.logger.filepath, newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 1)
        self.assertEqual(float(rows[0]["Main flow (GPM)"]), 40)
        self.assertEqual(float(rows[0]["Bypass flow (GPM)"]), 10)
        self.assertEqual(float(rows[0]["Pump speed command (%)"]), 60)
        for key in pump_cart.PRESSURE_CHANNELS:
            self.assertIn(f"{pump_cart.SENSOR_CONFIGS[key]['label']} (psid)", rows[0])


if __name__ == "__main__":
    unittest.main()
