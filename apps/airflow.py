"""Airflow apparatus screen using the shared controls, logging and lifecycle."""

import tkinter as tk
from math import ceil
from tkinter import ttk, simpledialog

from PIL import Image, ImageTk

from core.base_app import BaseAppFrame, UPDATE_INTERVAL_MS
from core.numeric_entry import finite_number
from core.ui_builders import build_apparatus_tile, enable_loop_widgets, ensure_control_styles, readout_row_scale


class AirflowFrame(BaseAppFrame):
    def _build_ui(self):
        self.style = ttk.Style(self)
        ensure_control_styles(self.style)
        self._sensor_widgets = {}
        self._loop_widgets = {}
        self._overlay_cards = []
        self._theme_dark = False
        self._build_header_bar()

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=10, pady=10)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self._canvas = tk.Canvas(body, highlightthickness=0, borderwidth=0)
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

        sidebar = ttk.Frame(self._sf, width=280)
        self._sidebar = sidebar
        sidebar.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 10))
        self._build_connection(sidebar)
        self._build_logging(sidebar)
        self._build_flow_control(sidebar)
        self._theme_btn = ttk.Button(sidebar, text="Dark Mode", command=self._toggle_theme)
        self._theme_btn.pack(fill="x", pady=(6, 0))
        self._apparatus_tile = build_apparatus_tile(sidebar, self.config.APPARATUS_IMAGE)
        logo = ttk.Frame(sidebar)
        logo.pack(fill="x", pady=(12, 0))
        with Image.open(self.config.LOGO_FILE) as source:
            image = source.convert("RGBA")
            image.thumbnail((160, 115), Image.Resampling.LANCZOS)
            self._logo_img = ImageTk.PhotoImage(image)
        self._logo_label = ttk.Label(logo, image=self._logo_img, anchor="center")
        self._logo_label.pack(fill="x")
        ttk.Label(logo, text="BYU TIPICE", font=("Helvetica", 18, "bold"), anchor="center").pack(fill="x", pady=(4, 0))

        # Keep the diagram/pressures together while the taller sidebar scrolls.
        self._diagram_column = ttk.Frame(self._sf)
        self._diagram_column.grid(row=0, column=1, rowspan=2, sticky="new")
        self._diagram_column.columnconfigure(0, weight=1)
        self._diagram_column.rowconfigure(0, weight=1)
        self._diagram_column.grid_propagate(False)
        diagram = ttk.LabelFrame(self._diagram_column, text="Piping and Instrumentation Diagram", padding=8)
        diagram.grid(row=0, column=0, sticky="nsew")
        self._diagram_panel = diagram
        self._pid = tk.Canvas(diagram, width=1080, height=410, bg="white", highlightthickness=0, borderwidth=0)
        self._pid.pack(fill="both", expand=True)
        with Image.open(self.config.PID_IMAGE) as source:
            self._diagram_image = source.convert("RGB")
        self._diagram_item = self._pid.create_image(0, 0, anchor="nw")

        # The four dashed pressure taps in the supplied drawing, left to right.
        self._delta_overlays = []
        for x, key in zip((304, 596, 777, 951), self.config.DELTA_P_KEYS):
            sensor = self.sensors[key]
            card = tk.Frame(self._pid, bg="white")
            tk.Label(card, text=f"{sensor.label} ({sensor.unit})", bg="white", fg="#263238",
                     font=("Helvetica", 11, "bold")).pack()
            entry = ttk.Entry(card, textvariable=sensor.value_var, width=10,
                              justify="center", state="readonly")
            entry.pack(pady=(3, 0))
            item = self._pid.create_window(0, 0, window=card, anchor="n")
            self._overlay_cards.append(card)
            self._delta_overlays.append((x, item))
            self._sensor_widgets[key] = {"entry": entry}

        indicator = tk.Frame(self._pid, bg="white")
        tk.Label(indicator, text="Rotameter", bg="white", fg="#263238",
                 font=("Helvetica", 11, "bold")).pack()
        self._rotameter_text = tk.StringVar(self, value="Indicator Only")
        self._rotameter_entry = ttk.Entry(
            indicator, textvariable=self._rotameter_text, width=14, justify="center", state="readonly")
        self._rotameter_entry.pack(pady=(3, 0))
        self._rotameter_overlay = self._pid.create_window(0, 0, window=indicator, anchor="n")
        self._overlay_cards.append(indicator)

        flow_card = tk.Frame(self._pid, bg="white")
        tk.Label(flow_card, text="Flow (SCFM)", bg="white", fg="#263238",
                 font=("Helvetica", 11, "bold")).pack()
        self._flow_entry = ttk.Entry(flow_card, textvariable=self.loops["flowrate"].measured_var,
                                     width=10, justify="center", state="readonly")
        self._flow_entry.pack(pady=(3, 0))
        self._flow_overlay = self._pid.create_window(0, 0, window=flow_card, anchor="n")
        self._overlay_cards.append(flow_card)

        valve_card = tk.Frame(self._pid, bg="white")
        tk.Label(valve_card, text="Valve (%)", bg="white", fg="#263238",
                 font=("Helvetica", 11, "bold")).pack()
        self._valve_entry = ttk.Entry(valve_card, textvariable=self.loops["flowrate"].rounded_valve_position,
                                      width=8, justify="center", state="readonly")
        self._valve_entry.pack(pady=(3, 0))
        self._valve_overlay = self._pid.create_window(0, 0, window=valve_card, anchor="e")
        self._overlay_cards.append(valve_card)

        self._temperature_overlays = []
        self._temperature_entries = {}
        for number, x in enumerate((513, 693, 867, 1041), start=1):
            key = f"temperature_{number}"
            card = tk.Frame(self._pid, bg="white")
            entry = ttk.Entry(card, textvariable=self.sensors[key].value_var, width=8,
                              justify="center", state="readonly", font=("Helvetica", 11, "bold"))
            entry.pack(side="left")
            tk.Label(card, text="°C", bg="white", fg="#263238",
                     font=("Helvetica", 11, "bold")).pack(side="left", padx=(4, 0))
            item = self._pid.create_window(0, 0, window=card, anchor="s")
            self._overlay_cards.append(card)
            self._temperature_overlays.append((x, item))
            self._temperature_entries[key] = entry
            self._sensor_widgets[key] = {"entry": entry}
        self._pid.bind("<Configure>", self._resize_diagram)
        scale = max(
            readout_row_scale([(x, self._pid.nametowidget(self._pid.itemcget(item, "window")))
                               for x, item in self._delta_overlays] +
                              [(435, flow_card), (1119, indicator)]),
            readout_row_scale([(x, self._pid.nametowidget(self._pid.itemcget(item, "window")))
                               for x, item in self._temperature_overlays]),
        )
        w, h = self._diagram_image.size
        margin = max(32, self._rotameter_entry.winfo_reqwidth() / 2 + 8)
        self._pid.configure(width=max(1080, ceil(w * scale + 2 * margin)),
                            height=max(410, ceil(h * scale + 74)))

        entrance = ttk.LabelFrame(self._diagram_column, text="Entrance Pressures (psi)", padding=(12, 20))
        entrance.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._entrance_panel = entrance
        for col, key in enumerate(self.config.ENTRANCE_PRESSURE_KEYS):
            self._sensor_cell(entrance, key, col, self.sensors[key].label)

    def _resize_body(self, event):
        right_width = max(self._diagram_panel.winfo_reqwidth(), self._entrance_panel.winfo_reqwidth())
        min_width = self._sidebar.winfo_reqwidth() + 10 + right_width
        self._diagram_column.configure(
            width=right_width,
            height=max(event.height, self._diagram_panel.winfo_reqheight() +
                       self._entrance_panel.winfo_reqheight() + 8))
        self._canvas.itemconfigure(self._sf_window, width=max(1280, min_width, event.width),
                                   height=max(self._sf.winfo_reqheight(), event.height))

    def _resize_diagram(self, event):
        # Keep the complete drawing in proportion and reserve a band for ΔP cards.
        w, h = self._diagram_image.size
        # Reserve space for the rotameter card centered under the rightmost pipe.
        margin = max(32, self._rotameter_entry.winfo_reqwidth() / 2 + 8)
        scale = max(0.01, min((event.width - 2 * margin) / w, (event.height - 74) / h))
        width, height = max(1, round(w * scale)), max(1, round(h * scale))
        left = (event.width - width) / 2
        top = max(0, (event.height - height - 74) / 2)
        self._bg_img = ImageTk.PhotoImage(self._diagram_image.resize((width, height), Image.Resampling.LANCZOS))
        self._pid.itemconfigure(self._diagram_item, image=self._bg_img)
        self._pid.coords(self._diagram_item, left, top)
        for x, item in self._delta_overlays:
            self._pid.coords(item, left + x * scale, top + 294 * scale)
        self._pid.coords(self._rotameter_overlay,
                         left + 1119 * scale, top + 294 * scale)
        self._pid.coords(self._flow_overlay, left + 435 * scale, top + 294 * scale)
        # Align the valve value (rather than the whole label/value card) with its tap.
        valve_center = self._valve_entry.winfo_y() + self._valve_entry.winfo_reqheight() / 2
        self._pid.coords(self._valve_overlay, left + 177 * scale,
                         top + 170 * scale - valve_center + self._valve_entry.master.winfo_reqheight() / 2)
        for number, (x, item) in enumerate(self._temperature_overlays, start=1):
            entry = self._temperature_entries[f"temperature_{number}"]
            card_width = entry.master.winfo_reqwidth()
            card_left = left + x * scale - entry.winfo_reqwidth() / 2
            if number == 4:
                # Keep the entire card clear of the rotameter at the upper right.
                card_left = min(card_left, left + 1105 * scale - card_width - 8)
            self._pid.itemconfigure(item, anchor="sw")
            self._pid.coords(item, card_left, top + 169 * scale)

    def _sensor_cell(self, panel, key, col, label=None):
        sensor = self.sensors[key]
        panel.columnconfigure(col, weight=1, uniform="readings")
        ttk.Label(panel, text=label or f"{sensor.label} ({sensor.unit})").grid(row=0, column=col, padx=6)
        entry = ttk.Entry(panel, textvariable=sensor.value_var, state="readonly", width=10, justify="center")
        entry.grid(row=1, column=col, sticky="ew", padx=6, pady=(5, 3))
        self._sensor_widgets[key] = {"entry": entry}

    def _build_connection(self, parent):
        panel = ttk.LabelFrame(parent, text="Controls", padding=(12, 8))
        panel.pack(fill="x", pady=(0, 8))
        ttk.OptionMenu(panel, self._connection_var, "Connect to LabJack", "USB", "Ethernet", "Disconnect",
                       command=self._on_connection_choice).pack(fill="x")
        self._connection_status = ttk.Label(panel, text="Not connected")
        self._connection_status.pack(fill="x", pady=4)

    def _build_flow_control(self, parent):
        loop = self.loops["flowrate"]
        panel = ttk.LabelFrame(parent, text=loop.label, padding=(16, 14))
        panel.pack(fill="x", pady=(0, 8))
        panel.columnconfigure(1, weight=1)
        widgets = {"frame": panel}
        ttk.Label(panel, text="Setpoint (SCFM)").grid(row=0, column=0, sticky="w", pady=6)
        widgets["setpoint_spinbox"] = ttk.Spinbox(panel, from_=0, to=350, textvariable=loop.setpoint_var, width=9)
        widgets["setpoint_spinbox"].grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=4)
        ttk.Label(panel, text="Measured (SCFM)").grid(row=1, column=0, sticky="w", pady=6)
        widgets["measured_entry"] = ttk.Entry(panel, textvariable=loop.measured_var, width=9, state="readonly")
        widgets["measured_entry"].grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=4)
        self._auto_var = tk.BooleanVar(value=False)
        widgets["mode_switch"] = ttk.Checkbutton(panel, text="Mode: MANUAL", style="Switch",
                                                   variable=self._auto_var, command=self._toggle_mode)
        widgets["mode_switch"].grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 12))
        ttk.Label(panel, text="Valve Command (%)").grid(row=3, column=0, columnspan=2, sticky="w")
        manual = ttk.Frame(panel)
        manual.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 12))
        manual.columnconfigure(0, weight=1)
        widgets["scale"] = ttk.Scale(manual, from_=0, to=100, variable=loop.valve_position)
        widgets["scale"].grid(row=0, column=0, sticky="ew")
        widgets["manual_spinbox"] = ttk.Spinbox(manual, from_=0, to=100, textvariable=loop.rounded_valve_position, width=6)
        widgets["manual_spinbox"].grid(row=0, column=1, sticky="e", padx=(8, 0))
        loop.valve_position.trace_add("write", self._sync_manual_slider)
        for event in ("<Return>", "<FocusOut>", "<<Increment>>", "<<Decrement>>"):
            widgets["manual_spinbox"].bind(event, self._commit_manual)

        tuning = ttk.Frame(panel)
        tuning.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        for col, (key, label, var, low) in enumerate((
            ("Kc", "Kc", loop.Kc_var, -1000),
            ("Ti", "Ti (min)", loop.Ti_var, 0),
            ("Td", "Td (min)", loop.Td_var, 0),
        )):
            tuning.columnconfigure(col, weight=1)
            ttk.Label(tuning, text=label).grid(row=0, column=col, padx=3)
            sb = ttk.Spinbox(tuning, from_=low, to=1000, textvariable=var, width=6)
            sb.grid(row=1, column=col, padx=3, pady=3, sticky="ew")
            widgets[f"{key}_spinbox"] = sb
        self._loop_widgets["flowrate"] = widgets

    def _sync_manual_slider(self, *_):
        loop = self.loops["flowrate"]
        loop.rounded_valve_position.set(round(max(0, min(100, finite_number(loop.valve_position.get())))))

    def _commit_manual(self, event=None):
        loop = self.loops["flowrate"]
        try:
            percent = round(max(0, min(100, finite_number(self._loop_widgets["flowrate"]["manual_spinbox"].get()))))
        except (ValueError, tk.TclError):
            percent = round(loop.valve_position.get())
        loop.valve_position.set(percent)

    def _toggle_mode(self):
        loop = self.loops["flowrate"]
        loop.is_auto = self._auto_var.get()
        if loop.is_auto:
            loop.pid.initialize(loop.get_manual_voltage())
        else:
            loop.pid.reset()
        widgets = self._loop_widgets["flowrate"]
        widgets["mode_switch"].configure(text="Mode: AUTO" if loop.is_auto else "Mode: MANUAL")
        enable_loop_widgets(widgets, loop)

    def _build_logging(self, parent):
        panel = ttk.LabelFrame(parent, text="Data Logging", padding=(12, 8))
        panel.pack(fill="x", pady=(0, 8))
        row = ttk.Frame(panel)
        row.pack(fill="x", pady=(0, 6))
        ttk.Label(row, text="Experiment ID").pack(side="left")
        self._experiment_id_entry = ttk.Entry(row, textvariable=self._experiment_id_var, width=18)
        self._experiment_id_entry.pack(side="right")
        self._toggle_logging_btn = ttk.Checkbutton(panel, textvariable=self._logging_text_var,
                                                   style="ToggleButton", command=self._on_toggle_logging)
        self._toggle_logging_btn.pack(fill="x", pady=(0, 6))
        for label, var, editable in (("Interval (s)", self._log_interval_var, True),
                                     ("Data Point Count", self._data_point_count, False)):
            row = ttk.Frame(panel)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label).pack(side="left")
            if editable:
                ttk.Spinbox(row, from_=0.1, to=100, textvariable=var, width=7).pack(side="right")
            else:
                ttk.Entry(row, textvariable=var, state="readonly", width=7).pack(side="right")

    def _toggle_theme(self):
        self._theme_dark = not self._theme_dark
        name = "forest-dark" if self._theme_dark else "forest-light"
        if name in self.style.theme_names():
            self.style.theme_use(name)
        self._theme_btn.configure(text="Light Mode" if self._theme_dark else "Dark Mode")
        self._canvas.configure(bg=self.style.lookup("TFrame", "background"))

    def _on_connection_choice(self, choice):
        if choice == "Ethernet" and not self.config.ETHERNET_ADDRESS:
            address = simpledialog.askstring("Ethernet Connection", "Airflow LabJack IP address or serial number:",
                                             parent=self.winfo_toplevel())
            if address and address.strip():
                self._connect("T7", "ETHERNET", address.strip())
            else:
                self._connection_var.set("Connect to LabJack")
            return
        super()._on_connection_choice(choice)

    def _connect(self, model, connection, identifier):
        # Reconnecting first shuts down the previous session and valve command.
        if self.daq.is_connected:
            self._disconnect()
        self.daq.safety.register_safe_output("DAC0", 0.0)
        super()._connect(model, connection, identifier)
        if str(self._status_lbl.cget("text")) != "CONNECTED":
            self._disconnect()
            self._status_lbl.configure(text="CONNECTION FAILED")

    def _disable_powered_controls(self):
        super()._disable_powered_controls()
        loop = self.loops["flowrate"]
        loop.is_auto = False
        loop.pid.reset()
        loop.set_valve_display(0)
        self._auto_var.set(False)
        self._loop_widgets["flowrate"]["mode_switch"].configure(text="Mode: MANUAL")
        self._toggle_logging_btn.state(["!selected"])

    def _disconnect(self):
        super()._disconnect()
        for sensor in self.sensors.values():
            sensor.value_var.set("---")
        self.loops["flowrate"].measured_var.set("---")

    def _update_all_sensors(self):
        if not self._polling:
            return
        if not self.daq.is_connected:
            self.after(UPDATE_INTERVAL_MS, self._update_all_sensors)
            return
        # Invalidate compensation before each read so failures cannot reuse stale CJC.
        self.config._cj_temp_c[0] = float("nan")
        super()._update_all_sensors()

    def _update_all_loops(self):
        if not self._polling:
            return
        if not self.daq.is_connected:
            self.after(UPDATE_INTERVAL_MS, self._update_all_loops)
            return
        loop = self.loops["flowrate"]
        if not loop.is_auto:
            # Spinbox limits do not constrain typed/pasted values. Bound the
            # actual command before the shared loop converts percent to volts.
            try:
                percent = loop.rounded_valve_position.get()
                bounded = max(0, min(100, percent))
                if bounded != percent:
                    loop.valve_position.set(bounded)
            except (ValueError, tk.TclError):
                pass  # Shared loop rejects incomplete numeric edits.
        super()._update_all_loops()

    def destroy(self):
        # Cancel callbacks before destroying their Tcl commands when leaving a screen.
        self._polling = False
        if hasattr(self, "logger"):
            self._disconnect()
        for callback in self.tk.call("after", "info"):
            script = str(self.tk.call("after", "info", callback)[0])
            if any(script.startswith(command) for command in self._tclCommands or ()):
                self.after_cancel(callback)
        super().destroy()
