"""Laptop pump-cart view; shares the development pump/valve lifecycle."""

import math
import time
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk

from apps.nonnewtonian import NonNewtonianFrame
from core.base_app import UPDATE_INTERVAL_MS
from core.numeric_entry import finite_number
from core.safety import SafetyState
from core.ui_builders import ensure_control_styles


class FlowParticle:
    """Open polyline: wrapping to the inlet never draws a closing shortcut."""
    def __init__(self, canvas, path, color, offset):
        self.path = path
        self.lengths = [math.dist(a, b) for a, b in zip(path, path[1:])]
        self.length = sum(self.lengths)
        self.distance = offset * self.length
        self.item = canvas.create_oval(0, 0, 0, 0, fill=color, outline="", state="hidden", tags="fluid")

    def at(self, distance):
        remaining = distance % self.length
        for a, b, length in zip(self.path, self.path[1:], self.lengths):
            if remaining <= length:
                f = remaining / length if length else 0
                return a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])
            remaining -= length
        return self.path[-1]


class PumpCartFrame(NonNewtonianFrame):
    ANIM_MS = 40
    def _build_ui(self):
        self.style = ttk.Style(self)
        ensure_control_styles(self.style)
        self._sensor_widgets = {}
        self._loop_widgets = {}
        self._auto_var = tk.BooleanVar(self, False)
        self._control_message = tk.StringVar(self, "")
        self._pump_speed_var = tk.StringVar(self, "0")
        self._manual_analog_vars["pump_speed"] = self._pump_speed_var
        self._output_label = "Valve"
        self._build_header_bar()
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=8, pady=6)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        self._sidebar = ttk.Frame(body, width=368)
        self._sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        self._sidebar.grid_propagate(False)
        self._sidebar.columnconfigure(0, weight=1)
        self._build_connection(self._sidebar)
        self._build_flow_control(self._sidebar)
        self._build_logging(self._sidebar)
        ttk.Label(self._sidebar, text="BYU TIPICE · Unit #1",
                  anchor="center").grid(row=3, column=0, sticky="ew", pady=3)
        diagram = ttk.LabelFrame(body, text="Piping and Instrumentation Diagram", padding=6)
        diagram.grid(row=0, column=1, sticky="nsew")
        self._pid = tk.Canvas(diagram, width=800, height=580, background="white",
                              highlightthickness=0, borderwidth=0)
        self._pid.pack(fill="both", expand=True)
        with Image.open(self.config.PID_IMAGE) as source:
            self._diagram_image = source.convert("RGB")
        self._diagram_item = self._pid.create_image(0, 0, anchor="nw")
        self._diagram_transform = (1, 0, 0)
        self._readouts = {}
        loop = self.loops["flowrate"]
        for key, label, card, tap in self.config.DIAGRAM_READOUTS:
            variable = (loop.measured_var if key == "flowrate" else
                        loop.rounded_valve_position if key == "valve" else self.sensors[key].value_var)
            unit = "GPM" if key == "flowrate" else "%" if key == "valve" else self.sensors[key].unit
            line = self._pid.create_line(0, 0, 0, 0, fill="#455a64", dash=(5, 3), width=2)
            frame = tk.Frame(self._pid, bg="white")
            tk.Label(frame, text=f"{label} ({unit})", bg="white", fg="#263238",
                     font=("Helvetica", 11, "bold")).pack()
            entry = ttk.Entry(frame, textvariable=variable, state="readonly", justify="center", width=10)
            entry.pack(pady=(3, 0))
            item = self._pid.create_window(0, 0, window=frame, anchor="center")
            self._readouts[key] = {"line": line, "item": item, "frame": frame, "entry": entry,
                                   "card": card, "tap": tap, "variable": variable}
            if key in self.sensors:
                self._sensor_widgets[key] = {"entry": entry}
        self._pump_indicator = self._pid.create_text(0, 0, text="Pump OFF", fill="#a12622")
        self._note = self._pid.create_text(0, 0, anchor="s", fill="#596975",
            text="* Approximate ΔP tap locations.  TODO = signal calibration needed.")
        self._particles = {}
        for name, path in self.config.FLOW_PATHS.items():
            count = max(3, int(sum(math.dist(a, b) for a, b in zip(path, path[1:])) / 70))
            self._particles[name] = [FlowParticle(self._pid, path,
                "#00897b" if name == "bypass" else "#1976d2", i / count) for i in range(count)]
        self._switch_vars["pump"].trace_add("write", self._update_pump_indicator)
        self._pid.bind("<Configure>", self._resize_diagram)
        self._last_animation = time.monotonic()
        self._animation_id = self.after(self.ANIM_MS, self._animate)

    def _panel(self, parent, title, row):
        panel = ttk.LabelFrame(parent, text=title, padding=(8, 4))
        panel.grid(row=row, column=0, sticky="new", pady=(0, 4))
        panel.columnconfigure(1, weight=1)
        return panel

    def _label(self, parent, text, row, col=0, **kw):
        label = ttk.Label(parent, text=text)
        label.grid(row=row, column=col, sticky="w", pady=1, **kw)
        return label

    def _spinbox(self, parent, variable, row, maximum=100, minimum=0):
        box = ttk.Spinbox(parent, from_=minimum, to=maximum, increment=0.1,
                          textvariable=variable, width=8)
        box.grid(row=row, column=1, sticky="ew", padx=(6, 0), pady=1)
        return box

    def _build_connection(self, parent):
        panel = self._panel(parent, "Pump and connection", 0)
        self._connect_dropdown = ttk.OptionMenu(panel, self._connection_var, "Connect to LabJack",
            "USB", "Ethernet", "Disconnect", command=self._on_connection_choice)
        self._connect_dropdown.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._connection_status = self._label(panel, "Not connected", 1, 1)
        switch = self.config.SYSTEM_SWITCHES[0]
        self._switch_vars["pump"] = tk.BooleanVar(self, False)
        self._pump_switch = ttk.Checkbutton(panel, text="Pump: OFF", style="Switch",
            variable=self._switch_vars["pump"], command=lambda: self._on_toggle_switch("pump", switch))
        self._pump_switch.grid(row=1, column=0, sticky="w", pady=1)
        self._switch_widgets.append((self._pump_switch, "Pump"))
        self._label(panel, "Speed command (%)", 2)
        self._pump_speed_box = self._spinbox(panel, self._pump_speed_var, 2)
        self._manual_analog_widgets.append(self._pump_speed_box)
        for row, (key, label) in enumerate((("pump_speed_rpm", "Actual speed (RPM)"),
                                           ("pump_motor_power", "Motor power (W)")), 3):
            self._label(panel, label, row)
            entry = ttk.Entry(panel, textvariable=self.sensors[key].value_var,
                              width=8, state="readonly", justify="center")
            entry.grid(row=row, column=1, sticky="ew", padx=(6, 0), pady=1)
            self._sensor_widgets[key] = {"entry": entry}

    def _build_flow_control(self, parent):
        panel = self._panel(parent, "Main flow control", 1)
        loop = self.loops["flowrate"]
        widgets = {"frame": panel}
        self._label(panel, "Setpoint (GPM)", 0)
        widgets["setpoint_spinbox"] = self._spinbox(panel, loop.setpoint_var, 0, maximum=79)
        self._label(panel, "Measured (GPM)", 1)
        widgets["measured_entry"] = ttk.Entry(panel, textvariable=loop.measured_var,
            state="readonly", width=8, justify="center")
        widgets["measured_entry"].grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=1)
        widgets["mode_switch"] = ttk.Checkbutton(panel, text="Mode: MANUAL", style="Switch",
            variable=self._auto_var, command=self._toggle_mode)
        widgets["mode_switch"].grid(row=2, column=0, columnspan=2, sticky="w", pady=1)
        self._label(panel, "Valve command (%)", 3)
        widgets["manual_spinbox"] = self._spinbox(panel, loop.rounded_valve_position, 3)
        widgets["scale"] = ttk.Scale(panel, from_=0, to=100, variable=loop.valve_position)
        widgets["scale"].grid(row=4, column=0, columnspan=2, sticky="ew", pady=1)
        loop.valve_position.trace_add("write", self._sync_manual_slider)
        for event in ("<Return>", "<FocusOut>", "<<Increment>>", "<<Decrement>>"):
            widgets["manual_spinbox"].bind(event, self._commit_manual)
        tuning = ttk.Frame(panel)
        tuning.grid(row=5, column=0, columnspan=2, sticky="ew", pady=1)
        for col, (key, label, var, minimum) in enumerate((
            ("Kc", "Kc", loop.Kc_var, -1000), ("Ti", "Ti (min)", loop.Ti_var, 0),
            ("Td", "Td (min)", loop.Td_var, 0))):
            tuning.columnconfigure(col, weight=1, uniform="pid")
            self._label(tuning, label, 0, col)
            box = ttk.Spinbox(tuning, from_=minimum, to=1000, increment=0.01, textvariable=var, width=4)
            box.grid(row=1, column=col, sticky="ew", padx=2)
            widgets[f"{key}_spinbox"] = box
        ttk.Label(panel, textvariable=self._control_message,
                  wraplength=330).grid(row=6, column=0, columnspan=2, sticky="ew")
        self._loop_widgets["flowrate"] = widgets

    def _build_logging(self, parent):
        panel = self._panel(parent, "Data Logging", 2)
        self._logging_panel = panel
        self._label(panel, "Experiment ID", 0)
        self._experiment_id_entry = ttk.Entry(panel, textvariable=self._experiment_id_var, width=13)
        self._experiment_id_entry.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=2)
        self._label(panel, "Interval (s)", 1)
        self._spinbox(panel, self._log_interval_var, 1, minimum=0.1)
        self._label(panel, "Data points", 2)
        ttk.Label(panel, textvariable=self._data_point_count, width=7).grid(row=2, column=1)
        self._toggle_logging_btn = ttk.Checkbutton(panel, textvariable=self._logging_text_var,
            style="ToggleButton", command=self._on_toggle_logging)
        self._toggle_logging_btn.grid(row=3, column=0, columnspan=2, sticky="ew", pady=2)

    def _resize_diagram(self, event):
        # Virtual space extends beyond the source PNG to hold the readouts.
        scale = max(0.1, min((event.width - 16) / 760, (event.height - 36) / 480))
        left = (event.width - 760 * scale) / 2 + 130 * scale
        top = (event.height - 480 * scale) / 2 + 80 * scale
        self._diagram_transform = scale, left, top
        w, h = self._diagram_image.size
        self._bg_img = ImageTk.PhotoImage(self._diagram_image.resize(
            (max(1, round(w * scale)), max(1, round(h * scale))), Image.Resampling.LANCZOS))
        self._pid.coords(self._diagram_item, left, top)
        self._pid.itemconfigure(self._diagram_item, image=self._bg_img)
        self._layout_readouts()
        self._pid.coords(self._pump_indicator, *self._point((144, 260)))
        self._pid.itemconfigure(self._pump_indicator, font=("Helvetica", 11, "bold"))
        self._pid.coords(self._note, event.width / 2, event.height - 4)
        self._pid.itemconfigure(self._note, font=("Helvetica", 9))

    def _layout_readouts(self):
        for readout in self._readouts.values():
            cx, cy = self._point(readout["card"])
            tx, ty = self._point(readout["tap"])
            self._pid.coords(readout["item"], cx, cy)
            frame = readout["frame"]
            half_width, half_height = frame.winfo_reqwidth() / 2, frame.winfo_reqheight() / 2
            bounds = cx - half_width, cy - half_height, cx + half_width, cy + half_height
            ex, ey = max(bounds[0], min(bounds[2], tx)), max(bounds[1], min(bounds[3], ty))
            self._pid.coords(readout["line"], tx, ty, ex, ey)

    def _point(self, point):
        scale, left, top = self._diagram_transform
        return left + point[0] * scale, top + point[1] * scale

    def _update_pump_indicator(self, *_):
        on = self._switch_vars["pump"].get()
        self._pid.itemconfigure(self._pump_indicator, text="Pump ON" if on else "Pump OFF",
                                fill="#23783c" if on else "#a12622")
        if not on:
            self._pid.itemconfigure("fluid", state="hidden")

    def _animate(self):
        now = time.monotonic()
        dt = min(0.15, now - self._last_animation)
        self._last_animation = now
        running = self.daq.is_connected and self._main_power_on and self._switch_vars["pump"].get()
        main = self.loops["flowrate"].get_measured()
        try:
            bypass = max(0, finite_number(self.sensors["bypass_flowrate"].value_var.get()))
        except (ValueError, tk.TclError):
            bypass = None
        rates = {"supply": main, "return": main, "bypass": bypass,
                 "pipe": max(0, main - bypass) if main is not None and bypass is not None else None}
        for name, particles in self._particles.items():
            rate = rates[name]
            active = running and rate is not None and rate > 0.05
            for particle in particles:
                self._pid.itemconfigure(particle.item, state="normal" if active else "hidden")
                if active:
                    particle.distance += dt * min(110, 22 + rate * 2)
                    x, y = self._point(particle.at(particle.distance))
                    r = max(2, 2.5 * self._diagram_transform[0])
                    self._pid.coords(particle.item, x-r, y-r, x+r, y+r)
        self._animation_id = self.after(self.ANIM_MS, self._animate)

    def _connect(self, model, connection, identifier):
        if self.daq.is_connected:
            self._disconnect()
        self.daq.safety.safe_outputs.clear()
        for pin in ("FIO2", "DAC0", "DAC1"):
            self.daq.safety.register_safe_output(pin, 0)
        try:
            self.daq.connect(model, connection, identifier)
            for pin, value in self.daq.safety.safe_outputs.items():
                self.daq._force_write(pin, value)
            for ch, settings in self.config.AIN_CONFIGS.items():
                for register, value in settings.items():
                    self.daq._force_write(f"{ch}_{register}", value)
            for register, value in self.config.BYPASS_INPUT_SETUP:
                self.daq._force_write(register, value)
            self._reset_loop()
            self._pump_speed_var.set("0")
            self.daq.safety.transition_to(SafetyState.ENABLED)
            self._main_power_on = True
            self._main_power_var.set(True)
            self._enable_powered_controls()
            self._connection_status.configure(text="Connected")
            self._status_lbl.configure(text="CONNECTED", foreground="green")
        except Exception as exc:
            self._disconnect()
            self._status_lbl.configure(text="CONNECTION FAILED", foreground="red")
            messagebox.showerror("Connection Failed", str(exc), parent=self.winfo_toplevel())

    def _disable_powered_controls(self):
        super()._disable_powered_controls()
        self._pump_speed_var.set("0")

    def _disconnect(self):
        super()._disconnect()
        self._pid.itemconfigure("fluid", state="hidden")

    def _on_toggle_switch(self, key, sw):
        super()._on_toggle_switch(key, sw)
        if not self._switch_vars[key].get():
            self._pump_speed_var.set("0")
            if self.daq.is_connected and self._main_power_on:
                try:
                    self.daq.write("DAC1", 0)
                except Exception as exc:
                    self._fault(f"Pump speed output failed: {exc}")

    def _update_all_sensors(self):
        if not self._polling:
            return
        if self.daq.is_connected:
            pending = self.config.pending_inputs()
            if "fluid_temperature" not in pending:
                try:
                    self.config._cj_temp_c[0] = finite_number(self.daq.read(self.config.COLD_JUNCTION_REGISTER)) - 273.15
                except Exception:
                    self.config._cj_temp_c[0] = float("nan")
            for key, sensor in self.sensors.items():
                if key in pending:
                    sensor.reset()
                    sensor.value_var.set("TODO")
                    continue
                try:
                    sensor.set_value(sensor.apply_calibration(self.daq.read(sensor.pin)))
                except Exception:
                    sensor.set_error()
        self.after(UPDATE_INTERVAL_MS, self._update_all_sensors)

    def _update_all_loops(self):
        if not self._polling:
            return
        super()._update_all_loops()
        if self.daq.is_connected and "flowrate" in self.config.pending_inputs():
            self.loops["flowrate"].measured_var.set("TODO")

    def _update_manual_analog_outputs(self):
        if not self._polling:
            return
        if self._main_power_on and self.daq.is_connected:
            try:
                percent = max(0, min(100, finite_number(self._pump_speed_var.get())))
                if not self._switch_vars["pump"].get():
                    percent = 0
                self._pump_speed_var.set(f"{percent:g}")
                low, high = self.config.PUMP_SPEED_OUTPUT_V
                voltage = low + percent / 100 * (high - low)
            except (ValueError, tk.TclError):
                voltage = 0
            try:
                self.daq.write("DAC1", voltage)
            except Exception as exc:
                self._fault(f"Pump speed output failed: {exc}")
        self.after(UPDATE_INTERVAL_MS, self._update_manual_analog_outputs)

    def _build_logger(self):
        self._unit_op = "PumpCart1"
        super()._build_logger()
        self.logger._sources["Pump speed command (%)"] = self._pump_speed_var.get
        self.logger._numeric_sources.add("Pump speed command (%)")
        self.logger._influx_sources["pump_speed_command"] = self._pump_speed_var.get
