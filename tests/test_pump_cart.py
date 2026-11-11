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

from PIL import Image

from apps.pump_cart import FlowDash, PumpCartFrame
from configs import AVAILABLE_CONFIGS, pump_cart
from core.sensor import Sensor
from core.labjack_interface import LabJackInterface
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

    def test_pressure_channels_and_scaling(self):
        self.assertNotIn("pump_dp", pump_cart.pending_inputs())
        expected = {"pump_dp": 7, "pipe_dp": 6, "bypass_dp": 8,
                    "tee_dp": 9, "u_dp": 10, "el_dp": 11, "globe_valve_dp": 12, "ball_valve_dp": 13}
        self.assertEqual(set(pump_cart.PRESSURE_CHANNELS), set(expected))
        for key, channel in expected.items():
            sensor = pump_cart.SENSOR_CONFIGS[key]
            self.assertEqual(sensor["pin"], f"AIN{channel}")
            self.assertEqual(sensor["unit"], "psi")
            for voltage, pressure in ((0.47082, 0), (0.472, 0), (1.416, 25), (2.360, 50)):
                with self.subTest(key=key, voltage=voltage):
                    self.assertAlmostEqual(sensor["calibration"](voltage), pressure)
            with self.subTest(key=key), self.assertRaises(ValueError):
                sensor["calibration"](0.0)

    def test_missing_scaling_cannot_be_misreported_as_engineering_units(self):
        for key in pump_cart.pending_inputs() - {"flowrate", "fluid_temperature"}:
            with self.subTest(key=key), self.assertRaises(ValueError):
                pump_cart.SENSOR_CONFIGS[key]["calibration"](1.0)
        with patch.object(pump_cart, "MAIN_FLOW_SIGNAL_V", None), self.assertRaises(ValueError):
            pump_cart._main_flow(1.0)
        with patch.object(pump_cart, "BYPASS_PULSES_PER_GALLON", 600):
            self.assertAlmostEqual(pump_cart._bypass_flow(0.01), 10)
            for bad in (-1, float("nan")):
                with self.assertRaises(ValueError):
                    pump_cart._bypass_flow(bad)

    def test_main_flow_scales_four_to_twenty_milliamps(self):
        self.assertNotIn("flowrate", pump_cart.pending_inputs())
        calibrate = pump_cart.CONTROL_LOOP_CONFIGS["flowrate"]["calibration"]
        for voltage, gpm in ((0.472, 0.79), (1.416, 39.895), (2.360, 79.0)):
            with self.subTest(voltage=voltage):
                self.assertAlmostEqual(calibrate(voltage), gpm)
        with self.assertRaises(ValueError):
            calibrate(0.0)

    def test_pump_speed_feedback_scales_calibrated_current_range(self):
        self.assertNotIn("pump_speed_rpm", pump_cart.pending_inputs())
        sensor = pump_cart.SENSOR_CONFIGS["pump_speed_rpm"]
        self.assertEqual(sensor["pin"], "AIN2")
        calibrate = sensor["calibration"]
        for voltage, rpm in ((0.472, 0), (0.51212, 0), (1.41364, 2195), (2.31516, 4390)):
            with self.subTest(voltage=voltage):
                self.assertAlmostEqual(calibrate(voltage), rpm)
        with self.assertRaises(ValueError):
            calibrate(0)  # Open current loop must show a read error.

    def test_motor_power_scales_measured_millivolts_to_watts_on_ain4(self):
        sensor = pump_cart.SENSOR_CONFIGS["pump_motor_power"]
        self.assertEqual(sensor["pin"], "AIN4")
        self.assertEqual(sensor["unit"], "W")
        self.assertNotIn("pump_motor_power", pump_cart.pending_inputs())
        calibrate = sensor["calibration"]
        for voltage, watts in ((0.008, 0), (0.171, 750), (0.334, 1500),
                               (0.660, 3000), (0.0, 0)):
            with self.subTest(voltage=voltage):
                self.assertAlmostEqual(calibrate(voltage), watts)
        for voltage in (math.nan, math.inf, -math.inf, "invalid"):
            with self.subTest(voltage=voltage), self.assertRaises(ValueError):
                calibrate(voltage)
        with patch.object(pump_cart, "PUMP_POWER_SIGNAL_V", None):
            self.assertIn("pump_motor_power", pump_cart.pending_inputs())
            with self.assertRaises(ValueError):
                calibrate(0.171)

    def test_fmg94_manual_k_factor_and_period_scaling(self):
        self.assertEqual(pump_cart.BYPASS_PULSES_PER_GALLON, 750)
        self.assertNotIn("bypass_flowrate", pump_cart.pending_inputs())
        self.assertEqual(pump_cart._bypass_flow(0), 0)
        for flow in (0.52, 1.3, 10, 26.4, 31.7):
            with self.subTest(flow=flow):
                self.assertAlmostEqual(pump_cart._bypass_flow(60 / (750 * flow)), flow)
        for factor in (None, 0, -1, math.nan, math.inf):
            with self.subTest(factor=factor), patch.object(pump_cart, "BYPASS_PULSES_PER_GALLON", factor):
                with self.assertRaises(ValueError):
                    pump_cart._bypass_flow(0.008)

    def test_readout_coverage_and_open_animation_paths_follow_the_branches(self):
        readouts = {key: (card, tap) for key, _, card, tap, _ in pump_cart.DIAGRAM_READOUTS}
        self.assertNotIn("control_valve_dp", pump_cart.SENSOR_CONFIGS)
        self.assertNotIn("control_valve_dp", readouts)
        self.assertNotIn("Control valve ΔP (psi)", pump_cart.LOG_COLUMNS)
        self.assertEqual(set(readouts), set(pump_cart.PRESSURE_CHANNELS) |
                         {"valve", "flowrate", "bypass_flowrate", "fluid_temperature"})
        self.assertEqual(readouts["fluid_temperature"][1], (441, 190))
        self.assertEqual(readouts["bypass_flowrate"][1], (395, 319))
        self.assertEqual(pump_cart.FLOW_PATHS["supply"][-1], pump_cart.FLOW_PATHS["pipe"][0])
        self.assertEqual(pump_cart.FLOW_PATHS["supply"][-1], pump_cart.FLOW_PATHS["bypass"][0])
        self.assertEqual(pump_cart.FLOW_PATHS["pipe"][-1], pump_cart.FLOW_PATHS["return"][0])
        self.assertEqual(pump_cart.FLOW_PATHS["bypass"][-1], pump_cart.FLOW_PATHS["return"][0])
        for name, path in pump_cart.FLOW_PATHS.items():
            dash = FlowDash(Mock(), path, "blue", 0)
            self.assertEqual(dash.at(0), path[0])
            self.assertEqual(dash.at(dash.length), path[0])
            # Every sample is on one of the explicitly drawn pipe segments.
            for i in range(100):
                p = dash.at(i / 100 * dash.length)
                self.assertTrue(any(abs(math.dist(a, p) + math.dist(p, b) - math.dist(a, b)) < 1e-7
                                    for a, b in zip(path, path[1:])), (name, p))

    def test_overlay_taps_and_animation_align_with_the_exported_drawing(self):
        # Check against the actual artwork, so an export-size change cannot
        # silently leave every overlay and animation on the old pipe locations.
        with Image.open(pump_cart.PID_IMAGE) as source:
            drawing = source.convert("L")
        radius = math.ceil(3 * max(drawing.width / pump_cart.DIAGRAM_SIZE[0],
                                   drawing.height / pump_cart.DIAGRAM_SIZE[1]))

        def on_drawing(point):
            x, y = (round(point[0] * drawing.width / pump_cart.DIAGRAM_SIZE[0]),
                    round(point[1] * drawing.height / pump_cart.DIAGRAM_SIZE[1]))
            return any(drawing.getpixel((px, py)) < 160
                       for px in range(max(0, x - radius), min(drawing.width, x + radius + 1))
                       for py in range(max(0, y - radius), min(drawing.height, y + radius + 1)))

        for key, _, _, tap, _ in pump_cart.DIAGRAM_READOUTS:
            self.assertTrue(on_drawing(tap), (key, tap))
        for name, path in pump_cart.FLOW_PATHS.items():
            # Inside the pump, dashes travel through its open symbol.
            if name == "supply":
                path = path[4:]
            for a, b in zip(path, path[1:]):
                for step in range(21):
                    point = tuple(start + (end - start) * step / 20 for start, end in zip(a, b))
                    self.assertTrue(on_drawing(point), (name, point))

    def test_flow_dashes_follow_corners_and_clip_before_wrapping(self):
        dash = FlowDash(Mock(), ((0, 0), (20, 0), (20, 20)), "blue", 0)
        dash.distance = 15
        self.assertEqual(dash.points(), [(15, 0), (20, 0), (20, 9)])
        dash.distance = 35
        self.assertEqual(dash.points(), [(20, 15), (20, 20)])
        dash.distance = 40
        self.assertEqual(dash.points(), [(0, 0), (14, 0)])

    def test_type_k_reads_ain1_through_inamp_with_cold_junction_compensation(self):
        from types import SimpleNamespace
        convert = Mock(return_value=373.15)
        self.assertEqual(pump_cart.SENSOR_CONFIGS["fluid_temperature"]["pin"], "AIN1")
        self.assertEqual(pump_cart.AIN_CONFIGS["AIN1"],
                         {"NEGATIVE_CH": 199, "RANGE": 10.0, "RESOLUTION_INDEX": 8})
        self.assertNotIn("fluid_temperature", pump_cart.pending_inputs())
        with patch.dict("sys.modules", {"labjack": SimpleNamespace(ljm=SimpleNamespace(tcVoltsToTemp=convert))}), \
                patch.object(pump_cart, "_cj_temp_c", [25.0]):
            for voltage in (0.003, 0.0, -0.001):
                with self.subTest(voltage=voltage):
                    self.assertAlmostEqual(pump_cart._temperature(1.25 + 51 * voltage), 100)
                    kind, tc_v, cj = convert.call_args.args
                    self.assertEqual(kind, 6004)
                    self.assertAlmostEqual(tc_v, voltage)
                    self.assertAlmostEqual(cj, 298.15)


