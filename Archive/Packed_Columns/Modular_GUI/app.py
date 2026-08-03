# app.py
# PackedColumnsApp — the top-level application class.
#
# Responsibilities:
#   • Build Sensor and ControlLoop objects from config.py
#   • Assemble the GUI (scrollable canvas, panels)
#   • Run the periodic sensor-read / PID-update loop via root.after()
#   • Handle connection, power toggle, column selector, dark/light mode
#   • Wire the DataLogger to the live sensor / loop variables
#
# What this file does NOT contain:
#   • Calibration equations          → config.py
#   • Pin assignments                → config.py
#   • PID math                       → pid_controller.py
#   • Widget layout code             → ui_builders.py
#   • CSV writing                    → data_logger.py
#   • ljm calls                      → labjack_interface.py

import tkinter as tk
from tkinter import ttk

import config
from sensor import Sensor
from control_loop import ControlLoop
from pid_controller import PIDController
from labjack_interface import LabJackInterface
from data_logger import DataLogger
from ui_builders import (
    build_sensor_display,
    build_control_loop_panel,
    enable_loop_widgets,
    disable_loop_widgets,
)

# How often (ms) the sensor-read and PID-update callbacks fire.
UPDATE_INTERVAL_MS = 500
DT_MINUTES = UPDATE_INTERVAL_MS / 1000 / 60   # used by PID.compute()


