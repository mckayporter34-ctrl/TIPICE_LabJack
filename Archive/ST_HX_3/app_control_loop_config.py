# app.py — Shell and Tube Heat Exchanger GUI
# ===========================================
# Layout:
#   Col 0        Col 1-2                          Col 3-5
#   ──────────   ──────────────────────────────   ──────────────────────
#   Controls     Data Logging (spans cols 1-2)    Level loop
#   Logo         Temperatures | Pressures/Flow    Flowrate loop
#                                                 Steam Pressure loop

import os
import math
import time
import tkinter as tk
from tkinter import ttk
from threading import Thread, Event

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

UPDATE_INTERVAL_MS = 500
DT_MINUTES = UPDATE_INTERVAL_MS / 1000 / 60


class ShellTubeHXApp:
    BASE_WIDTH  = 1600
    BASE_HEIGHT = 900

    def __init__(self):
        self.root = tk.Tk()
        self.root.geometry("1350x900")
        self.root.title(config.SYSTEM_NAME)
        self.root.option_add("*tearOff", False)

        self.daq = LabJackInterface()

        self.sensors = self._build_sensors()
        self.loops   = self._build_control_loops()

        self._theme_mode      = tk.IntVar(value=0)
        self._connection_var  = tk.StringVar(value="Connect to LabJack")
        self._main_power_on   = False
        self._main_power_var  = tk.BooleanVar(value=False)
        self._pump_on         = False
        self._pump_var        = tk.BooleanVar(value=False)

        self._logging_text_var = tk.StringVar(value="Start Logging")
        self._log_interval_var = tk.DoubleVar(value=1.0)
        self._data_point_count = tk.IntVar(value=0)

        # ── Auto-tuner state ──────────────────────────────────────────
        self._tuning_active      = False          # blocks normal PID output
        self._tuning_loop_key    = None           # which loop is being tuned
        self._tune_abort         = Event()        # set to stop tuner thread
        self._tune_status_var    = tk.StringVar(value="Idle")
        self._tune_kc_result_var = tk.StringVar(value="—")
        self._tune_ti_result_var = tk.StringVar(value="—")
        self._tune_loop_var      = tk.StringVar(value=list(config.CONTROL_LOOP_CONFIGS.keys())[0])
        self._tune_center_var    = tk.StringVar(value="2.5")
        self._tune_amp_var       = tk.StringVar(value="1.0")
        self._tune_setpoint_var  = tk.StringVar(value="0")
        self._tune_maxtime_var   = tk.StringVar(value="120")

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
            loops[key].setpoint_var.set(str(cfg.get("default_setpoint", 0)))
        return loops

    def _configure_root(self):
        # 6 columns: 1 for controls/logo, 2 for sensor panels, 3 for loops
        for i in range(6):
            self.root.columnconfigure(i, weight=1)
        # Only configure rows that have content
        for i in range(3):
            self.root.rowconfigure(i, weight=1)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        scalef = min(sw / self.BASE_WIDTH, sh / self.BASE_HEIGHT)
        self.root.tk.eval(f"set scalef {scalef:.3f}")
        self.root.tk.call("source", os.path.join(base_dir, "assets", "forest-dark.tcl"))
        self.root.tk.call("source", os.path.join(base_dir, "assets", "forest-light.tcl"))

    def _load_themes(self):
        self.style = ttk.Style()
        self.style.theme_use("forest-light")
        self.style.configure("Green.TLabel", foreground="green")
        self.style.configure("Red.TLabel",   foreground="red")

    def _build_logger(self):
        sources = {}
        for header, (kind, key) in config.LOG_COLUMNS.items():
            if kind == "sensor" and key in self.sensors:
                sources[header] = self.sensors[key].value_var.get
            elif kind == "loop" and key in self.loops:
                sources[header] = self.loops[key].measured_var.get
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
        self._canvas.configure(bg=self.style.lookup("TFrame", "background"))

        v_scrollbar = ttk.Scrollbar(container, orient="vertical", command=self._canvas.yview)
        v_scrollbar.pack(side="right", fill="y")

        h_scrollbar = ttk.Scrollbar(self.root, orient="horizontal", command=self._canvas.xview)
        h_scrollbar.pack(side="bottom", fill="x")

        self._canvas.configure(
            yscrollcommand=v_scrollbar.set,
            xscrollcommand=h_scrollbar.set,
        )

        self._sf = ttk.Frame(self._canvas)
        self._canvas.create_window((0, 0), window=self._sf, anchor="nw")
        self._sf.bind("<Configure>", lambda e: self._canvas.configure(
            scrollregion=self._canvas.bbox("all")
        ))
        self._sf.bind("<Enter>", lambda e: self.root.bind_all("<MouseWheel>", self._on_mousewheel))
        self._sf.bind("<Leave>", lambda e: self.root.unbind_all("<MouseWheel>"))

        # ── Col 0: Controls (row 0) + Logo (row 1, spanning rows 1-2) ─────────
        self._build_controls_frame()
        self._build_logo_frame()

        # ── Col 1-2: Data Logging (row 0) + Temp (row 1) | Pressure (row 1) ───
        self._build_data_logging_frame()
        self._build_temp_panel()
        self._build_pressure_panel()

        # ── Col 3-5: Control loop panels stacked (rows 0, 1, 2) ───────────────
        self._loop_widgets = {}
        loop_rows = {
            "level":          0,
            "flowrate":       1,
            "steam_pressure": 2,
        }
        for key, row in loop_rows.items():
            if key in self.loops:
                widgets = build_control_loop_panel(
                    self._sf, self.loops[key], self.sensors,
                    row=row, col=3, columnspan=3, root=self.root,
                )
                self._loop_widgets[key] = widgets

        # ── Col 3-5 row 3: Auto-tuner panel ───────────────────────────────────
        self._build_autotuner_panel()

    def _build_controls_frame(self):
        """Connection, power, and pump switch — col 0, row 0."""
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

        self._pump_switch = ttk.Checkbutton(
            f, text="Pump: OFF", style="Switch",
            variable=self._pump_var,
            command=self._on_pump_toggle,
        )
        self._pump_switch.grid(row=3, column=0, padx=5, pady=10, sticky="nsew")

    def _build_logo_frame(self):
        """Logo and theme toggle — col 0, rows 1-2."""
        f = tk.LabelFrame(self._sf, borderwidth=0, relief="flat")
        f.grid(row=1, column=0, rowspan=2, padx=(20, 10), pady=(10, 10), sticky="nsew")

        try:
            self._logo_img = tk.PhotoImage(file=config.LOGO_FILE)
            ttk.Label(f, image=self._logo_img).grid(
                row=0, column=0, padx=5, pady=5, sticky="nsew"
            )
        except Exception:
            ttk.Label(f, text="[logo]").grid(
                row=0, column=0, padx=5, pady=5, sticky="nsew"
            )

        ttk.Label(f, text="BYU TIPICE",
                  font=("Copperplate Gothic Bold", 40), wraplength=180).grid(
            row=1, column=0, padx=5, pady=5, sticky="nsew"
        )
        self._theme_btn = ttk.Checkbutton(
            f, text="Dark Mode", style="ToggleButton",
            command=self._on_theme_toggle,
        )
        self._theme_btn.grid(row=2, column=0, padx=5, pady=10)
        self._logo_frame = f

    def _build_data_logging_frame(self):
        """Data logging — cols 1-2, row 0."""
        f = ttk.LabelFrame(self._sf, text="Data Logging", padding=(20, 10))
        f.grid(row=0, column=1, columnspan=2, padx=(10, 10), pady=(10, 10), sticky="nsew")

        self._toggle_logging_btn = ttk.Checkbutton(
            f, textvariable=self._logging_text_var,
            style="ToggleButton", command=self._on_toggle_logging,
            padding=(20, 20), state="disabled",
        )
        self._toggle_logging_btn.grid(
            row=0, rowspan=4, column=0, padx=40, pady=(20, 5), sticky="nsew"
        )
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

    def _build_temp_panel(self):
        """Temperature sensors — col 1, rows 1-2."""
        f = ttk.LabelFrame(self._sf, text="Temperatures", padding=(20, 10))
        f.grid(row=1, column=1, rowspan=2, padx=(10, 5), pady=(10, 10), sticky="nsew")

        temp_keys = ["water_inlet_temp", "water_outlet_temp", "makeup_temperature"]
        for i, key in enumerate(temp_keys):
            if key in self.sensors:
                build_sensor_display(f, self.sensors[key], row=i * 2, col=0)

    def _build_pressure_panel(self):
        """Pressure and flow sensors — col 2, rows 1-2."""
        f = ttk.LabelFrame(self._sf, text="Pressures & Flow", padding=(20, 10))
        f.grid(row=1, column=2, rowspan=2, padx=(5, 10), pady=(10, 10), sticky="nsew")

        pressure_keys = [
            "house_steam_pressure",
            "tube_side_pressure_drop",
            "makeup_flowrate",
        ]
        for i, key in enumerate(pressure_keys):
            if key in self.sensors:
                build_sensor_display(f, self.sensors[key], row=i * 2, col=0)

    # ══════════════════════════════════════════════════════════════════
    # Power / enable / disable
    # ══════════════════════════════════════════════════════════════════

    def _set_initial_states(self):
        self._power_switch.configure(state="disabled")
        self._pump_switch.configure(state="disabled")
        self._toggle_logging_btn.configure(state="disabled")
        for key_widgets in self._loop_widgets.values():
            disable_loop_widgets(key_widgets)

    def _enable_powered_controls(self):
        for key_widgets in self._loop_widgets.values():
            enable_loop_widgets(key_widgets)
        self._toggle_logging_btn.configure(state="normal")
        self._pump_switch.configure(state="normal")

    def _disable_powered_controls(self):
        for key_widgets in self._loop_widgets.values():
            disable_loop_widgets(key_widgets)
        self._toggle_logging_btn.configure(state="disabled")
        self._pump_switch.configure(state="disabled")
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
        except Exception as exc:
            self._connection_status.config(text=f"Failed: {exc}", style="Red.TLabel")

    def _disconnect(self):
        self.daq.disconnect()
        self._connection_status.config(text="Disconnected", style="Green.TLabel")
        self._power_switch.configure(state="disabled")
        self._main_power_on = False
        self._main_power_var.set(False)
        self._power_switch.config(text="Main Power: OFF")
        self._pump_on = False
        self._pump_var.set(False)
        self._pump_switch.config(text="Pump: OFF")
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
            self._pump_on = False
            self._pump_var.set(False)
            self._pump_switch.config(text="Pump: OFF")
            self.daq.write(config.PUMP_SWITCH_PIN, 0)
            self._disable_powered_controls()

    def _on_pump_toggle(self):
        self._pump_on = not self._pump_on
        if self._pump_on:
            self._pump_switch.config(text="Pump: ON")
            self.daq.write(config.PUMP_SWITCH_PIN, 1)
        else:
            self._pump_switch.config(text="Pump: OFF")
            self.daq.write(config.PUMP_SWITCH_PIN, 0)

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
        self._theme_btn.config(
            text="Light Mode" if self._theme_mode.get() else "Dark Mode"
        )
        self.style.theme_use(f"forest-{mode}")
        bg = self.style.lookup(".", "background")
        self.root.configure(background=bg)
        self._logo_frame.configure(background=bg)
        self._canvas.configure(bg=bg)
        self.root.update_idletasks()

    def _on_mousewheel(self, event):
        if event.delta in (1, -1):
            scroll = -event.delta * 3   # macOS
        else:
            scroll = int(-1 * (event.delta / 120)) * 3   # Windows/Linux
        self._canvas.yview_scroll(scroll, "units")

    # ══════════════════════════════════════════════════════════════════
    # Periodic update loop
    # ══════════════════════════════════════════════════════════════════

    def _schedule_updates(self):
        self.root.after(UPDATE_INTERVAL_MS, self._update_all_sensors)
        self.root.after(UPDATE_INTERVAL_MS, self._update_all_loops)

    def _update_all_sensors(self):
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
        for key, loop in self.loops.items():
            try:
                raw = self.daq.read(loop.input_pin)
                loop.set_measured(loop.apply_calibration(raw))
            except Exception:
                loop.set_error()

            # Skip output for the loop currently being auto-tuned —
            # the tuner thread owns that output pin during its test.
            if self._tuning_active and key == self._tuning_loop_key:
                continue

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

    # ══════════════════════════════════════════════════════════════════
    # Auto-tuner panel
    # ══════════════════════════════════════════════════════════════════

    def _build_autotuner_panel(self):
        """
        Auto-tuner panel — col 3-5, row 3.
        Runs relay feedback tuning on whichever loop is selected.
        The normal PID/manual output for that loop is suspended while
        the tuner is active; all other loops continue running normally.
        """
        f = ttk.LabelFrame(self._sf, text="PI Auto-Tuner (Relay Feedback)",
                           padding=(20, 10))
        f.grid(row=3, column=3, columnspan=3,
               padx=(20, 20), pady=(10, 10), sticky="nsew")

        # Row 0-1: Loop selector + setpoint
        ttk.Label(f, text="Loop to tune").grid(
            row=0, column=0, padx=5, pady=(10, 0), sticky="w")
        loop_names = list(config.CONTROL_LOOP_CONFIGS.keys())
        ttk.OptionMenu(f, self._tune_loop_var, loop_names[0], *loop_names).grid(
            row=1, column=0, padx=5, pady=(0, 10), sticky="ew")

        ttk.Label(f, text="Test setpoint").grid(
            row=0, column=1, padx=5, pady=(10, 0), sticky="w")
        ttk.Entry(f, textvariable=self._tune_setpoint_var, width=8).grid(
            row=1, column=1, padx=5, pady=(0, 10), sticky="ew")

        # Row 2-3: Relay parameters
        ttk.Label(f, text="Relay centre (V)", wraplength=100).grid(
            row=2, column=0, padx=5, pady=(5, 0), sticky="w")
        ttk.Entry(f, textvariable=self._tune_center_var, width=8).grid(
            row=3, column=0, padx=5, pady=(0, 10), sticky="ew")

        ttk.Label(f, text="Relay amplitude (V)", wraplength=100).grid(
            row=2, column=1, padx=5, pady=(5, 0), sticky="w")
        ttk.Entry(f, textvariable=self._tune_amp_var, width=8).grid(
            row=3, column=1, padx=5, pady=(0, 10), sticky="ew")

        ttk.Label(f, text="Max test time (s)", wraplength=100).grid(
            row=2, column=2, padx=5, pady=(5, 0), sticky="w")
        ttk.Entry(f, textvariable=self._tune_maxtime_var, width=8).grid(
            row=3, column=2, padx=5, pady=(0, 10), sticky="ew")

        # Row 4: Start / Abort
        self._tune_start_btn = ttk.Button(
            f, text="Start Tuning", style="Accent.TButton",
            command=self._start_autotuner, state="disabled")
        self._tune_start_btn.grid(row=4, column=0, padx=5, pady=10, sticky="ew")

        self._tune_abort_btn = ttk.Button(
            f, text="Abort / Safe State",
            command=self._abort_autotuner, state="disabled")
        self._tune_abort_btn.grid(row=4, column=1, padx=5, pady=10, sticky="ew")

        # Row 5: Status
        ttk.Label(f, text="Status:").grid(
            row=5, column=0, padx=5, pady=(5, 0), sticky="w")
        ttk.Label(f, textvariable=self._tune_status_var,
                  foreground="blue", wraplength=500).grid(
            row=5, column=1, columnspan=3, padx=5, pady=(5, 0), sticky="w")

        # Row 6-7: Results
        ttk.Separator(f, orient="horizontal").grid(
            row=6, column=0, columnspan=4, padx=5, pady=10, sticky="ew")

        ttk.Label(f, text="Recommended Kc:").grid(
            row=7, column=0, padx=5, pady=5, sticky="w")
        ttk.Label(f, textvariable=self._tune_kc_result_var,
                  font=("Helvetica", 11, "bold")).grid(
            row=7, column=1, padx=5, pady=5, sticky="w")

        ttk.Label(f, text="Recommended Ti (min):").grid(
            row=7, column=2, padx=5, pady=5, sticky="w")
        ttk.Label(f, textvariable=self._tune_ti_result_var,
                  font=("Helvetica", 11, "bold")).grid(
            row=7, column=3, padx=5, pady=5, sticky="w")

        # Row 8: Apply
        self._tune_apply_btn = ttk.Button(
            f, text="Apply to Loop",
            command=self._apply_tuning_results, state="disabled")
        self._tune_apply_btn.grid(
            row=8, column=0, columnspan=2, padx=5, pady=(5, 10), sticky="ew")

        ttk.Label(f, text="Applies found Kc/Ti to the loop's spinboxes.",
                  foreground="grey").grid(
            row=8, column=2, columnspan=2, padx=5, pady=(5, 10), sticky="w")

    # ══════════════════════════════════════════════════════════════════
    # Auto-tuner logic
    # ══════════════════════════════════════════════════════════════════

    def _start_autotuner(self):
        key = self._tune_loop_var.get()
        if key not in self.loops or key not in config.CONTROL_LOOP_CONFIGS:
            self._tune_status_var.set("ERROR: Unknown loop selected.")
            return
        try:
            float(self._tune_center_var.get())
            float(self._tune_amp_var.get())
            float(self._tune_setpoint_var.get())
            float(self._tune_maxtime_var.get())
        except ValueError:
            self._tune_status_var.set("ERROR: All fields must be numbers.")
            return

        self._tune_kc_result_var.set("—")
        self._tune_ti_result_var.set("—")
        self._tune_apply_btn.configure(state="disabled")
        self._tuning_loop_key = key
        self._tuning_active   = True
        self._tune_abort.clear()
        self._tune_start_btn.configure(state="disabled")
        self._tune_abort_btn.configure(state="normal")
        self._tune_status_var.set(
            f"Starting tuner on '{config.CONTROL_LOOP_CONFIGS[key]['label']}'...")
        Thread(target=self._run_autotuner, args=(key,), daemon=True).start()

    def _run_autotuner(self, key):
        loop_cfg = config.CONTROL_LOOP_CONFIGS[key]
        loop_obj = self.loops[key]
        out_pin  = loop_cfg["output_pin"]
        center   = float(self._tune_center_var.get())
        amp      = float(self._tune_amp_var.get())
        setpoint = float(self._tune_setpoint_var.get())
        max_time = float(self._tune_maxtime_var.get())
        out_max  = loop_cfg.get("output_max", 5.0)
        action   = loop_cfg.get("action", "direct")
        min_cyc  = 3
        v_high   = min(center + amp, out_max)
        v_low    = max(center - amp, 0.0)

        # Settle
        self.root.after(0, lambda: self._tune_status_var.set(
            "Settling at relay centre for 10 s..."))
        self.daq.write(out_pin, center)
        t0 = time.time()
        while time.time() - t0 < 10.0:
            if self._tune_abort.is_set():
                self._finish_autotuner(key, None, "Aborted during settle.")
                return
            time.sleep(0.2)

        # Initial PV
        try:
            pv = float(loop_obj.measured_var.get())
        except ValueError:
            self._finish_autotuner(
                key, None, "Cannot read PV — is the sensor connected?")
            return

        relay_high = (pv < setpoint) if action == "direct" else (pv > setpoint)
        crossings  = []
        peaks_high = []
        peaks_low  = []
        pv_window  = []
        prev_above = pv > setpoint
        t_start    = time.time()

        while not self._tune_abort.is_set():
            elapsed = time.time() - t_start
            if elapsed > max_time:
                self._finish_autotuner(
                    key, None,
                    f"Timeout after {max_time:.0f} s — no oscillation found. "
                    "Try increasing relay amplitude or max time.")
                return

            try:
                pv = float(loop_obj.measured_var.get())
            except ValueError:
                time.sleep(0.2)
                continue

            pv_window.append(pv)
            if len(pv_window) > 10:
                pv_window.pop(0)

            above = pv > setpoint
            if above != prev_above:
                if pv_window:
                    if prev_above:
                        peaks_high.append(max(pv_window))
                    else:
                        peaks_low.append(min(pv_window))
                crossings.append(time.time())
                pv_window  = []
                prev_above = above
                relay_high = (not above) if action == "direct" else above

            v_out = v_high if relay_high else v_low
            self.daq.write(out_pin, v_out)
            loop_obj.set_valve_display(v_out)

            complete = max(0, (len(crossings) - 1) // 2)
            self.root.after(0, lambda p=pv, v=v_out, c=complete:
                self._tune_status_var.set(
                    f"Relay active — {c}/{min_cyc} cycles — "
                    f"PV: {p:.3f} | Output: {v:.2f} V"))

            if complete >= min_cyc and len(crossings) >= 3:
                break
            time.sleep(0.2)

        if self._tune_abort.is_set():
            self._finish_autotuner(key, None, "Aborted by user.")
            return

        # Compute
        periods = [crossings[i+2] - crossings[i]
                   for i in range(0, len(crossings) - 2, 2)]
        if not periods or not peaks_high or not peaks_low:
            self._finish_autotuner(
                key, None, "Not enough oscillation data collected.")
            return

        Pu_min = (sum(periods) / len(periods)) / 60.0
        a      = (sum(peaks_high)/len(peaks_high)
                  - sum(peaks_low)/len(peaks_low)) / 2.0
        if a <= 0:
            self._finish_autotuner(
                key, None, "Oscillation amplitude is zero — check sensor.")
            return

        Ku = (4.0 * amp) / (math.pi * a)
        Kc = 0.45 * Ku
        Ti = Pu_min / 1.2
        if action == "reverse":
            Kc = -abs(Kc)

        self._finish_autotuner(
            key, (Kc, Ti),
            f"Done.  Pu = {Pu_min*60:.1f} s  |  Ku = {Ku:.4f}  |  a = {a:.4f}")

    def _finish_autotuner(self, key, result, status_msg):
        safe_voltages = {"DAC0": 0.0, "DAC1": 5.0, "TDAC0": 0.0}
        out_pin = config.CONTROL_LOOP_CONFIGS[key]["output_pin"]
        self.daq.write(out_pin, safe_voltages.get(out_pin, 0.0))
        self._tuning_active   = False
        self._tuning_loop_key = None

        def _ui():
            self._tune_status_var.set(status_msg)
            self._tune_start_btn.configure(state="normal")
            self._tune_abort_btn.configure(state="disabled")
            if result is not None:
                Kc, Ti = result
                self._tune_kc_result_var.set(f"{Kc:.4f}")
                self._tune_ti_result_var.set(f"{Ti:.4f}")
                self._tune_apply_btn.configure(state="normal")
                self._last_tune_key = key
                self._last_tune_Kc  = Kc
                self._last_tune_Ti  = Ti

        self.root.after(0, _ui)

    def _abort_autotuner(self):
        self._tune_abort.set()
        self._tune_status_var.set("Aborting — returning to safe state...")

    def _apply_tuning_results(self):
        if not hasattr(self, "_last_tune_key"):
            return
        loop = self.loops.get(self._last_tune_key)
        if loop is None:
            return
        loop.Kc_var.set(round(self._last_tune_Kc, 4))
        loop.Ti_var.set(round(self._last_tune_Ti, 4))
        loop.sync_tuning_to_pid()
        self._tune_status_var.set(
            f"Applied Kc={self._last_tune_Kc:.4f}, Ti={self._last_tune_Ti:.4f} "
            f"to '{config.CONTROL_LOOP_CONFIGS[self._last_tune_key]['label']}'. "
            f"Switch loop to AUTO to activate.")

    # ══════════════════════════════════════════════════════════════════
    # Override enable/disable to include tuner buttons
    # ══════════════════════════════════════════════════════════════════

    def _enable_powered_controls(self):
        for key_widgets in self._loop_widgets.values():
            enable_loop_widgets(key_widgets)
        self._toggle_logging_btn.configure(state="normal")
        self._pump_switch.configure(state="normal")
        self._tune_start_btn.configure(state="normal")

    def _disable_powered_controls(self):
        for key_widgets in self._loop_widgets.values():
            disable_loop_widgets(key_widgets)
        self._toggle_logging_btn.configure(state="disabled")
        self._pump_switch.configure(state="disabled")
        self._tune_start_btn.configure(state="disabled")
        self._tune_abort_btn.configure(state="disabled")
        self._tune_apply_btn.configure(state="disabled")
        if self._tuning_active:
            self._abort_autotuner()
        if self.logger.is_logging:
            self.logger.stop()
            self._logging_text_var.set("Start Logging")
            self._data_point_count.set(0)
