# base_app.py
# Unified Base Application frame that dynamically loads and displays
# an apparatus configuration.

import tkinter as tk
from tkinter import ttk, messagebox
import os
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[Warning] Pillow not found — images will be blank placeholders.")

from core.sensor import Sensor
from core.control_loop import ControlLoop
from core.pid_controller import PIDController
from core.ui_builders import (
    build_sensor_display,
    build_control_loop_panel,
    enable_loop_widgets,
    disable_loop_widgets,
)
from core.data_logger import DataLogger

UPDATE_INTERVAL_MS = 500
DT_MINUTES = UPDATE_INTERVAL_MS / 1000 / 60


class BaseAppFrame(ttk.Frame):
    """
    Dynamic GUI panel that builds itself from a configuration module.
    """

    def __init__(self, parent, config, daq, on_back=None):
        super().__init__(parent)
        self.config = config
        self.daq = daq
        self.on_back = on_back

        self.sensors = self._build_sensors()
        self.loops = self._build_control_loops()

        # Tkinter variables
        self._connection_var = tk.StringVar(value="Connect to LabJack")
        self._main_power_var = tk.BooleanVar(value=False)
        self._main_power_on = False

        self._logging_text_var = tk.StringVar(value="Start Logging")
        self._log_interval_var = tk.DoubleVar(value=1.0)
        self._data_point_count = tk.IntVar(value=0)

        # Dynamic switches vars
        self._switch_vars = {}
        self._switch_widgets = []

        # Manual analog outputs vars
        self._manual_analog_vars = {}
        self._manual_analog_widgets = []

        # Build UI
        self._build_ui()
        self._set_initial_states()
        self._build_logger()

        # Start periodic updates
        self._polling = True
        self._schedule_updates()

    # ══════════════════════════════════════════════════════════════════
    # Initialisation helpers
    # ══════════════════════════════════════════════════════════════════

    def _build_sensors(self) -> dict:
        return {
            key: Sensor(
                key=key,
                label=cfg["label"],
                unit=cfg["unit"],
                pin=cfg["pin"],
                calibration=cfg["calibration"],
            )
            for key, cfg in getattr(self.config, "SENSOR_CONFIGS", {}).items()
        }

    def _build_control_loops(self) -> dict:
        loops = {}
        for key, cfg in getattr(self.config, "CONTROL_LOOP_CONFIGS", {}).items():
            pid_defaults = cfg.get("pid_defaults", {})
            pid = PIDController(
                Kc=pid_defaults.get("Kc", 1.0),
                Ti=pid_defaults.get("Ti", 1.0),
                Td=pid_defaults.get("Td", 0.0),
            )
            
            # Extract extra sensor keys
            extra_keys = cfg.get("extra_sensor_keys")
            extra_key = cfg.get("extra_sensor_key")
            
            loop = ControlLoop(
                key=key,
                label=cfg["label"],
                unit=cfg["unit"],
                input_pin=cfg["input_pin"],
                output_pin=cfg["output_pin"],
                calibration=cfg["calibration"],
                setpoint_min=cfg.get("setpoint_min", 0.0),
                setpoint_max=cfg.get("setpoint_max", 100.0),
                pid=pid,
                extra_sensor_keys=extra_keys,
                extra_sensor_key=extra_key,
            )
            
            # Set loop gating if defined
            if "gate_switch" in cfg:
                loop.gate_switch = cfg["gate_switch"]
                loop.gate_value = cfg.get("gate_value", True)
                
            # Seed setpoint default
            loop.setpoint_var.set(str(cfg.get("default_setpoint", 0.0)))
            loops[key] = loop
        return loops

    def _build_logger(self):
        sources = {}
        for header, (kind, key) in getattr(self.config, "LOG_COLUMNS", {}).items():
            if kind == "sensor" and key in self.sensors:
                var = self.sensors[key].value_var
            elif kind == "loop" and key in self.loops:
                var = self.loops[key].measured_var
            else:
                continue
            sources[header] = var.get

        self.logger = DataLogger(
            sources=sources,
            folder=getattr(self.config, "LOG_FOLDER", "LoggedData"),
            count_var=self._data_point_count,
        )

    # ══════════════════════════════════════════════════════════════════
    # GUI construction
    # ══════════════════════════════════════════════════════════════════

    def _build_ui(self):
        # Configure grid expansion
        self._sensor_widgets = {}

        # Header Bar
        self._build_header_bar()

        # Main Body container (scrollable frame)
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        # Canvas
        self._canvas = tk.Canvas(body)
        self._canvas.grid(row=0, column=0, sticky="nsew")

        # Scrollbars
        v_scrollbar = ttk.Scrollbar(body, orient="vertical")
        v_scrollbar.grid(row=0, column=1, sticky="ns")

        h_scrollbar = ttk.Scrollbar(body, orient="horizontal")
        h_scrollbar.grid(row=1, column=0, sticky="ew")

        # Configure body grid weights to let canvas expand
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        # Configure scrollbars and canvas scrolling
        v_scrollbar.config(command=self._canvas.yview)
        h_scrollbar.config(command=self._canvas.xview)
        self._canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        self._sf = ttk.Frame(self._canvas)
        self._canvas.create_window((0, 0), window=self._sf, anchor="nw")
        
        self._sf.bind("<Configure>", lambda e: self._canvas.configure(
            scrollregion=self._canvas.bbox("all")
        ))
        
        self._sf.bind("<Enter>", lambda e: self.bind_all("<MouseWheel>", self._on_mousewheel))
        self._sf.bind("<Leave>", lambda e: self.unbind_all("<MouseWheel>"))

        # ── Controls Frame ──
        c_row = getattr(self.config, "CONTROLS_ROW", 0)
        c_col = getattr(self.config, "CONTROLS_COL", 0)
        self._build_controls_frame(self._sf, c_row, c_col)

        # ── Logo Frame ──
        l_row = getattr(self.config, "LOGO_ROW", 1)
        l_col = getattr(self.config, "LOGO_COL", 0)
        l_colspan = getattr(self.config, "LOGO_COLSPAN", 1)
        self._build_logo_frame(self._sf, l_row, l_col, l_colspan)

        # ── Apparatus Image Frame (Optional) ──
        img_file = getattr(self.config, "APPARATUS_IMAGE", None)
        if img_file and os.path.exists(img_file):
            img_row = getattr(self.config, "APPARATUS_IMAGE_ROW", 2)
            img_col = getattr(self.config, "APPARATUS_IMAGE_COL", 0)
            img_colspan = getattr(self.config, "APPARATUS_IMAGE_COLSPAN", 1)
            self._build_apparatus_image(self._sf, img_file, img_row, img_col, img_colspan)

        # ── Data Logging Frame ──
        dl_row = getattr(self.config, "DATA_LOGGING_ROW", 0)
        dl_col = getattr(self.config, "DATA_LOGGING_COL", 1)
        dl_colspan = getattr(self.config, "DATA_LOGGING_COLSPAN", 2)
        self._build_data_logging_frame(self._sf, dl_row, dl_col, dl_colspan)

        # ── Manual Analog Outputs Panel (Optional) ──
        mao_panel_cfg = getattr(self.config, "MANUAL_ANALOG_OUTPUTS_PANEL", None)
        if mao_panel_cfg:
            self._build_manual_analog_outputs_panel(self._sf, mao_panel_cfg)

        # ── Sensor Panels ──
        sensor_panels = getattr(self.config, "SENSOR_PANELS", [])
        for sp in sensor_panels:
            self._build_sensor_panel(self._sf, sp)

        # ── Control Loop Panels ──
        self._loop_widgets = {}
        loop_rows = getattr(self.config, "LOOP_ROWS", None)
        
        # If no loop rows are explicitly defined, stack them vertically in column 3
        if loop_rows is None:
            loop_rows = {k: idx for idx, k in enumerate(self.loops.keys())}
            
        for key, row in loop_rows.items():
            if key in self.loops:
                widgets = build_control_loop_panel(
                    self._sf, self.loops[key], self.sensors,
                    row=row, col=3, columnspan=3, root=self.winfo_toplevel()
                )
                self._loop_widgets[key] = widgets

    def _build_header_bar(self):
        bar = ttk.Frame(self, relief="raised", borderwidth=1)
        bar.pack(fill="x", side="top")

        # Back Button
        btn = ttk.Button(bar, text="← Dashboard", command=self._go_back)
        btn.pack(side="left", padx=10, pady=5)

        # Title
        title_lbl = ttk.Label(
            bar, text=self.config.SYSTEM_NAME,
            font=("Helvetica", 14, "bold")
        )
        title_lbl.pack(side="left", padx=20, pady=5)

        # Connection status badge
        self._status_lbl = ttk.Label(
            bar, text="DISCONNECTED",
            foreground="red", font=("Helvetica", 10, "bold")
        )
        self._status_lbl.pack(side="right", padx=15, pady=5)

    def _build_controls_frame(self, parent, row, col):
        f = ttk.LabelFrame(parent, text="Controls", padding=(20, 10))
        f.grid(row=row, column=col, padx=(20, 10), pady=(10, 10), sticky="nsew")

        # Connection Selection
        self._connect_dropdown = ttk.OptionMenu(
            f, self._connection_var,
            "Connect to LabJack",
            "USB", "Ethernet", "Disconnect",
            command=self._on_connection_choice,
        )
        self._connect_dropdown.grid(row=0, column=0, padx=5, pady=(10, 5), sticky="nsew")

        self._connection_status = ttk.Label(f, text="Not connected", padding=(5, 5))
        self._connection_status.grid(row=1, column=0, padx=5, pady=0, sticky="nsew")

        # Main Power Switch
        self._power_switch = ttk.Checkbutton(
            f, text="Main Power: OFF", style="Switch",
            variable=self._main_power_var,
            command=self._on_power_toggle,
        )
        self._power_switch.grid(row=2, column=0, padx=5, pady=10, sticky="nsew")

        # Dynamic System Switches (e.g. Pump, Column Selector)
        switches = getattr(self.config, "SYSTEM_SWITCHES", [])
        for idx, sw in enumerate(switches):
            key = sw["key"]
            label = sw["label"]
            sw_type = sw.get("type", "toggle")

            if sw_type == "toggle":
                var = tk.BooleanVar(value=bool(sw.get("default", False)))
                self._switch_vars[key] = var

                chk = ttk.Checkbutton(
                    f, text=f"{label}: OFF", style="Switch",
                    variable=var,
                    command=lambda k=key, s=sw: self._on_toggle_switch(k, s)
                )
                chk.grid(row=3 + idx, column=0, padx=5, pady=10, sticky="nsew")
                self._switch_widgets.append((chk, label))

            elif sw_type == "radio":
                var = tk.BooleanVar(value=bool(sw.get("default", True)))
                self._switch_vars[key] = var

                # Build option frame
                rf = ttk.Frame(f)
                rf.grid(row=3 + idx, column=0, padx=5, pady=10, sticky="nsew")
                
                ttk.Label(rf, text=label, font=("Helvetica", 9, "bold")).grid(
                    row=0, column=0, columnspan=2, padx=5, pady=(5, 5), sticky="w"
                )
                
                options = sw.get("options", [])
                for opt_idx, (opt_lbl, opt_val, *_) in enumerate(options):
                    rad = ttk.Radiobutton(
                        rf, text=opt_lbl,
                        variable=var, value=bool(opt_val),
                        command=lambda k=key, s=sw: self._on_radio_switch(k, s)
                    )
                    rad.grid(row=1 + opt_idx, column=0, padx=5, pady=5, sticky="w")
                    self._switch_widgets.append((rad, None))

    def _build_logo_frame(self, parent, row, col, columnspan):
        f = ttk.Frame(parent)
        f.grid(row=row, column=col, columnspan=columnspan, padx=(20, 10), pady=(10, 10), sticky="nsew")

        # Logo Image
        logo_path = getattr(self.config, "LOGO_FILE", "assets/tipice_logo.png")
        try:
            self._logo_img = tk.PhotoImage(file=logo_path)
            ttk.Label(f, image=self._logo_img).grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        except Exception:
            ttk.Label(f, text="[logo]").grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        # Department text
        dept_text = "BYU TIPICE"
        ttk.Label(f, text=dept_text, font=("Copperplate Gothic Bold", 35), wraplength=200).grid(
            row=0, column=1, padx=(10, 10), pady=5, sticky="nsew"
        )
        self._logo_frame = f

    def _build_apparatus_image(self, parent, img_path, row, col, columnspan):
        f = ttk.LabelFrame(parent, text="Apparatus Diagram", padding=(10, 10))
        f.grid(row=row, column=col, columnspan=columnspan, padx=(20, 10), pady=(10, 10), sticky="nsew")
        
        if PIL_AVAILABLE:
            try:
                img = Image.open(img_path)
                img = img.resize((200, 200))
                self._apparatus_photo = ImageTk.PhotoImage(img)
                lbl = ttk.Label(f, image=self._apparatus_photo, anchor="center")
                lbl.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
            except Exception as e:
                print(f"Error loading apparatus image {img_path}: {e}")
                ttk.Label(f, text="[Image Not Found]").grid(row=0, column=0, padx=5, pady=5)
        else:
            ttk.Label(f, text="[Install Pillow to view image]").grid(row=0, column=0, padx=5, pady=5)

    def _build_data_logging_frame(self, parent, row, col, columnspan):
        f = ttk.LabelFrame(parent, text="Data Logging", padding=(20, 10))
        f.grid(row=row, column=col, columnspan=columnspan, padx=(10, 10), pady=(10, 10), sticky="nsew")

        self._toggle_logging_btn = ttk.Checkbutton(
            f, textvariable=self._logging_text_var,
            style="ToggleButton", command=self._on_toggle_logging,
            padding=(20, 20), state="disabled",
        )
        self._toggle_logging_btn.grid(row=0, rowspan=4, column=0, padx=20, pady=(20, 5), sticky="nsew")
        
        ttk.Label(f, text="Interval (s)").grid(row=0, column=1, padx=5, pady=(20, 5), sticky="nsew")
        ttk.Spinbox(
            f, from_=0.1, to=100.0, textvariable=self._log_interval_var,
            width=5, state="normal",
        ).grid(row=1, column=1, padx=5, pady=5, sticky="nsew")

        ttk.Label(f, text="Data Point Count").grid(row=2, column=1, padx=5, pady=5, sticky="nsew")
        self._data_point_entry = ttk.Entry(
            f, textvariable=self._data_point_count, state="disabled", width=8
        )
        self._data_point_entry.grid(row=3, column=1, padx=5, pady=5, sticky="nsew")

    def _build_sensor_panel(self, parent, sp_cfg):
        title = sp_cfg["title"]
        row = sp_cfg["row"]
        col = sp_cfg["col"]
        colspan = sp_cfg.get("columnspan", 1)
        grid_cols = sp_cfg.get("columns", 1)

        f = ttk.LabelFrame(parent, text=title, padding=(10, 10))
        f.grid(row=row, column=col, columnspan=colspan, padx=(10, 10), pady=(10, 10), sticky="nsew")

        for idx, key in enumerate(sp_cfg["sensors"]):
            if key not in self.sensors:
                continue
            grid_row = (idx // grid_cols) * 2
            grid_col = idx % grid_cols
            w = build_sensor_display(f, self.sensors[key], row=grid_row, col=grid_col)
            self._sensor_widgets[key] = w

    def _build_manual_analog_outputs_panel(self, parent, panel_cfg):
        title = panel_cfg["title"]
        row = panel_cfg["row"]
        col = panel_cfg["col"]
        colspan = panel_cfg.get("columnspan", 1)

        f = ttk.LabelFrame(parent, text=title, padding=(20, 10))
        f.grid(row=row, column=col, columnspan=colspan, padx=(20, 10), pady=(10, 10), sticky="nsew")

        outputs = panel_cfg.get("outputs", [])
        
        # Build manual controls
        for idx, key in enumerate(outputs):
            cfg = self.config.MANUAL_ANALOG_OUTPUTS.get(key)
            if not cfg:
                continue
            
            lbl = cfg["label"]
            unit = cfg.get("unit", "V")
            min_val = cfg.get("min_val", 0.0)
            max_val = cfg.get("max_val", 5.0)
            default_val = cfg.get("default", 0.0)
            
            ttk.Label(f, text=f"{lbl} ({unit})").grid(row=idx * 2, column=0, padx=5, pady=0, sticky="nsew")
            
            var = tk.StringVar(value=str(default_val))
            self._manual_analog_vars[key] = var
            
            sb = ttk.Spinbox(
                f, from_=min_val, to=max_val, textvariable=var,
                width=5, state="disabled",
            )
            sb.grid(row=idx * 2 + 1, column=0, padx=5, pady=(5, 10), sticky="nsew")
            self._manual_analog_widgets.append(sb)

        # Embedded read-only sensors
        sensors = panel_cfg.get("sensors", [])
        for idx, key in enumerate(sensors):
            if key in self.sensors:
                # Place below the output spinboxes
                w = build_sensor_display(f, self.sensors[key], row=len(outputs) * 2 + idx * 2, col=0)
                self._sensor_widgets[key] = w

    # ══════════════════════════════════════════════════════════════════
    # Power / enable / disable
    # ══════════════════════════════════════════════════════════════════

    def _set_initial_states(self):
        """Disable everything until LabJack is connected."""
        self._power_switch.configure(state="disabled")
        self._toggle_logging_btn.configure(state="disabled")
        
        for w in self._switch_widgets:
            w[0].configure(state="disabled")
            
        for w in self._manual_analog_widgets:
            w.configure(state="disabled")
            
        for kw in self._loop_widgets.values():
            disable_loop_widgets(kw)

    def _enable_powered_controls(self):
        """Enable controls when main power is turned ON."""
        self._toggle_logging_btn.configure(state="normal")
        
        for w in self._switch_widgets:
            w[0].configure(state="normal")
            
        for w in self._manual_analog_widgets:
            w.configure(state="normal")
            
        for kw in self._loop_widgets.values():
            enable_loop_widgets(kw)

    def _disable_powered_controls(self):
        """Disable controls and reset outputs to safe states when power is OFF."""
        self._toggle_logging_btn.configure(state="disabled")
        
        for w in self._switch_widgets:
            w[0].configure(state="disabled")
            
        for w in self._manual_analog_widgets:
            w.configure(state="disabled")
            
        for kw in self._loop_widgets.values():
            disable_loop_widgets(kw)

        # Stop logging if running
        if self.logger.is_logging:
            self.logger.stop()
            self._logging_text_var.set("Start Logging")
            self._data_point_count.set(0)

        # Reset switch variables to false and update label texts
        for key, var in self._switch_vars.items():
            var.set(False)
            
        for widget, label in self._switch_widgets:
            if label is not None:
                widget.config(text=f"{label}: OFF")

        # Zero all physical outputs on LabJack (if connected)
        if self.daq.is_connected:
            # Main power pin
            main_power_pin = getattr(self.config, "MAIN_POWER_PIN", None)
            if main_power_pin and main_power_pin != "TODO" and main_power_pin != "":
                self.daq.write(main_power_pin, 0.0)
            
            # Other digital outputs
            switches = getattr(self.config, "SYSTEM_SWITCHES", [])
            for sw in switches:
                pin = sw.get("pin")
                if pin:
                    inactive_val = sw.get("inactive_value", 0.0)
                    self.daq.write(pin, inactive_val)
                    
            # Loop output pins
            for loop in self.loops.values():
                self.daq.write(loop.output_pin, 0.0)
                loop.set_valve_display(0.0)
                
            # Manual analog outputs
            mao_panel_cfg = getattr(self.config, "MANUAL_ANALOG_OUTPUTS_PANEL", None)
            if mao_panel_cfg:
                for key in mao_panel_cfg.get("outputs", []):
                    cfg = self.config.MANUAL_ANALOG_OUTPUTS.get(key)
                    if cfg:
                        self.daq.write(cfg["pin"], 0.0)

    # ══════════════════════════════════════════════════════════════════
    # Event callbacks
    # ══════════════════════════════════════════════════════════════════

    def _on_connection_choice(self, choice):
        if choice == "USB":
            self._connect("T7", "USB", "ANY")
        elif choice == "Ethernet":
            self._connect("T7", "ETHERNET", self.config.ETHERNET_ADDRESS)
        elif choice == "Disconnect":
            self._disconnect()

    def _connect(self, model, connection, identifier):
        try:
            self.daq.connect(model, connection, identifier)
            
            # Configure channels (AIN settings) if specified
            ain_configs = getattr(self.config, "AIN_CONFIGS", {})
            for ch, settings in ain_configs.items():
                for register, value in settings.items():
                    self.daq.write(f"{ch}_{register}", value)

            self._connection_status.config(text="Connected", style="Green.TLabel")
            self._status_lbl.config(text="CONNECTED", foreground="green")
            self._power_switch.configure(state="normal")
            
            # Write initial states of digital switches if device is connected but main power is off
            # (or wait until main power is on)
        except Exception as exc:
            self._connection_status.config(text=f"Failed: {exc}", style="Red.TLabel")
            self._status_lbl.config(text="CONNECTION FAILED", foreground="red")
            messagebox.showerror(
                "Connection Failed",
                f"Could not connect to LabJack at {identifier}.\n\nError: {exc}"
            )

    def _disconnect(self):
        self._main_power_on = False
        self._main_power_var.set(False)
        self._power_switch.config(text="Main Power: OFF")
        self._disable_powered_controls()
        
        self.daq.disconnect()
        
        self._connection_status.config(text="Disconnected", style="Green.TLabel")
        self._status_lbl.config(text="DISCONNECTED", foreground="red")
        self._power_switch.configure(state="disabled")

    def _on_power_toggle(self):
        self._main_power_on = not self._main_power_on
        if self._main_power_on:
            self._power_switch.config(text="Main Power: ON")
            main_power_pin = getattr(self.config, "MAIN_POWER_PIN", None)
            if main_power_pin and main_power_pin != "TODO" and main_power_pin != "":
                self.daq.write(main_power_pin, 1.0)
            self._enable_powered_controls()
        else:
            self._power_switch.config(text="Main Power: OFF")
            self._disable_powered_controls()

    def _on_toggle_switch(self, key, sw):
        var = self._switch_vars[key]
        state = var.get()
        
        for widget, label in self._switch_widgets:
            if label == sw["label"]:
                widget.config(text=f"{label}: {'ON' if state else 'OFF'}")
                break

        pin = sw.get("pin")
        if pin and self.daq.is_connected:
            active_val = sw.get("active_value", 1.0)
            inactive_val = sw.get("inactive_value", 0.0)
            val = active_val if state else inactive_val
            self.daq.write(pin, val)

    def _on_radio_switch(self, key, sw):
        var = self._switch_vars[key]
        state = var.get()
        pin = sw.get("pin")
        if pin and self.daq.is_connected:
            for label, s_val, p_val in sw.get("options", []):
                if s_val == state:
                    self.daq.write(pin, p_val)
                    break

    def _on_toggle_logging(self):
        if not self.logger.is_logging:
            self.logger.set_interval(self._log_interval_var.get())
            self.logger.start()
            self._logging_text_var.set("Stop Logging")
        else:
            self.logger.stop()
            self._logging_text_var.set("Start Logging")
            self._data_point_count.set(0)

    def _on_mousewheel(self, event):
        # Universal cross-platform mouse wheel scroll
        if event.delta in (1, -1):
            scroll = -event.delta * 3
        else:
            scroll = int(-1 * (event.delta / 120)) * 3
        self._canvas.yview_scroll(scroll, "units")

    # ══════════════════════════════════════════════════════════════════
    # Periodic update loop
    # ══════════════════════════════════════════════════════════════════

    def _schedule_updates(self):
        self.after(UPDATE_INTERVAL_MS, self._update_all_sensors)
        self.after(UPDATE_INTERVAL_MS, self._update_all_loops)
        self.after(UPDATE_INTERVAL_MS, self._update_manual_analog_outputs)

    def _update_all_sensors(self):
        if not self._polling:
            return

        # Update cold junction temperature for thermocouple compensation if defined
        cj_register = getattr(self.config, "COLD_JUNCTION_REGISTER", None)
        if cj_register and self.daq.is_connected:
            try:
                cj_k = self.daq.read(cj_register)
                if hasattr(self.config, "_cj_temp_c"):
                    self.config._cj_temp_c[0] = cj_k - 273.15
            except Exception:
                pass

        # Read and update all sensors
        for sensor in self.sensors.values():
            if not sensor.is_configured():
                sensor.set_error()
                continue
            try:
                raw = self.daq.read(sensor.pin)
                sensor.set_value(sensor.apply_calibration(raw))
            except Exception:
                sensor.set_error()

        self.after(UPDATE_INTERVAL_MS, self._update_all_sensors)

    def _update_all_loops(self):
        if not self._polling:
            return

        for key, loop in self.loops.items():
            # ── Read Process Variable ──
            try:
                raw = self.daq.read(loop.input_pin)
                loop.set_measured(loop.apply_calibration(raw))
            except Exception:
                loop.set_error()

            # ── Gating checks ──
            if hasattr(loop, "gate_switch") and loop.gate_switch in self._switch_vars:
                current_gate_val = self._switch_vars[loop.gate_switch].get()
                if current_gate_val != loop.gate_value:
                    continue  # Loop is inactive, don't write to output pin

            # ── Write Output ──
            try:
                if loop.is_auto:
                    sp = loop.get_setpoint()
                    meas = loop.get_measured()
                    if sp is not None and meas is not None:
                        loop.sync_tuning_to_pid()
                        u = loop.pid.compute(sp, meas, dt=DT_MINUTES)
                        self.daq.write(loop.output_pin, u)
                        loop.set_valve_display(u)
                else:
                    u = loop.get_manual_voltage()
                    self.daq.write(loop.output_pin, u)
            except Exception as exc:
                print(f"[Loop {key}] output error: {exc}")

        self.after(UPDATE_INTERVAL_MS, self._update_all_loops)

    def _update_manual_analog_outputs(self):
        if not self._polling:
            return

        for key, var in self._manual_analog_vars.items():
            cfg = self.config.MANUAL_ANALOG_OUTPUTS.get(key)
            if not cfg:
                continue
            
            try:
                setpoint_val = float(var.get())
                scale = cfg.get("scale", 1.0)
                voltage = setpoint_val / scale
                self.daq.write(cfg["pin"], voltage)
            except Exception as exc:
                print(f"[Manual Output {key}] write error: {exc}")

        self.after(UPDATE_INTERVAL_MS, self._update_manual_analog_outputs)

    # ══════════════════════════════════════════════════════════════════
    # Clean-up and Navigation
    # ══════════════════════════════════════════════════════════════════

    def _go_back(self):
        # Stop background polling loops
        self._polling = False
        
        # Turn off power safely and close LabJack interface
        self._disconnect()
        
        if self.on_back:
            self.on_back()