class PumpDAQ(FakeAirflowDAQ):
    def read(self, pin):
        self.reads.append(pin)
        if pin == "TEMPERATURE_DEVICE_K":
            return 298.15
        if pin == "AIN1":
            return 1.25 + 51 * 0.003  # InAmp output for a 3 mV thermocouple signal.
        if pin == "DIO0_EF_READ_A_AND_RESET":
            return 640_000  # 8 ms at 80 MHz -> 125 Hz -> 10 GPM at K=750.
        if pin == "AIN2":
            return 1.180  # 10 mA through the LJTick-CurrentShunt -> 1626.14 RPM.
        if pin == "AIN4":
            return 0.171  # Midpoint of the measured motor-power span -> 750 W.
        return 1.416


class PumpCartIOTests(unittest.TestCase):
    """Real connection/read lifecycle with fake I/O, without a window server."""

    def setUp(self):
        self.root = tk.Tcl()
        self.frame = PumpCartFrame.__new__(PumpCartFrame)
        f = self.frame
        f.config, f.daq = pump_cart, PumpDAQ()
        cfg = pump_cart.SENSOR_CONFIGS["bypass_flowrate"]
        f.sensors = {"bypass_flowrate": Sensor("bypass_flowrate", **cfg,
                     value_var=tk.StringVar(self.root))}
        f._polling = True
        f.after = Mock()
        f._reset_loop = Mock()
        f._enable_powered_controls = Mock()
        f._disable_powered_controls = Mock()
        f._pump_speed_var = tk.StringVar(self.root)
        f._switch_vars = {"pump": tk.BooleanVar(self.root, False)}
        f._main_power_var = tk.BooleanVar(self.root)
        f._connection_status, f._status_lbl = Mock(), Mock()
        f._pid = Mock()
        f.loops = {"flowrate": Mock()}
        f._connect("T7", "USB", "ANY")
        self.sensor = f.sensors["bypass_flowrate"]
        self.pin = cfg["pin"]

    def test_pump_speed_polling_preserves_draft_until_committed(self):
        f = self.frame
        for draft in ("", "5", "50"):
            f._pump_speed_var.set(draft)
            f._update_manual_analog_outputs()
            self.assertEqual(f._pump_speed_var.get(), draft)
            self.assertEqual(f.daq.writes[-1], ("DAC1", 0.0))
        f._commit_pump_speed()
        f._update_manual_analog_outputs()
        self.assertEqual(f.daq.writes[-1], ("DAC1", 0.0))

        f._switch_vars["pump"].set(True)
        for draft in ("", "7", "75"):
            f._pump_speed_var.set(draft)
            f._update_manual_analog_outputs()
            self.assertEqual(f._pump_speed_var.get(), draft)
            self.assertEqual(f.daq.writes[-1], ("DAC1", 2.5))
        f._commit_pump_speed()
        f._update_manual_analog_outputs()
        self.assertEqual(f.daq.writes[-1], ("DAC1", 3.75))

        f._pump_speed_var.set("1e")
        f._commit_pump_speed()
        f._update_manual_analog_outputs()
        self.assertEqual(f._pump_speed_var.get(), "75")
        self.assertEqual(f.daq.writes[-1], ("DAC1", 3.75))

    def poll(self, ticks, now):
        self.frame.daq.read = Mock(side_effect=lambda pin: ticks if pin == self.pin else 298.15)
        with patch("apps.pump_cart.time.monotonic", return_value=now):
            self.frame._update_all_sensors()

    def test_connect_configures_fio0_clock_and_read_reset(self):
        self.assertEqual(self.pin, "DIO0_EF_READ_A_AND_RESET")
        expected = [("DIO0_EF_ENABLE", 0), ("DIO_EF_CLOCK0_ENABLE", 0),
                    ("DIO_EF_CLOCK0_DIVISOR", 1), ("DIO_EF_CLOCK0_ROLL_VALUE", 0),
                    ("DIO_EF_CLOCK0_OPTIONS", 0), ("DIO_EF_CLOCK0_ENABLE", 1),
                    ("DIO0_EF_INDEX", 3), ("DIO0_EF_OPTIONS", 0),
                    ("DIO0_EF_CONFIG_A", 0), ("DIO0_EF_ENABLE", 1)]
        self.assertEqual(self.frame.daq.writes[-len(expected):], expected)
        self.poll(640_000, 100)
        self.assertEqual(self.sensor.value_var.get(), "10.00")
        self.assertEqual(self.sensor.get_raw_value(), 10)
        self.frame.daq.read.assert_any_call(self.pin)
        self.assertNotIn("DIO0_EF_READ_A_F", [c.args[0] for c in self.frame.daq.read.call_args_list])

    def test_inamp_thermocouple_polling_cjc_failure_and_recovery(self):
        from types import SimpleNamespace
        f = self.frame
        sensor = Sensor("fluid_temperature", **pump_cart.SENSOR_CONFIGS["fluid_temperature"],
                        value_var=tk.StringVar(self.root))
        f.sensors["fluid_temperature"] = sensor
        for register, value in (("AIN1_NEGATIVE_CH", 199), ("AIN1_RANGE", 10.0),
                                ("AIN1_RESOLUTION_INDEX", 8)):
            self.assertIn((register, value), f.daq.writes)
        convert = Mock(return_value=373.15)
        with patch.dict("sys.modules", {"labjack": SimpleNamespace(ljm=SimpleNamespace(tcVoltsToTemp=convert))}):
            f._update_all_sensors()
            convert.assert_called_once()
            kind, voltage, cj = convert.call_args.args
            self.assertEqual(kind, 6004)
            self.assertAlmostEqual(voltage, 0.003)
            self.assertAlmostEqual(cj, 298.15)
            self.assertEqual(sensor.value_var.get(), "100.00")
            self.assertIn("AIN1", f.daq.reads)
            self.assertNotIn("AIN0", f.daq.reads)
            convert.reset_mock()
            original_read = f.daq.read

            def failed_cjc(pin):
                if pin == "TEMPERATURE_DEVICE_K":
                    raise OSError("CJC read failed")
                return original_read(pin)

            with patch.object(f.daq, "read", side_effect=failed_cjc):
                f._update_all_sensors()
            self.assertEqual(sensor.value_var.get(), "Error")
            convert.assert_not_called()
            f._update_all_sensors()
            self.assertEqual(sensor.value_var.get(), "100.00")

    def test_startup_hold_timeout_and_restart_even_with_identical_periods(self):
        # Repeated nonzero values are NEW periods because the register clears on read.
        for ticks, now, flow in ((0, 99, 0), (640_000, 100, 10), (640_000, 100.5, 10),
                                 (0, 101, 10), (0, 101.5, 0), (640_000, 102, 10)):
            with self.subTest(ticks=ticks, now=now):
                self.poll(ticks, now)
                self.assertEqual(self.sensor.get_raw_value(), flow)

    def test_read_errors_and_invalid_ticks_clear_flow_history(self):
        for bad in (-1, math.nan, math.inf, 2**32, 0.5, "invalid", OSError("read failed")):
            with self.subTest(bad=bad):
                self.poll(640_000, 100)
                if isinstance(bad, Exception):
                    self.frame.daq.read = Mock(side_effect=bad)
                    self.frame._update_all_sensors()
                else:
                    self.poll(bad, 100.5)
                self.assertEqual(self.sensor.value_var.get(), "Error")
                with self.assertRaises(ValueError):
                    self.sensor.get_raw_value()
                self.poll(0, 100.6)
                self.assertEqual(self.sensor.get_raw_value(), 0)
        self.poll(640_000, 101)
        self.assertEqual(self.sensor.get_raw_value(), 10)

    def test_disconnect_and_reconnect_clear_flow_history(self):
        self.poll(640_000, 100)
        self.frame._disconnect()
        self.assertEqual(self.sensor.value_var.get(), "---")
        self.assertIsNone(self.frame._bypass_last_sample_time)
        self.frame._connect("T7", "USB", "ANY")
        self.poll(0, 100.1)
        self.assertEqual(self.sensor.get_raw_value(), 0)

    def test_unconfirmed_calibration_remains_todo(self):
        self.poll(640_000, 100)
        with patch.object(pump_cart, "BYPASS_PULSES_PER_GALLON", None):
            self.poll(640_000, 100.1)
        self.assertEqual(self.sensor.value_var.get(), "TODO")
        self.poll(0, 100.2)
        self.assertEqual(self.sensor.get_raw_value(), 0)

    def test_simulation_returns_timer_ticks_for_both_supported_inputs(self):
        daq = LabJackInterface()  # Defaults to simulation; never opens hardware.
        daq.safety.transition_to(SafetyState.CONNECTED_SAFE)
        daq.safety.transition_to(SafetyState.ENABLED)
        for pin in ("DIO0_EF_READ_A_AND_RESET", "DIO1_EF_READ_A_AND_RESET"):
            ticks = daq.read(pin)
            self.assertEqual(ticks, int(ticks))
            flow = pump_cart._bypass_flow(ticks / pump_cart.BYPASS_CLOCK_HZ)
            self.assertAlmostEqual(flow, 10, delta=0.5)
        daq.disconnect()


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
                    for tile in self.frame._sidebar.winfo_children():
                        self.assertLessEqual(tile.winfo_y() + tile.winfo_height(),
                                             self.frame._sidebar.winfo_height())
                    self.assertEqual(self.frame._loop_widgets["flowrate"]["mode_switch"].cget("style"), "Switch")
                    mode = self.frame._loop_widgets["flowrate"]["mode_switch"]
                    manual = self.frame._loop_widgets["flowrate"]["manual_spinbox"]
                    self.assertEqual(mode.grid_info()["row"], manual.grid_info()["row"])
                    self.assertAlmostEqual(mode.winfo_rooty() + mode.winfo_height() / 2,
                                           manual.winfo_rooty() + manual.winfo_height() / 2, delta=1)
                    bounds = [self.frame._pid.bbox(r["item"]) for r in self.frame._readouts.values()]
                    field_centers = {}
                    for key, readout in self.frame._readouts.items():
                        self.assertEqual(str(readout["entry"].cget("state")), "readonly")
                        self.assertEqual(readout["entry"].cget("style"), "")
                        self.assertEqual(str(readout["entry"].cget("textvariable")), str(readout["variable"]))
                        self.assertGreaterEqual(float(self.frame._pid.itemcget(readout["line"], "width")), 2)
                        entry = readout["entry"]
                        cx = entry.winfo_rootx() + entry.winfo_width() / 2 - self.frame._pid.winfo_rootx()
                        cy = entry.winfo_rooty() + entry.winfo_height() / 2 - self.frame._pid.winfo_rooty()
                        field_centers[key] = cx, cy
                        target_x, target_y = self.frame._point(readout["card"])
                        self.assertAlmostEqual(cx, target_x, delta=1)
                        self.assertAlmostEqual(cy, target_y, delta=1)
                        line = self.frame._pid.coords(readout["line"])
                        if readout["edge"] in ("top", "bottom"):
                            self.assertAlmostEqual(line[-2], cx, delta=1)
                        else:
                            self.assertAlmostEqual(line[-1], cy, delta=1)
                        # Leaders use right-angle bends and enter field centers.
                        for x1, y1, x2, y2 in zip(line[0::2], line[1::2], line[2::2], line[3::2]):
                            self.assertTrue(abs(x1 - x2) < 1e-6 or abs(y1 - y2) < 1e-6)
                    bottom_y = [field_centers[key][1] for key in
                                ("el_dp", "bypass_dp", "pipe_dp", "bypass_flowrate")]
                    self.assertLessEqual(max(bottom_y) - min(bottom_y), 1)
                    for key in ("ball_valve_dp", "valve"):
                        self.assertAlmostEqual(field_centers[key][0],
                                               self.frame._point(self.frame._readouts[key]["tap"])[0], delta=1)
                    for key in ("flowrate", "fluid_temperature", "tee_dp"):
                        self.assertAlmostEqual(field_centers[key][1],
                                               self.frame._point(self.frame._readouts[key]["tap"])[1], delta=1)
                    for item in self.frame._pid.find_all():
                        if self.frame._pid.type(item) == "text":
                            self.assertNotIn("Approximate", self.frame._pid.itemcget(item, "text"))
                            self.assertNotIn("TODO", self.frame._pid.itemcget(item, "text"))
                    elbow = self.frame._readouts["el_dp"]
                    self.assertEqual(tuple(self.frame._pid.coords(elbow["line"])[:2]),
                                     self.frame._point((10, 349)))
                    image = self.frame._pid.bbox(self.frame._diagram_item)
                    self.assertGreaterEqual(min(image[:2]), 0)
                    self.assertLessEqual(image[2], self.frame._pid.winfo_width())
                    self.assertLessEqual(image[3], self.frame._pid.winfo_height())
                    for a in bounds:
                        self.assertGreaterEqual(min(a[:2]), 0)
                        self.assertLessEqual(a[2], self.frame._pid.winfo_width())
                        self.assertLessEqual(a[3], self.frame._pid.winfo_height())
                    for i, a in enumerate(bounds):
                        for b in bounds[i+1:]:
                            self.assertTrue(a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (a, b))
        self.assertEqual(self.daq.reads, [])

    def test_source_export_resolution_does_not_change_layout(self):
        self.root.geometry("1320x700+0+40")
        self.root.deiconify()
        self.root.update()
        f = self.frame
        source = f._diagram_image
        original_image_bounds = f._pid.bbox(f._diagram_item)
        original_readouts = {key: f._pid.coords(r["item"]) for key, r in f._readouts.items()}
        try:
            # The same crop at one-third of the source resolution must occupy
            # exactly the same display area and keep the leaders in place.
            f._diagram_image = source.resize((source.width // 3, source.height // 3))
            from types import SimpleNamespace
            f._resize_diagram(SimpleNamespace(width=f._pid.winfo_width(), height=f._pid.winfo_height()))
            self.assertEqual(f._pid.bbox(f._diagram_item), original_image_bounds)
            self.assertEqual({key: f._pid.coords(r["item"]) for key, r in f._readouts.items()},
                             original_readouts)
            self.assertLess(f._bg_img.width(), source.width)
        finally:
            f._diagram_image = source

    def test_connection_manual_speed_valve_bounds_and_shutdown(self):
        f = self.frame
        f._connect("T7", "USB", "ANY")
        self.assertEqual(self.daq.safety.safe_outputs, {"FIO2": 0, "DAC0": 0, "DAC1": 0})
        self.assertEqual(self.daq.writes[:3], [("FIO2", 0), ("DAC0", 0), ("DAC1", 0)])
        self.assertFalse(f._switch_vars["pump"].get())
        f._pump_speed_box.delete(0, "end")
        for digit in "50":
            f._pump_speed_box.insert("end", digit)
            f._update_manual_analog_outputs()
        self.assertEqual(f._pump_speed_box.get(), "50")
        f._pump_speed_box.event_generate("<FocusOut>")
        f._update_manual_analog_outputs()
        self.assertEqual(self.daq.writes[-1], ("DAC1", 0))
        f._pump_switch.invoke()
        f._update_manual_analog_outputs()
        self.assertEqual(self.daq.writes[-1], ("DAC1", 2.5))
        f._update_all_sensors()
        self.assertEqual(f.sensors["pump_speed_rpm"].value_var.get(), "1626.14")
        self.assertEqual(f.sensors["pump_motor_power"].value_var.get(), "750.00")
        self.assertEqual(f.sensors["pump_dp"].value_var.get(), "25.00")
        self.assertNotIn("control_valve_dp", f._readouts)
        self.assertNotIn("control_valve_dp", f.sensors)
        self.assertNotIn("AIN5", self.daq.reads)
        f._pump_speed_var.set("150")
        f._pump_speed_box.event_generate("<FocusOut>")
        f._update_manual_analog_outputs()
        self.assertEqual(self.daq.writes[-1], ("DAC1", 5))
        self.assertEqual(f._pump_speed_var.get(), "100")
        f.loops["flowrate"].rounded_valve_position.set(200)
        f._update_all_loops()
        self.assertEqual(self.daq.writes[-1], ("DAC0", 5))
        self.assertAlmostEqual(f.loops["flowrate"].get_measured(), 39.895, delta=0.01)
        f._pump_switch.invoke()
        self.assertEqual(self.daq.writes[-1], ("DAC1", 0))
        f._disconnect()
        self.assertEqual(self.daq.safety.state, SafetyState.DISCONNECTED)
        self.assertEqual(dict(self.daq.writes[-3:]), {"FIO2": 0, "DAC0": 0, "DAC1": 0})
        self.assertEqual(f.loops["flowrate"].measured_var.get(), "---")
        self.assertEqual(f._pump_speed_var.get(), "0")

    def test_main_flow_pid_bypass_is_monitor_only_and_animation_stops(self):
        f = self.frame
        with patch.object(pump_cart, "MAIN_FLOW_SIGNAL_V", (0.472, 2.360)):
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
            for dashes in f._dashes.values():
                for dash in dashes:
                    self.assertEqual(f._pid.itemcget(dash.item, "state"), "normal")
                    self.assertEqual(f._pid.type(dash.item), "line")
                    self.assertGreaterEqual(len(f._pid.coords(dash.item)), 4)
            f._pump_switch.invoke()
            self.assertTrue(all(f._pid.itemcget(p.item, "state") == "hidden"
                                for dashes in f._dashes.values() for p in dashes))
            self.daq.read = Mock(side_effect=OSError("sensor unplugged"))
            f._pump_switch.invoke()
            f._update_all_loops()
            self.assertEqual(self.daq.safety.state, SafetyState.FAULTED)
            self.assertFalse(f._main_power_on)
            self.assertEqual(dict(self.daq.writes[-3:]), {"FIO2": 0, "DAC0": 0, "DAC1": 0})

    def test_csv_records_main_and_bypass_separately_with_manual_speed(self):
        f = self.frame
        f._connect("T7", "USB", "ANY")
        f._update_all_sensors()
        f.loops["flowrate"].set_measured(40)
        f.sensors["bypass_flowrate"].set_value(10)
        f._pump_switch.invoke()
        f._pump_speed_var.set("60")
        f._commit_pump_speed()
        f._on_toggle_logging()
        f.logger.stop()
        with open(f.logger.filepath, newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 1)
        self.assertEqual(float(rows[0]["Main flow (GPM)"]), 40)
        self.assertEqual(float(rows[0]["Bypass flow (GPM)"]), 10)
        self.assertEqual(float(rows[0]["Pump speed command (%)"]), 60)
        self.assertEqual(float(rows[0]["Motor power (W)"]), 750)
        self.assertEqual(float(rows[0]["Pump ΔP (psi)"]), 25)
        self.assertNotIn("Control valve ΔP (psi)", rows[0])
        for key in pump_cart.PRESSURE_CHANNELS:
            self.assertIn(f"{pump_cart.SENSOR_CONFIGS[key]['label']} (psi)", rows[0])


if __name__ == "__main__":
    unittest.main()