class PackedColumnsApp:
    BASE_WIDTH  = 1600
    BASE_HEIGHT = 900

    def __init__(self):
        self.root = tk.Tk()
        self.root.geometry("1350x900")
        self.root.title(config.SYSTEM_NAME)
        self.root.option_add("*tearOff", False)

        # ── Hardware interface ─────────────────────────────────────────
        self.daq = LabJackInterface()

        # ── Build data objects from config ────────────────────────────
        self.sensors = self._build_sensors()
        self.loops   = self._build_control_loops()

        # ── Misc state ────────────────────────────────────────────────
        self._theme_mode     = tk.IntVar(value=0)   # 0 = light, 1 = dark
        self._connection_var = tk.StringVar(value="Connect to LabJack")
        self._main_power_on  = False
        self._main_power_var = tk.BooleanVar(value=False)
        self._col_select_var = tk.BooleanVar(value=True)   # True = Col 1

        # Logging state
        self._logging_text_var   = tk.StringVar(value="Start Logging")
        self._log_interval_var   = tk.DoubleVar(value=1.0)
        self._data_point_count   = tk.IntVar(value=0)

        # ── GUI setup ─────────────────────────────────────────────────
        self._configure_root()
        self._load_themes()
        self._build_ui()
        self._set_initial_states()
        self._build_logger()
        self._schedule_updates()

        self.root.mainloop()

    # ══════════════════════════════════════════════════════════════════
    # Initialisation helpers
    # ══════════════════════════════════════════════════════════════════

    def _build_sensors(self) -> dict:
        """Create one Sensor object per entry in SENSOR_CONFIGS."""
        return {
            key: Sensor(
                key=key,
                label=cfg["label"],
                unit=cfg["unit"],
                pin=cfg["pin"],
                calibration=cfg["calibration"],
            )
            for key, cfg in config.SENSOR_CONFIGS.items()
        }

    def _build_control_loops(self) -> dict:
        """Create one ControlLoop (with its PIDController) per entry in CONTROL_LOOP_CONFIGS."""
        loops = {}
        for key, cfg in config.CONTROL_LOOP_CONFIGS.items():
            pid_defaults = cfg.get("pid_defaults", {})
            pid = PIDController(
                Kc=pid_defaults.get("Kc", 1.0),
                Ti=pid_defaults.get("Ti", 1.0),
                Td=pid_defaults.get("Td", 0.0),
            )
            loops[key] = ControlLoop(
                key=key,
                label=cfg["label"],
                unit=cfg["unit"],
                input_pin=cfg["input_pin"],
                output_pin=cfg["output_pin"],
                calibration=cfg["calibration"],
                setpoint_min=cfg.get("setpoint_min", 0),
                setpoint_max=cfg.get("setpoint_max", 100),
                pid=pid,
                extra_sensor_key=cfg.get("extra_sensor_key"),
            )
            # Seed setpoint default
            loops[key].setpoint_var.set(str(cfg.get("default_setpoint", 0)))
        return loops

    def _configure_root(self):
        for i in range(3):
            self.root.columnconfigure(i, weight=1)
            self.root.rowconfigure(i, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        scalef = min(sw / self.BASE_WIDTH, sh / self.BASE_HEIGHT)
        self.root.tk.eval(f"set scalef {scalef:.3f}")
        self.root.tk.call("source", "assets/forest-dark.tcl")
        self.root.tk.call("source", "assets/forest-light.tcl")

    def _load_themes(self):
        self.style = ttk.Style()
        self.style.theme_use("forest-light")
        self.style.configure("Green.TLabel", foreground="green")
        self.style.configure("Red.TLabel",   foreground="red")

    def _build_logger(self):
        """
        Build the DataLogger, wiring its sources directly from config.LOG_COLUMNS.
        Adding a new log column only requires editing config.py.
        """
        sources = {}
        for header, (kind, key) in config.LOG_COLUMNS.items():
            if kind == "sensor" and key in self.sensors:
                var = self.sensors[key].value_var
            elif kind == "loop" and key in self.loops:
                var = self.loops[key].measured_var
            else:
                continue
            sources[header] = var.get     # callable → current string value

        self.logger = DataLogger(
            sources=sources,
            folder=config.LOG_FOLDER,
            count_var=self._data_point_count,
        )

    # ══════════════════════════════════════════════════════════════════
    # GUI construction
    # ══════════════════════════════════════════════════════════════════

    def _build_ui(self):
        container = ttk.Frame(self.root)
        container.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(container)
        self._canvas.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self._canvas.yview)
        scrollbar.pack(side="right", fill="y")

        self._sf = ttk.Frame(self._canvas)    # scrollable_frame
        self._canvas.create_window((0, 0), window=self._sf, anchor="nw")
        self._canvas.configure(yscrollcommand=scrollbar.set)
        self._sf.bind("<Configure>", lambda e: self._canvas.configure(
            scrollregion=self._canvas.bbox("all")
        ))
        self._sf.bind("<Enter>", lambda e: self.root.bind_all("<MouseWheel>", self._on_mousewheel))
        self._sf.bind("<Leave>", lambda e: self.root.unbind_all("<MouseWheel>"))

        # ── Top-left cluster: connection, air flow, logging ───────────
        self._build_controls_frame()
        self._build_air_flow_frame()
        self._build_data_logging_frame()

        # ── Separator and logo ────────────────────────────────────────
        ttk.Separator(self._sf).grid(
            row=0, column=2, rowspan=3, padx=(20, 10), pady=10, sticky="ns"
        )
        self._build_logo_frame()

        # ── Control loop panels (right side) ─────────────────────────
        # Layout: water at row 0, column1 at row 1, column2 at row 2 —
        # all in the same columns 3-5.  Edit these grid() calls to
        # rearrange panels for a different system.
        self._loop_widgets = {}
        loop_rows = {
            "water_flow":    0,
            "column1_level": 1,
            "column2_level": 2,
        }
        for key, row in loop_rows.items():
            if key in self.loops:
                widgets = build_control_loop_panel(
                    self._sf, self.loops[key], self.sensors,
                    row=row, col=3, columnspan=3, root=self.root,
                )
                self._loop_widgets[key] = widgets

    def _build_controls_frame(self):
        f = ttk.LabelFrame(self._sf, text="Controls", padding=(20, 10))
        f.grid(row=0, column=0, padx=(20, 10), pady=(10, 10), sticky="nsew")

        self._connect_dropdown = ttk.OptionMenu(
            f, self._connection_var,
            "Connect to LabJack",
            "USB", "Ethernet", "Disconnect",
            command=self._on_connection_choice,
        )
        self._connect_dropdown.grid(row=0, column=0, padx=5, pady=(10, 5), sticky="nsew")

        self._connection_status = ttk.Label(f, text="Not connected", padding=(5, 5))
        self._connection_status.grid(row=1, column=0, padx=5, pady=0, sticky="nsew")

        self._power_switch = ttk.Checkbutton(
            f, text="Main Power: OFF", style="Switch",
            variable=self._main_power_var,
            command=self._on_power_toggle,
        )
        self._power_switch.grid(row=2, column=0, padx=5, pady=10, sticky="nsew")

        # Column selector radio buttons (specific to this system).
        # For systems without a physical column selector, remove these.
        self._col1_radio = ttk.Radiobutton(
            f, text="Column 1 (White)",
            variable=self._col_select_var, value=True,
        )
        self._col1_radio.grid(row=4, column=0, padx=5, pady=10, sticky="nsew")

        self._col2_radio = ttk.Radiobutton(
            f, text="Column 2 (Blue)",
            variable=self._col_select_var, value=False,
        )
        self._col2_radio.grid(row=5, column=0, padx=5, pady=(5, 5), sticky="nsew")

        self._col_select_var.trace_add("write", self._on_column_select)

    def _build_air_flow_frame(self):
        """
        Air flow is a setpoint-only output (no feedback PID), so it gets its
        own small frame rather than a full ControlLoop panel.
        For a system without air flow, simply remove this method and its call
        in _build_ui().
        """
        f = ttk.LabelFrame(self._sf, text="Air Flow", padding=(20, 10))
        f.grid(row=0, column=1, padx=(20, 10), pady=(10, 10), sticky="nsew")

        self._air_setpoint_var = tk.StringVar(value="0")

        ttk.Label(f, text="Air Flow Setpoint (SLPM)").grid(
            row=0, column=0, padx=5, pady=0, sticky="nsew"
        )
        self._air_setpoint_spinbox = ttk.Spinbox(
            f, from_=0, to=1000, textvariable=self._air_setpoint_var,
            width=5, state="disabled",
        )
        self._air_setpoint_spinbox.grid(row=1, column=0, padx=5, pady=(5, 10), sticky="nsew")

        # Read-only displays for air-side sensors from SENSOR_CONFIGS
        self._air_sensor_widgets = {}
        air_sensor_keys = ["air_flowrate", "co2_concentration"]
        for i, key in enumerate(air_sensor_keys):
            if key in self.sensors:
                w = build_sensor_display(f, self.sensors[key], row=2 + i * 2, col=0)
                self._air_sensor_widgets[key] = w

    def _build_data_logging_frame(self):
        f = ttk.LabelFrame(self._sf, text="Data Logging", padding=(20, 10))
        f.grid(row=1, column=0, columnspan=2, padx=(20, 10), pady=(10, 10), sticky="nsew")

        self._toggle_logging_btn = ttk.Checkbutton(
            f, textvariable=self._logging_text_var,
            style="ToggleButton",
            command=self._on_toggle_logging,
            padding=(20, 20),
            state="disabled",
        )
        self._toggle_logging_btn.grid(row=0, rowspan=4, column=0, padx=40, pady=(20, 5), sticky="nsew")

        ttk.Label(f, text="Time Between Data (s)").grid(
            row=0, column=1, padx=5, pady=(20, 5), sticky="nsew"
        )
        ttk.Spinbox(
            f, from_=0, to=100, textvariable=self._log_interval_var,
            width=5, state="normal",
        ).grid(row=1, column=1, padx=5, pady=5, sticky="nsew")

        ttk.Label(f, text="Data Point Count").grid(
            row=2, column=1, padx=5, pady=5, sticky="nsew"
        )
        self._data_point_entry = ttk.Entry(
            f, textvariable=self._data_point_count, state="disabled",
        )
        self._data_point_entry.grid(row=3, column=1, padx=5, pady=5, sticky="nsew")

    def _build_logo_frame(self):
        f = tk.LabelFrame(self._sf, borderwidth=0, relief="flat")
        f.grid(row=2, column=0, columnspan=2, padx=(40, 10), pady=(0, 0), sticky="nsew")

        try:
            self._logo_img = tk.PhotoImage(file=config.LOGO_FILE)
            ttk.Label(f, image=self._logo_img).grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        except Exception:
            ttk.Label(f, text="[logo]").grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        ttk.Label(f, text="BYU TIPICE", font=("Copperplate Gothic Bold", 60), wraplength=300).grid(
            row=0, column=1, padx=(5, 20), pady=5, sticky="nsew"
        )

        self._theme_btn = ttk.Checkbutton(
            f, text="Dark Mode", style="ToggleButton", command=self._on_theme_toggle
        )
        self._theme_btn.grid(row=1, column=0, columnspan=2, padx=5, pady=10)
        self._logo_frame = f   # kept for background-colour sync in theme toggle

    # ══════════════════════════════════════════════════════════════════
    # Power / enable / disable
    # ══════════════════════════════════════════════════════════════════

    def _set_initial_states(self):
        """Everything is disabled until the LabJack is connected."""
        self._power_switch.configure(state="disabled")
        self._toggle_logging_btn.configure(state="disabled")
        if hasattr(self, "_air_setpoint_spinbox"):
            self._air_setpoint_spinbox.configure(state="disabled")
        for key_widgets in self._loop_widgets.values():
            disable_loop_widgets(key_widgets)

    def _enable_powered_controls(self):
        if hasattr(self, "_air_setpoint_spinbox"):
            self._air_setpoint_spinbox.configure(state="normal")
        for key_widgets in self._loop_widgets.values():
            enable_loop_widgets(key_widgets)
        self._toggle_logging_btn.configure(state="normal")

    def _disable_powered_controls(self):
        if hasattr(self, "_air_setpoint_spinbox"):
            self._air_setpoint_spinbox.configure(state="disabled")
        for key_widgets in self._loop_widgets.values():
            disable_loop_widgets(key_widgets)
        self._toggle_logging_btn.configure(state="disabled")
        if self.logger.is_logging:
            self.logger.stop()
            self._logging_text_var.set("Start Logging")
            self._data_point_count.set(0)

    # ══════════════════════════════════════════════════════════════════
    # Event callbacks
    # ══════════════════════════════════════════════════════════════════

    def _on_connection_choice(self, choice):
        if choice == "USB":
            self._connect("T7", "USB", "ANY")
        elif choice == "Ethernet":
            self._connect("T7", "ETHERNET", config.ETHERNET_ADDRESS)
        elif choice == "Disconnect":
            self._disconnect()

    def _connect(self, model, connection, identifier):
        try:
            self.daq.connect(model, connection, identifier)
            self._connection_status.config(text="Connected", style="Green.TLabel")
            self._power_switch.configure(state="normal")
            self._on_column_select()
        except Exception as exc:
            self._connection_status.config(
                text=f"Failed: {exc}", style="Red.TLabel"
            )

    def _disconnect(self):
        self.daq.disconnect()
        self._connection_status.config(text="Disconnected", style="Green.TLabel")
        self._power_switch.configure(state="disabled")
        self._main_power_on = False
        self._main_power_var.set(False)
        self._power_switch.config(text="Main Power: OFF")
        self._disable_powered_controls()

    def _on_power_toggle(self):
        self._main_power_on = not self._main_power_on
        if self._main_power_on:
            self._power_switch.config(text="Main Power: ON")
            self.daq.write(config.MAIN_POWER_PIN, 1)
            self._enable_powered_controls()
        else:
            self._power_switch.config(text="Main Power: OFF")
            self.daq.write(config.MAIN_POWER_PIN, 0)
            self._disable_powered_controls()

    def _on_column_select(self, *_args):
        """Write 0 V for Column 1, 5 V for Column 2 to the selector relay."""
        if not self.daq.is_connected:
            return
        voltage = 0 if self._col_select_var.get() else 5
        self.daq.write(config.COLUMN_SELECTOR_PIN, voltage)

    def _on_toggle_logging(self):
        if not self.logger.is_logging:
            self.logger.set_interval(self._log_interval_var.get())
            self.logger.start()
            self._logging_text_var.set("Stop Logging")
        else:
            self.logger.stop()
            self._logging_text_var.set("Start Logging")
            self._data_point_count.set(0)

    def _on_theme_toggle(self):
        self._theme_mode.set(1 - self._theme_mode.get())
        mode = "dark" if self._theme_mode.get() else "light"
        self._theme_btn.config(text="Light Mode" if self._theme_mode.get() else "Dark Mode")
        self.style.theme_use(f"forest-{mode}")
        bg = self.style.lookup(".", "background")
        self.root.configure(background=bg)
        self._logo_frame.configure(background=bg)
        self.root.update_idletasks()

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ══════════════════════════════════════════════════════════════════
    # Periodic update loop
    # ══════════════════════════════════════════════════════════════════

    def _schedule_updates(self):
        """Fire all update callbacks once; each one reschedules itself."""
        self.root.after(UPDATE_INTERVAL_MS, self._update_all_sensors)
        self.root.after(UPDATE_INTERVAL_MS, self._update_all_loops)
        self.root.after(UPDATE_INTERVAL_MS, self._update_air_setpoint_output)

    def _update_all_sensors(self):
        """Read every sensor in SENSOR_CONFIGS and push the value into value_var."""
        for sensor in self.sensors.values():
            if not sensor.is_configured():
                sensor.set_error()
                continue
            try:
                raw = self.daq.read(sensor.pin)
                sensor.set_value(sensor.apply_calibration(raw))
            except Exception:
                sensor.set_error()
        self.root.after(UPDATE_INTERVAL_MS, self._update_all_sensors)

    def _update_all_loops(self):
        """
        For each ControlLoop:
          1. Read and convert the process variable.
          2. If in AUTO mode: run PID, write output, update progress bar.
          3. If in MANUAL mode: write slider value directly to output.
        The column selector (Col 1 / Col 2) gates which level loop is active.
        """
        col1_active = self._col_select_var.get()

        for key, loop in self.loops.items():
            # ── Read process variable ──────────────────────────────────
            try:
                raw = self.daq.read(loop.input_pin)
                loop.set_measured(loop.apply_calibration(raw))
            except Exception:
                loop.set_error()

            # ── Column selector gate ───────────────────────────────────
            # The two level loops share one output pin (DAC0).  Only the
            # active column's loop should write to it.
            if key == "column1_level" and not col1_active:
                continue
            if key == "column2_level" and col1_active:
                continue

            # ── Output ────────────────────────────────────────────────
            try:
                if loop.is_auto:
                    sp   = loop.get_setpoint()
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

        self.root.after(UPDATE_INTERVAL_MS, self._update_all_loops)

    def _update_air_setpoint_output(self):
        """Convert the air SLPM setpoint to a voltage and send to the MFC."""
        if hasattr(self, "_air_setpoint_var"):
            try:
                voltage = float(self._air_setpoint_var.get()) / config.AIR_SETPOINT_SCALE
                self.daq.write(config.AIR_SETPOINT_PIN, voltage)
            except Exception as exc:
                print(f"[Air setpoint] {exc}")
        self.root.after(UPDATE_INTERVAL_MS, self._update_air_setpoint_output)
