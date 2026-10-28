"""Non-Newtonian apparatus screen with a pump-driven flow PID loop."""

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from core.base_app import BaseAppFrame, DT_MINUTES, UPDATE_INTERVAL_MS
from core.numeric_entry import finite_number
from core.safety import SafetyState


class NonNewtonianFrame(BaseAppFrame):
    def _build_ui(self):
        self.style = ttk.Style(self)
        self._sensor_widgets = {}
        self._loop_widgets = {}
        self._theme_dark = False
        self._auto_var = tk.BooleanVar(value=False)
        self._output_label = getattr(self.config, "OUTPUT_LABEL", "Pump Speed")
        self._control_message = tk.StringVar(value="")
        self._build_header_bar()

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=10, pady=10)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self._canvas = tk.Canvas(body, highlightthickness=0)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(body, command=self._canvas.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(body, orient="horizontal", command=self._canvas.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self._canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self._sf = ttk.Frame(self._canvas)
        self._sf.columnconfigure(1, weight=1)
        self._sf.rowconfigure(0, weight=1)
        self._sf_window = self._canvas.create_window(0, 0, window=self._sf, anchor="nw")
        self._canvas.bind("<Configure>", self._resize_body)
        self._sf.bind("<Configure>", lambda _: self._canvas.configure(scrollregion=self._canvas.bbox("all")))

        sidebar = ttk.Frame(self._sf)
        sidebar.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 12))
        controls = ttk.LabelFrame(sidebar, text="Controls", padding=12)
        controls.pack(fill="x", pady=(0, 10))
        ttk.OptionMenu(controls, self._connection_var, "Connect to LabJack", "USB", "Ethernet", "Disconnect",
                       command=self._on_connection_choice).pack(fill="x")
        self._connection_status = ttk.Label(controls, text="Not connected")
        self._connection_status.pack(fill="x", pady=6)
        switch = self.config.SYSTEM_SWITCHES[0]
        self._switch_vars["pump"] = tk.BooleanVar(value=False)
        self._pump_switch = ttk.Checkbutton(
            controls, text="Pump: OFF", style="Switch", variable=self._switch_vars["pump"],
            command=lambda: self._on_toggle_switch("pump", switch))
        self._pump_switch.pack(fill="x", pady=4)
        self._switch_widgets.append((self._pump_switch, "Pump"))
        ttk.Label(controls, textvariable=self._control_message, wraplength=240).pack(fill="x", pady=(4, 0))

        log = ttk.LabelFrame(sidebar, text="Data Logging", padding=12)
        log.pack(fill="x", pady=(0, 10))
        row = ttk.Frame(log)
        row.pack(fill="x", pady=(0, 8))
        ttk.Label(row, text="Experiment ID").pack(side="left")
        self._experiment_id_entry = ttk.Entry(row, textvariable=self._experiment_id_var, width=18)
        self._experiment_id_entry.pack(side="right")
        self._toggle_logging_btn = ttk.Checkbutton(
            log, textvariable=self._logging_text_var, style="ToggleButton", command=self._on_toggle_logging)
        self._toggle_logging_btn.pack(fill="x", pady=(0, 8))
        for label, var, editable in (("Interval (s)", self._log_interval_var, True),
                                     ("Data Point Count", self._data_point_count, False)):
            row = ttk.Frame(log)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=label).pack(side="left")
            if editable:
                ttk.Spinbox(row, from_=0.1, to=100, textvariable=var, width=7).pack(side="right")
            else:
                ttk.Entry(row, textvariable=var, state="readonly", width=7).pack(side="right")
        self._theme_btn = ttk.Button(sidebar, text="Dark Mode", command=self._toggle_theme)
        self._theme_btn.pack(fill="x")
        with Image.open(self.config.LOGO_FILE) as source:
            logo = source.convert("RGBA")
        logo.thumbnail((180, 120), Image.Resampling.LANCZOS)
        self._logo_img = ImageTk.PhotoImage(logo)
        ttk.Label(sidebar, image=self._logo_img, anchor="center").pack(fill="x", pady=(18, 5))
        ttk.Label(sidebar, text="BYU TIPICE", font=("Helvetica", 20, "bold"), anchor="center").pack(fill="x")

        diagram = ttk.LabelFrame(self._sf, text="Piping and Instrumentation Diagram", padding=8)
        diagram.grid(row=0, column=1, sticky="nsew", pady=(0, 10))
        self._pid = tk.Canvas(diagram, width=950, height=390, bg="white", highlightthickness=0)
        self._pid.pack(fill="both", expand=True)
        with Image.open(self.config.PID_IMAGE) as source:
            self._diagram_image = source.convert("RGB")
        self._diagram_item = self._pid.create_image(0, 0, anchor="nw")
        self._overlays = []
        self._readout_widgets = {}
        loop = self.loops["flowrate"]
        for key, label, x, y, anchor in self.config.DIAGRAM_READOUTS:
            if key == "flowrate":
                variable = loop.measured_var
            elif key == "output":
                variable = loop.rounded_valve_position
            else:
                variable = self.sensors[key].value_var
            self._add_readout(label, variable, x, y, anchor, key)
        self._pump_status_label = tk.Label(
            self._pid, font=("Helvetica", 11, "bold"), fg="white", padx=8, pady=3,
        )
        self._pump_status_item = self._pid.create_window(
            0, 0, window=self._pump_status_label, anchor="s")
        self._overlays.append((*self.config.PUMP_STATUS_POSITION, self._pump_status_item))
        self._switch_vars["pump"].trace_add("write", self._update_pump_indicator)
        self._update_pump_indicator()
        self._pid.bind("<Configure>", self._resize_diagram)
        self._build_flow_panel(self._sf)

    def _resize_body(self, event):
        self._canvas.itemconfigure(self._sf_window, width=max(1200, event.width),
                                   height=max(self._sf.winfo_reqheight(), event.height))

    def _add_readout(self, label, variable, x, y, anchor, key):
        card = tk.Frame(self._pid, bg="white")
        tk.Label(card, text=label, bg="white", fg="#263238", font=("Helvetica", 11, "bold")).pack()
        entry = ttk.Entry(card, textvariable=variable, state="readonly", justify="center", width=10)
        entry.pack(pady=(3, 0))
        item = self._pid.create_window(0, 0, window=card, anchor=anchor)
        self._overlays.append((x, y, item))
        self._readout_widgets[key] = {"entry": entry, "frame": card, "item": item}
        if key in self.sensors:
            self._sensor_widgets[key] = {"entry": entry}

    def _update_pump_indicator(self, *_):
        pump_on = self._switch_vars["pump"].get()
        self._pump_status_label.configure(
            text="Pump: ON" if pump_on else "Pump: OFF",
            bg="#2e7d32" if pump_on else "#b71c1c",
        )

    def _resize_diagram(self, event):
        w, h = self._diagram_image.size
        scale = max(0.01, min((event.width - 64) / w, (event.height - 110) / h))
        width, height = max(1, round(w * scale)), max(1, round(h * scale))
        left = (event.width - width) / 2
        top = max(20, (event.height - height - 65) / 2)
        self._bg_img = ImageTk.PhotoImage(self._diagram_image.resize((width, height), Image.Resampling.LANCZOS))
        self._pid.itemconfigure(self._diagram_item, image=self._bg_img)
        self._pid.coords(self._diagram_item, left, top)
        for x, y, item in self._overlays:
            self._pid.coords(item, left + x * scale, top + y * scale)

    def _build_flow_panel(self, parent):
        loop = self.loops["flowrate"]
        panel = ttk.LabelFrame(parent, text="Flowrate Control", padding=12)
        panel.grid(row=1, column=1, sticky="ew")
        widgets = {"frame": panel}
        for col in range(3):
            panel.columnconfigure(col, weight=1)
        readings = ttk.Frame(panel)
        readings.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        ttk.Label(readings, text=f"Flow Setpoint ({loop.unit})").grid(row=0, column=0, sticky="w")
        widgets["setpoint_spinbox"] = ttk.Spinbox(
            readings, from_=loop.setpoint_min, to=loop.setpoint_max, increment=0.1,
            textvariable=loop.setpoint_var, width=10)
        widgets["setpoint_spinbox"].grid(row=1, column=0, sticky="ew", pady=(4, 8))
        ttk.Label(readings, text=f"{loop.label} ({loop.unit})").grid(row=2, column=0, sticky="w")
        widgets["measured_entry"] = ttk.Entry(readings, textvariable=loop.measured_var, width=10, state="readonly")
        widgets["measured_entry"].grid(row=3, column=0, sticky="ew", pady=4)

        manual = ttk.Frame(panel)
        manual.grid(row=0, column=1, sticky="nsew", padx=(0, 20))
        manual.columnconfigure(0, weight=1)
        widgets["mode_switch"] = ttk.Checkbutton(
            manual, text="Mode: MANUAL", style="Switch", variable=self._auto_var, command=self._toggle_mode)
        widgets["mode_switch"].grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(manual, text=f"{self._output_label} Command (%)").grid(row=1, column=0, columnspan=2, sticky="w")
        widgets["scale"] = ttk.Scale(manual, from_=0, to=100, variable=loop.valve_position)
        widgets["scale"].grid(row=2, column=0, sticky="ew", pady=8)
        widgets["manual_spinbox"] = ttk.Spinbox(
            manual, from_=0, to=100, textvariable=loop.rounded_valve_position, width=6)
        widgets["manual_spinbox"].grid(row=2, column=1, padx=(8, 0))
        loop.valve_position.trace_add("write", self._sync_manual_slider)
        for event in ("<Return>", "<FocusOut>", "<<Increment>>", "<<Decrement>>"):
            widgets["manual_spinbox"].bind(event, self._commit_manual)
        tuning = ttk.Frame(panel)
        tuning.grid(row=0, column=2, sticky="nsew")
        for col, (key, label, var, low) in enumerate((
            ("Kc", f"Kc (V/{loop.unit})", loop.Kc_var, -100),
            ("Ti", "Ti (min)", loop.Ti_var, 0),
            ("Td", "Td (min)", loop.Td_var, 0),
        )):
            ttk.Label(tuning, text=label).grid(row=0, column=col, padx=4)
            sb = ttk.Spinbox(tuning, from_=low, to=100, increment=0.01, textvariable=var, width=7)
            sb.grid(row=1, column=col, padx=4, pady=4)
            widgets[f"{key}_spinbox"] = sb
        ttk.Label(tuning, text="Initial tuning — commission on apparatus",
                  wraplength=240).grid(row=2, column=0, columnspan=3, pady=8)
        self._loop_widgets["flowrate"] = widgets

    def _sync_manual_slider(self, *_):
        loop = self.loops["flowrate"]
        loop.rounded_valve_position.set(round(max(0, min(100, finite_number(loop.valve_position.get())))))

    def _commit_manual(self, event=None):
        loop = self.loops["flowrate"]
        try:
            percent = finite_number(self._loop_widgets["flowrate"]["manual_spinbox"].get())
        except (ValueError, tk.TclError):
            percent = loop.valve_position.get()
        loop.valve_position.set(round(max(0, min(100, percent))))

    def _toggle_mode(self):
        loop = self.loops["flowrate"]
        loop.is_auto = self._auto_var.get()
        if loop.is_auto:
            loop.pid.initialize(loop.get_manual_voltage())
        else:
            loop.pid.reset()
        self._loop_widgets["flowrate"]["mode_switch"].configure(
            text="Mode: AUTO" if loop.is_auto else "Mode: MANUAL")
        self._enable_powered_controls()

    def _reset_loop(self):
        loop = self.loops["flowrate"]
        loop.is_auto = False
        loop.pid.reset()
        loop.set_valve_display(0)
        self._auto_var.set(False)
        self._loop_widgets["flowrate"]["mode_switch"].configure(text="Mode: MANUAL")
        self._control_message.set("")

    def _validate_experiment_id(self, *args):
        """Make logging available immediately after connection, with an optional run label."""
        if self._main_power_on:
            self._toggle_logging_btn.configure(state="normal")

    def _disable_powered_controls(self):
        super()._disable_powered_controls()
        self._reset_loop()
        self._toggle_logging_btn.state(["!selected"])

    def _connect(self, model, connection, identifier):
        if self.daq.is_connected:
            self._disconnect()
        for sensor in self.sensors.values():
            sensor.reset()
        # This DAQ object is shared by dashboard screens. Only this apparatus's
        # outputs may be applied when this screen connects to its T7.
        self.daq.safety.safe_outputs.clear()
        for sw in self.config.SYSTEM_SWITCHES:
            self.daq.safety.register_safe_output(sw["pin"], sw["inactive_value"])
        for loop in self.loops.values():
            self.daq.safety.register_safe_output(loop.output_pin, loop.pid.output_min)
        try:
            self.daq.connect(model, connection, identifier)
            # Establish OFF before enabling normal writes or exposing controls.
            for pin, value in self.daq.safety.safe_outputs.items():
                self.daq._force_write(pin, value)
            for ch, settings in self.config.AIN_CONFIGS.items():
                for register, value in settings.items():
                    self.daq._force_write(f"{ch}_{register}", value)
            self._reset_loop()
            self.daq.safety.transition_to(SafetyState.ENABLED)
            self._main_power_on = True
            self._main_power_var.set(True)
            self._enable_powered_controls()
            self._connection_status.configure(text="Connected")
            self._status_lbl.configure(text="CONNECTED", foreground="green")
        except Exception as exc:
            self._disconnect()
            self._connection_status.configure(text=f"Failed: {exc}")
            self._status_lbl.configure(text="CONNECTION FAILED", foreground="red")
            messagebox.showerror("Connection Failed", f"Could not connect to LabJack at {identifier}.\n\n{exc}",
                                 parent=self.winfo_toplevel())

    def _disconnect(self):
        # Stop the pump using this unit's OFF polarity before normal writes
        # are disabled, then close the connection through the shared lifecycle.
        if self.daq.is_connected:
            self.daq.safety.transition_to(SafetyState.SHUTTING_DOWN)
        super()._disconnect()
        # Do not carry this unit's output/polarity settings into another T7.
        self.daq.safety.safe_outputs.clear()
        for sensor in self.sensors.values():
            sensor.reset()
        self.loops["flowrate"].measured_var.set("---")

    def _on_toggle_switch(self, key, sw):
        if not self.daq.is_connected or not self._main_power_on:
            return
        try:
            pump_on = self._switch_vars[key].get()
            if not getattr(self.config, "MANUAL_OUTPUT_REQUIRES_PUMP", True):
                # A valve is independent of the pump relay: preserve its command
                # when starting/stopping the pump, and pause AUTO while stopped.
                self.daq.write(sw["pin"], sw["active_value"] if pump_on else sw["inactive_value"])
                self._pump_switch.configure(text="Pump: ON" if pump_on else "Pump: OFF")
                loop = self.loops["flowrate"]
                if loop.is_auto:
                    if pump_on:
                        loop.pid.initialize(loop.get_manual_voltage())
                    else:
                        loop.pid.reset()
                self._control_message.set(
                    "Automatic flow control paused — pump is off" if loop.is_auto and not pump_on
                    else "Automatic flow control" if loop.is_auto else "Manual valve control")
            elif pump_on:
                self._reset_loop()
                self.daq.write(self.loops["flowrate"].output_pin, 0.0)
                self.daq.write(sw["pin"], sw["active_value"])
                self._pump_switch.configure(text="Pump: ON")
                self._control_message.set(f"Manual {self._output_label.lower()} control")
            else:
                self.daq.write(sw["pin"], sw["inactive_value"])
                self.daq.write(self.loops["flowrate"].output_pin, 0.0)
                self._reset_loop()
                self._pump_switch.configure(text="Pump: OFF")
            self._enable_powered_controls()
        except Exception as exc:
            self._fault(f"Pump control failed: {exc}")

    def _fault(self, message):
        self.daq.safety.transition_to(SafetyState.FAULTED)
        self._main_power_on = False
        self._main_power_var.set(False)
        self._disable_powered_controls()
        self._status_lbl.configure(text="FAULT", foreground="red")
        self._connection_status.configure(text="Fault — reconnect to reset")
        self._control_message.set(message)

    def _update_all_sensors(self):
        if not self._polling:
            return
        if self.daq.is_connected:
            if hasattr(self.config, "_cj_temp_c"):
                self.config._cj_temp_c[0] = float("nan")
            super()._update_all_sensors()
        else:
            self.after(UPDATE_INTERVAL_MS, self._update_all_sensors)

    def _update_all_loops(self):
        if not self._polling:
            return
        try:
            if not self.daq.is_connected:
                return
            loop = self.loops["flowrate"]
            pump_on = self._switch_vars["pump"].get()
            manual_requires_pump = getattr(self.config, "MANUAL_OUTPUT_REQUIRES_PUMP", True)
            try:
                measured = finite_number(loop.apply_calibration(self.daq.read(loop.input_pin)))
                loop.set_measured(measured)
            except Exception as exc:
                loop.set_error()
                if loop.is_auto and pump_on and self._main_power_on:
                    self._fault(f"Flow measurement failed: {exc}")
                if loop.is_auto or manual_requires_pump:
                    return
            if not self._main_power_on:
                return
            if loop.is_auto and not pump_on:
                self._control_message.set("Automatic flow control paused — pump is off")
                return
            if manual_requires_pump and not pump_on:
                return
            try:
                if loop.is_auto:
                    sp = loop.get_setpoint()
                    if sp is None or not loop.setpoint_min <= sp <= loop.setpoint_max:
                        raise ValueError(f"Enter a flow setpoint from {loop.setpoint_min:g} to {loop.setpoint_max:g} {loop.unit}")
                    loop.sync_tuning_to_pid()
                    if loop.pid.Ti < 0 or loop.pid.Td < 0:
                        raise ValueError("Ti and Td must be non-negative")
                    voltage = loop.pid.compute(sp, measured, DT_MINUTES)
                else:
                    voltage = loop.get_manual_voltage()
            except (ValueError, TypeError, OverflowError, tk.TclError) as exc:
                voltage = 0.0
                loop.pid.reset()
                self._control_message.set(f"Output command held at zero: {exc}")
            else:
                self._control_message.set("Automatic flow control" if loop.is_auto else "Manual output control")
            try:
                voltage = max(loop.pid.output_min, min(loop.pid.output_max, finite_number(voltage)))
                self.daq.write(loop.output_pin, voltage)
                loop.set_valve_display(voltage)
            except Exception as exc:
                self._fault(f"Flow-control output write failed: {exc}")
        finally:
            self.after(UPDATE_INTERVAL_MS, self._update_all_loops)

    def _on_connection_choice(self, choice):
        if choice == "Ethernet" and not self.config.ETHERNET_ADDRESS:
            address = simpledialog.askstring("Ethernet Connection", f"{self.config.SYSTEM_NAME} LabJack IP address or serial number:",
                                             parent=self.winfo_toplevel())
            if address and address.strip():
                self._connect("T7", "ETHERNET", address.strip())
            else:
                self._connection_var.set("Connect to LabJack")
            return
        super()._on_connection_choice(choice)

    def _toggle_theme(self):
        self._theme_dark = not self._theme_dark
        theme = "forest-dark" if self._theme_dark else "forest-light"
        if theme in self.style.theme_names():
            self.style.theme_use(theme)
        self._theme_btn.configure(text="Light Mode" if self._theme_dark else "Dark Mode")
        self._canvas.configure(bg=self.style.lookup("TFrame", "background"))

    def destroy(self):
        self._polling = False
        if hasattr(self, "logger"):
            self._disconnect()
        for callback in self.tk.call("after", "info"):
            script = str(self.tk.call("after", "info", callback)[0])
            if any(script.startswith(command) for command in self._tclCommands or ()):
                self.after_cancel(callback)
        super().destroy()
