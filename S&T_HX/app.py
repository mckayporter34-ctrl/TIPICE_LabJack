# app.py — Shell and Tube Heat Exchanger GUI
# ===========================================
# Layout:
#   Col 0        Col 1-2                          Col 3-5
#   ──────────   ──────────────────────────────   ──────────────────────
#   Controls     Data Logging (spans cols 1-2)    Level loop
#   Logo         Temperatures | Pressures/Flow    Flowrate loop
#                                                 Steam Pressure loop

import os
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
