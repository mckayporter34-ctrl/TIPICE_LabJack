# app.py — Packed Columns — Redesigned P&ID Interface
# ===================================================

import os
import time
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk

import config
from sensor import Sensor
from control_loop import ControlLoop
from pid_controller import PIDController
from labjack_interface import LabJackInterface
from data_logger import DataLogger

UPDATE_INTERVAL_MS = 500
DT_MINUTES         = UPDATE_INTERVAL_MS / 1000 / 60

# ── Canvas dimensions ─────────────────────────────────────────────────────────
CW, CH = 902, 554


class PackedColumnsRedesignApp:
    BASE_WIDTH  = 1440
    BASE_HEIGHT = 800

    def __init__(self):
        self.root = tk.Tk()
        self.root.geometry("1200x820")
        self.root.title(config.SYSTEM_NAME + " — Redesigned P&ID View")
        self.root.option_add("*tearOff", False)

        # ── Hardware interface ────────────────────────────────────────
        self.daq = LabJackInterface()

        # ── Data structures from config ──────────────────────────────
        self.sensors = self._build_sensors()
        self.loops   = self._build_control_loops()

        # ── GUI States ────────────────────────────────────────────────
        self._theme_mode      = tk.IntVar(value=0)  # 0 = light, 1 = dark
        self._connection_var  = tk.StringVar(value="Connect to LabJack")
        self._main_power_on   = False
        self._main_power_var  = tk.BooleanVar(value=False)
        self._col_select_var  = tk.BooleanVar(value=True)   # True = Column 1, False = Column 2

        # Data logging states
        self._logging_text_var = tk.StringVar(value="Start Logging")
        self._log_interval_var = tk.DoubleVar(value=1.0)
        self._data_point_count = tk.IntVar(value=0)

        # Bottom Panel state variables
        self._level_mode_auto_var = tk.BooleanVar(value=False)
        self._water_mode_auto_var = tk.BooleanVar(value=False)
        self._simple_panel_widgets = {}

        # Canvas overlays list
        self._overlay_cards = []

        # Dedicate a variable to display water exit valve percentage dynamically
        self._water_exit_valve_percent_var = tk.StringVar(value="0")

        # Air Flow control state variables
        self._air_setpoint_var = tk.StringVar(value="0")
        self._air_setpoint_double_var = tk.DoubleVar(value=0.0)
        self._air_valve_percent_var = tk.StringVar(value="0")

        # Active column overlays for canvas
        self._active_pressure_drop_var = tk.StringVar(value="---")
        self._active_level_var = tk.StringVar(value="---")

        # Sync air valve percent variable on setpoint write
        self._air_setpoint_var.trace_add("write", lambda *a: self._sync_air_valve_percent())

        self._configure_root()
        self._load_themes()
        self._build_ui()
        self._set_initial_states()
        self._build_logger()
        self._schedule_updates()

        # Initialize column selector state and bindings
        self._on_column_select()

        # Defer simulation warning dialog
        self.root.after(200, self._show_sim_warning)

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
                calibration=cfg["calibration"]
            )
            for key, cfg in config.SENSOR_CONFIGS.items()
        }

    def _build_control_loops(self) -> dict:
        loops = {}
        for key, cfg in config.CONTROL_LOOP_CONFIGS.items():
            d = cfg.get("pid_defaults", {})
            loops[key] = ControlLoop(
                key=key,
                label=cfg["label"],
                unit=cfg["unit"],
                input_pin=cfg["input_pin"],
                output_pin=cfg["output_pin"],
                calibration=cfg["calibration"],
                setpoint_min=cfg.get("setpoint_min", 0),
                setpoint_max=cfg.get("setpoint_max", 100),
                pid=PIDController(
                    Kc=d.get("Kc", 1.0),
                    Ti=d.get("Ti", 1.0),
                    Td=d.get("Td", 0.0)
                ),
                extra_sensor_key=cfg.get("extra_sensor_key"),
            )
            loops[key].setpoint_var.set(str(cfg.get("default_setpoint", 0)))
        return loops

    def _configure_root(self):
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.columnconfigure(2, weight=1)
        self.root.columnconfigure(3, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=0)

        # Load forest themes from Modular_GUI
        base_dir = os.path.dirname(os.path.abspath(__file__))
        assets_dir = os.path.join(os.path.dirname(base_dir), "Modular_GUI", "assets")
        
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        scalef = min(sw / self.BASE_WIDTH, sh / self.BASE_HEIGHT)
        self.root.tk.eval(f"set scalef {scalef:.3f}")
        
        try:
            self.root.tk.call("source", os.path.join(assets_dir, "forest-dark.tcl"))
            self.root.tk.call("source", os.path.join(assets_dir, "forest-light.tcl"))
        except Exception as e:
            print(f"Error loading theme files: {e}")

    def _load_themes(self):
        self.style = ttk.Style()
        try:
            self.style.theme_use("forest-light")
        except Exception:
            pass
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
            count_var=self._data_point_count
        )

    def _show_sim_warning(self):
        if self.daq.simulated:
            messagebox.showwarning(
                "LabJack Not Connected",
                "No LabJack T7 detected.\n\n"
                "Running in SIMULATED mode.\n"
                "Flows and levels are modeled dynamically based on control valve outputs.\n\n"
                "Connect to a real LabJack via the Connection controls."
            )

    # ══════════════════════════════════════════════════════════════════
    # UI construction
    # ══════════════════════════════════════════════════════════════════

    def _build_ui(self):
        container = ttk.Frame(self.root)
        container.pack(fill="both", expand=True)

        self._canvas_outer = tk.Canvas(container)
        self._canvas_outer.pack(side="left", fill="both", expand=True)

        v_sb = ttk.Scrollbar(container, orient="vertical", command=self._canvas_outer.yview)
        v_sb.pack(side="right", fill="y")
        h_sb = ttk.Scrollbar(self.root, orient="horizontal", command=self._canvas_outer.xview)
        h_sb.pack(side="bottom", fill="x")

        self._canvas_outer.configure(yscrollcommand=v_sb.set, xscrollcommand=h_sb.set)
        bg = self.style.lookup("TFrame", "background")
        self._canvas_outer.configure(bg=bg)

        self._sf = ttk.Frame(self._canvas_outer)
        self._canvas_outer.create_window((0, 0), window=self._sf, anchor="nw")
        
        self._sf.bind("<Configure>", lambda e: self._canvas_outer.configure(
            scrollregion=self._canvas_outer.bbox("all")
        ))
        self._sf.bind("<Enter>", lambda e: self.root.bind_all("<MouseWheel>", self._on_mousewheel))
        self._sf.bind("<Leave>", lambda e: self.root.unbind_all("<MouseWheel>"))

        self._build_left_column()
        self._build_pid_canvas()
        self._build_horizontal_panels()

    # ── Left column ───────────────────────────────────────────────────

    def _build_left_column(self):
        col = ttk.Frame(self._sf)
        col.grid(row=0, column=0, rowspan=2, padx=(10, 5), pady=10, sticky="nsew")

        # Controls panel
        ctrl = ttk.LabelFrame(col, text="Controls", padding=(30, 15))
        ctrl.pack(fill="x", pady=(0, 8))

        self._connect_dd = ttk.OptionMenu(
            ctrl, self._connection_var, "Connect to LabJack",
            "USB", "Ethernet", "Disconnect",
            command=self._on_connection_choice
        )
        self._connect_dd.pack(fill="x", pady=(4, 4))

        self._status_lbl = ttk.Label(ctrl, text="Simulated Mode", style="Red.TLabel", padding=(4, 2))
        self._status_lbl.pack(fill="x")

        self._power_sw = ttk.Checkbutton(
            ctrl, text="Main Power: OFF", style="Switch",
            variable=self._main_power_var, command=self._on_power_toggle
        )
        self._power_sw.pack(fill="x", pady=6)

        # Column Selector
        ttk.Label(ctrl, text="Column Selector").pack(fill="x", pady=(6, 2))
        self._col1_radio = ttk.Radiobutton(
            ctrl, text="Column 1 (Left)",
            variable=self._col_select_var, value=True
        )
        self._col1_radio.pack(fill="x", pady=2)

        self._col2_radio = ttk.Radiobutton(
            ctrl, text="Column 2 (Right)",
            variable=self._col_select_var, value=False
        )
        self._col2_radio.pack(fill="x", pady=2)

        self._col_select_var.trace_add("write", self._on_column_select)

        # Data logging panel
        log = ttk.LabelFrame(col, text="Data Logging", padding=(30, 15))
        log.pack(fill="x", pady=(0, 8))

        self._log_btn = ttk.Checkbutton(
            log, textvariable=self._logging_text_var,
            style="ToggleButton", command=self._on_toggle_logging,
            padding=(15, 12), state="disabled"
        )
        self._log_btn.pack(fill="x", pady=4)

        r = ttk.Frame(log)
        r.pack(fill="x", pady=2)
        ttk.Label(r, text="Interval (s)").pack(side="left")
        ttk.Spinbox(r, from_=0.1, to=100.0, textvariable=self._log_interval_var, width=5).pack(side="right")

        r2 = ttk.Frame(log)
        r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="Count").pack(side="left")
        ttk.Entry(r2, textvariable=self._data_point_count, state="disabled", width=6).pack(side="right")

        # Apparatus Image
        img_f = ttk.LabelFrame(col, text="Apparatus Image", padding=10)
        img_f.pack(fill="x", pady=(0, 8))
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            workspace_dir = os.path.dirname(os.path.dirname(base_dir))
            img_path = os.path.join(workspace_dir, "images", "packed_column.jpg")
            img = Image.open(img_path)
            img.thumbnail((200, 160))
            self._appar_img = ImageTk.PhotoImage(img)
            ttk.Label(img_f, image=self._appar_img, anchor="center").pack()
        except Exception as e:
            print(f"Error loading photo: {e}")
            ttk.Label(img_f, text="No Image Found", anchor="center").pack()

        # Theme toggle
        self._theme_btn = ttk.Checkbutton(
            col, text="Dark Mode", style="ToggleButton",
            command=self._on_theme_toggle
        )
        self._theme_btn.pack(fill="x")

    # ── P&ID Canvas ───────────────────────────────────────────────────

    def _build_pid_canvas(self):
        outer = tk.LabelFrame(self._sf, text="P&ID — Packed Columns",
                               bg="white", fg="#263238", font=("Helvetica", 10, "bold"),
                               bd=1, relief="solid", padx=10, pady=10)
        outer.grid(row=0, column=1, columnspan=3, padx=5, pady=10, sticky="nsew")

        self._pid = tk.Canvas(outer, width=CW, height=CH, bg="white", highlightthickness=0)
        self._pid.pack(expand=True)

        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            bg_path = os.path.join(os.path.dirname(base_dir), "packedcoloumn_pid.png")
            self._bg_img_raw = Image.open(bg_path)
            self._bg_img_resized = self._bg_img_raw.resize((CW, CH), Image.Resampling.LANCZOS)
            self._bg_img = ImageTk.PhotoImage(self._bg_img_resized)
            self._pid.create_image(0, 0, anchor="nw", image=self._bg_img)
        except Exception as e:
            print(f"Error loading P&ID background image: {e}")
            self._pid.create_text(CW//2, CH//2, text="P&ID Diagram Image Not Found", font=("Helvetica", 16))

        self._create_sensor_overlays()

    def _create_sensor_overlays(self):
        s = self.sensors
        lps = self.loops

        # Column indicators variables
        self._col1_indicator_val = tk.StringVar(value="COLUMN 1 (ACTIVE)")
        self._col2_indicator_val = tk.StringVar(value="COLUMN 2 (INACTIVE)")

        # Create column selected indicators
        self._col1_lbl = tk.Label(self._pid, textvariable=self._col1_indicator_val,
                                  font=("Helvetica", 11, "bold"), bg="#2E7D32", fg="white", padx=6, pady=4, relief="ridge")
        self._pid.create_window(240, 15, window=self._col1_lbl, anchor="center")

        self._col2_lbl = tk.Label(self._pid, textvariable=self._col2_indicator_val,
                                  font=("Helvetica", 11, "bold"), bg="#B0BEC5", fg="#37474F", padx=6, pady=4, relief="ridge")
        self._pid.create_window(570, 15, window=self._col2_lbl, anchor="center")

        overlays = [
            # Single active column readings in the center (tagged to support coordinate changes)
            (400, 230, "Column 1 Pressure Drop\n(Pa)", self._active_pressure_drop_var, "dp"),
            (400, 310, "Column 1 Level\n(mm)", self._active_level_var, "level"),

            # Water Line readings (Right top)
            (810, 35, "Water Flowrate\n(L/min)", lps["water_flow"].measured_var),
            (810, 105, "Water Temp\n(°C)", s["water_temperature"].value_var),
            (650, 160, "Water Flow Valve\n(%)", lps["water_flow"].rounded_valve_position),

            # Water Exit Line reading (Left bottom)
            (108, 480, "Water Exit Valve\n(%)", self._water_exit_valve_percent_var),

            # Air Line readings (Right bottom)
            (475, 505, "Air Flowrate\n(SLPM)", s["air_flowrate"].value_var),
            (400, 85, "CO₂ Concentration\n(ppm)", s["co2_concentration"].value_var),
            (635, 520, "Air Valve\n(%)", self._air_valve_percent_var),
        ]

        for item in overlays:
            x, y, label, var = item[0], item[1], item[2], item[3]
            tag = item[4] if len(item) > 4 else None

            card = tk.Frame(self._pid, bg="white", padx=2, pady=2)
            lbl = tk.Label(card, text=label, font=("Helvetica", 10, "bold"), bg="white", fg="#263238", anchor="center")
            lbl.pack(fill="x", padx=0, pady=0)
            entry_box = ttk.Entry(card, textvariable=var, state="disabled", width=8, justify="center", font=("Helvetica", 11, "bold"))
            entry_box.pack(fill="x", padx=0, pady=(2, 4))

            if tag == "dp":
                self._active_dp_lbl_widget = lbl
            elif tag == "level":
                self._active_level_lbl_widget = lbl

            self._pid.create_window(x, y, window=card, anchor="center")
            self._overlay_cards.append(card)

    # ── Horizontal bottom control panels ──────────────────────────────

    def _build_horizontal_panels(self):
        # 1. Water control loop panel
        w_widgets = self._build_simple_loop_panel(self._sf, "water_flow", self.loops["water_flow"], row=1, col=1)
        self._simple_panel_widgets["water_flow"] = w_widgets

        # 2. Level control loop panel (initially column 1 level)
        self._level_panel_frame = ttk.LabelFrame(self._sf, text="Level Control - Column 1", padding=(12, 8))
        self._level_panel_frame.grid(row=1, column=2, padx=8, pady=5, sticky="nsew")
        self._level_panel_frame.columnconfigure(1, weight=1)

        l_widgets = self._build_simple_level_panel_contents(self._level_panel_frame)
        self._simple_panel_widgets["level"] = l_widgets

        # 3. Air flow control panel
        a_widgets = self._build_air_flow_panel(self._sf, row=1, col=3)
        self._simple_panel_widgets["air_flow"] = a_widgets

    def _build_simple_loop_panel(self, parent, key, loop, row, col) -> dict:
        f = ttk.LabelFrame(parent, text=loop.label, padding=(12, 8))
        f.grid(row=row, column=col, padx=8, pady=5, sticky="nsew")
        f.columnconfigure(1, weight=1)

        widgets = {}

        # Setpoint
        ttk.Label(f, text=f"Setpoint ({loop.unit})", wraplength=110).grid(row=0, column=0, sticky="w", padx=4, pady=4)
        sp = ttk.Spinbox(f, from_=loop.setpoint_min, to=loop.setpoint_max,
                         textvariable=loop.setpoint_var, width=8, state="disabled")
        sp.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        widgets["sp"] = sp

        # Mode switch
        self._water_mode_auto_var.set(loop.is_auto)
        
        def _toggle():
            loop.is_auto = self._water_mode_auto_var.get()
            self._set_loop_panel_states(self._main_power_on)

        mode_btn = ttk.Checkbutton(f, text="MANUAL", style="Switch",
                                   variable=self._water_mode_auto_var, command=_toggle, state="disabled")
        mode_btn.grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=6)
        widgets["mode"] = mode_btn

        # Manual slider
        ttk.Label(f, text="Manual Output (%)").grid(row=2, column=0, sticky="w", padx=4, pady=(4, 2))
        slider_frame = ttk.Frame(f)
        slider_frame.grid(row=2, column=1, sticky="ew", padx=4, pady=(4, 2))
        slider_frame.columnconfigure(0, weight=1)

        slider = ttk.Scale(slider_frame, from_=0, to=100, variable=loop.valve_position, state="disabled")
        slider.grid(row=0, column=0, sticky="ew")

        def _sync_slider(*_a, lp=loop):
            lp.rounded_valve_position.set(round(lp.valve_position.get()))
        loop.valve_position.trace_add("write", _sync_slider)

        pct_lbl = ttk.Label(slider_frame, textvariable=loop.rounded_valve_position, width=4)
        pct_lbl.grid(row=0, column=1, padx=(4, 0))
        widgets["slider"] = slider
        widgets["pct_lbl"] = pct_lbl

        # PID constants in a row
        pid_f = ttk.Frame(f)
        pid_f.grid(row=3, column=0, columnspan=2, sticky="ew", padx=4, pady=(6, 4))

        for i, (name, var, lo, hi) in enumerate([
            ("Kc",       loop.Kc_var, -100.0, 100.0),
            ("Ti (min)", loop.Ti_var, 0.0,   100.0),
            ("Td",       loop.Td_var, 0.0,   10.0),
        ]):
            ttk.Label(pid_f, text=name, font=("Helvetica", 8)).grid(row=0, column=i, padx=3, sticky="w")
            sb = ttk.Spinbox(pid_f, textvariable=var, from_=lo, to=hi, width=6, state="disabled")
            sb.grid(row=1, column=i, padx=3, pady=2, sticky="ew")
            widgets[f"pid_{name.split()[0]}"] = sb

        return widgets

    def _build_simple_level_panel_contents(self, frame) -> dict:
        """Create the Level loop panel widgets. They will be bound dynamically to the active column."""
        # Col 1 Level is default on startup
        loop = self.loops["column1_level"]
        widgets = {}

        # Setpoint
        ttk.Label(frame, text=f"Setpoint ({loop.unit})", wraplength=110).grid(row=0, column=0, sticky="w", padx=4, pady=4)
        sp = ttk.Spinbox(frame, from_=loop.setpoint_min, to=loop.setpoint_max,
                         textvariable=loop.setpoint_var, width=8, state="disabled")
        sp.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        widgets["sp"] = sp

        # Mode switch
        self._level_mode_auto_var.set(loop.is_auto)

        def _toggle():
            col1_active = self._col_select_var.get()
            active_key = "column1_level" if col1_active else "column2_level"
            self.loops[active_key].is_auto = self._level_mode_auto_var.get()
            self._set_loop_panel_states(self._main_power_on)

        mode_btn = ttk.Checkbutton(frame, text="MANUAL", style="Switch",
                                   variable=self._level_mode_auto_var, command=_toggle, state="disabled")
        mode_btn.grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=6)
        widgets["mode"] = mode_btn

        # Manual slider
        ttk.Label(frame, text="Manual Output (%)").grid(row=2, column=0, sticky="w", padx=4, pady=(4, 2))
        slider_frame = ttk.Frame(frame)
        slider_frame.grid(row=2, column=1, sticky="ew", padx=4, pady=(4, 2))
        slider_frame.columnconfigure(0, weight=1)

        slider = ttk.Scale(slider_frame, from_=0, to=100, variable=loop.valve_position, state="disabled")
        slider.grid(row=0, column=0, sticky="ew")

        # Sync code that handles scale updates
        def _sync_slider(*_a):
            col1_active = self._col_select_var.get()
            active_key = "column1_level" if col1_active else "column2_level"
            lp = self.loops[active_key]
            lp.rounded_valve_position.set(round(lp.valve_position.get()))
        
        # Link traces to both level loops
        self.loops["column1_level"].valve_position.trace_add("write", _sync_slider)
        self.loops["column2_level"].valve_position.trace_add("write", _sync_slider)

        pct_lbl = ttk.Label(slider_frame, textvariable=loop.rounded_valve_position, width=4)
        pct_lbl.grid(row=0, column=1, padx=(4, 0))
        widgets["slider"] = slider
        widgets["pct_lbl"] = pct_lbl

        # PID constants row
        pid_f = ttk.Frame(frame)
        pid_f.grid(row=3, column=0, columnspan=2, sticky="ew", padx=4, pady=(6, 4))

        for i, name in enumerate(["Kc", "Ti", "Td"]):
            ttk.Label(pid_f, text=name if name != "Ti" else "Ti (min)", font=("Helvetica", 8)).grid(row=0, column=i, padx=3, sticky="w")
            
            # Setup correct ranges
            lo, hi = -100.0, 100.0
            if name == "Ti": lo, hi = 0.0, 100.0
            if name == "Td": lo, hi = 0.0, 10.0

            sb = ttk.Spinbox(pid_f, textvariable=getattr(loop, f"{name}_var"), from_=lo, to=hi, width=6, state="disabled")
            sb.grid(row=1, column=i, padx=3, pady=2, sticky="ew")
            widgets[f"pid_{name}"] = sb

        return widgets

    def _build_air_flow_panel(self, parent, row, col) -> dict:
        f = ttk.LabelFrame(parent, text="Air Flow Control", padding=(12, 8))
        f.grid(row=row, column=col, padx=8, pady=5, sticky="nsew")
        f.columnconfigure(1, weight=1)

        widgets = {}

        # Setpoint
        ttk.Label(f, text="Setpoint (SLPM)", wraplength=110).grid(row=0, column=0, sticky="w", padx=4, pady=4)
        sp = ttk.Spinbox(f, from_=0, to=1000, textvariable=self._air_setpoint_var, width=8, state="disabled")
        sp.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        widgets["sp"] = sp

        # Slider
        ttk.Label(f, text="Adjust Flow").grid(row=1, column=0, sticky="w", padx=4, pady=(4, 2))
        slider_frame = ttk.Frame(f)
        slider_frame.grid(row=1, column=1, sticky="ew", padx=4, pady=(4, 2))
        slider_frame.columnconfigure(0, weight=1)

        slider = ttk.Scale(slider_frame, from_=0, to=1000, variable=self._air_setpoint_double_var, state="disabled")
        slider.grid(row=0, column=0, sticky="ew")

        def _sync_air_slider(*_a):
            self._air_setpoint_var.set(str(round(self._air_setpoint_double_var.get())))
        self._air_setpoint_double_var.trace_add("write", _sync_air_slider)

        def _sync_air_spinbox(*_a):
            try:
                self._air_setpoint_double_var.set(float(self._air_setpoint_var.get()))
            except ValueError:
                pass
        self._air_setpoint_var.trace_add("write", _sync_air_spinbox)

        pct_lbl = ttk.Label(slider_frame, textvariable=self._air_setpoint_var, width=4)
        pct_lbl.grid(row=0, column=1, padx=(4, 0))
        widgets["slider"] = slider

        # Read-only Sensor Entries
        ttk.Label(f, text="Air Flowrate (SLPM)").grid(row=2, column=0, sticky="w", padx=4, pady=(6, 2))
        entry_air = ttk.Entry(f, textvariable=self.sensors["air_flowrate"].value_var, state="disabled", width=8)
        entry_air.grid(row=2, column=1, sticky="ew", padx=4, pady=(6, 2))
        widgets["sensor_air"] = entry_air

        ttk.Label(f, text="Delta CO2 (ppm)").grid(row=3, column=0, sticky="w", padx=4, pady=(6, 2))
        entry_co2 = ttk.Entry(f, textvariable=self.sensors["co2_concentration"].value_var, state="disabled", width=8)
        entry_co2.grid(row=3, column=1, sticky="ew", padx=4, pady=(6, 2))
        widgets["sensor_co2"] = entry_co2

        return widgets

    # ══════════════════════════════════════════════════════════════════
    # Enable / disable panel states
    # ══════════════════════════════════════════════════════════════════

    def _set_initial_states(self):
        self._power_sw.configure(state="disabled")
        self._log_btn.configure(state="disabled")
        self._set_loop_panel_states(False)

    def _set_loop_panel_states(self, enabled):
        """Unified method to manage states of loop control panel widgets."""
        # 1. Water panel states
        w_widgets = self._simple_panel_widgets["water_flow"]
        w_loop = self.loops["water_flow"]
        if enabled:
            w_widgets["mode"].configure(state="normal")
            w_widgets["pid_Kc"].configure(state="normal")
            w_widgets["pid_Ti"].configure(state="normal")
            w_widgets["pid_Td"].configure(state="normal")
            if w_loop.is_auto:
                w_widgets["mode"].configure(text="AUTO")
                w_widgets["sp"].configure(state="normal")
                w_widgets["slider"].configure(state="disabled")
            else:
                w_widgets["mode"].configure(text="MANUAL")
                w_widgets["sp"].configure(state="disabled")
                w_widgets["slider"].configure(state="normal")
        else:
            for w in w_widgets.values():
                try: w.configure(state="disabled")
                except Exception: pass
            w_widgets["mode"].configure(text="MANUAL")

        # 2. Level panel states (switched dynamically)
        l_widgets = self._simple_panel_widgets["level"]
        col1_active = self._col_select_var.get()
        l_loop = self.loops["column1_level"] if col1_active else self.loops["column2_level"]
        if enabled:
            l_widgets["mode"].configure(state="normal")
            l_widgets["pid_Kc"].configure(state="normal")
            l_widgets["pid_Ti"].configure(state="normal")
            l_widgets["pid_Td"].configure(state="normal")
            if l_loop.is_auto:
                l_widgets["mode"].configure(text="AUTO")
                l_widgets["sp"].configure(state="normal")
                l_widgets["slider"].configure(state="disabled")
            else:
                l_widgets["mode"].configure(text="MANUAL")
                l_widgets["sp"].configure(state="disabled")
                l_widgets["slider"].configure(state="normal")
        else:
            for w in l_widgets.values():
                try: w.configure(state="disabled")
                except Exception: pass
            l_widgets["mode"].configure(text="MANUAL")

        # 3. Air panel states
        a_widgets = self._simple_panel_widgets["air_flow"]
        if enabled:
            a_widgets["sp"].configure(state="normal")
            a_widgets["slider"].configure(state="normal")
        else:
            a_widgets["sp"].configure(state="disabled")
            a_widgets["slider"].configure(state="disabled")

    def _enable_powered_controls(self):
        self._log_btn.configure(state="normal")
        self._set_loop_panel_states(True)

    def _disable_powered_controls(self):
        self._log_btn.configure(state="disabled")
        self._set_loop_panel_states(False)
        
        if hasattr(self, "logger") and self.logger.is_logging:
            self.logger.stop()
            self._logging_text_var.set("Start Logging")
            self._data_point_count.set(0)

    # ══════════════════════════════════════════════════════════════════
    # Event callbacks
    # ══════════════════════════════════════════════════════════════════

    def _on_connection_choice(self, choice):
        if choice == "USB":       self._connect("T7", "USB",      "ANY")
        elif choice == "Ethernet": self._connect("T7", "ETHERNET", config.ETHERNET_ADDRESS)
        elif choice == "Disconnect": self._disconnect()

    def _connect(self, model, connection, identifier):
        try:
            self.daq.connect(model, connection, identifier)
            self._status_lbl.config(text="Connected", style="Green.TLabel")
            self._power_sw.configure(state="normal")
            self._on_column_select()
        except Exception as exc:
            self._status_lbl.config(text=f"Failed: {exc}", style="Red.TLabel")

    def _disconnect(self):
        self.daq.disconnect()
        self._status_lbl.config(text="Simulated Mode", style="Red.TLabel")
        self._power_sw.configure(state="disabled")
        self._main_power_on = False
        self._main_power_var.set(False)
        self._power_sw.config(text="Main Power: OFF")
        self._disable_powered_controls()

    def _on_power_toggle(self):
        self._main_power_on = not self._main_power_on
        if self._main_power_on:
            self._power_sw.config(text="Main Power: ON")
            self.daq.write(config.MAIN_POWER_PIN, 1)
            self._enable_powered_controls()
        else:
            self._power_sw.config(text="Main Power: OFF")
            self.daq.write(config.MAIN_POWER_PIN, 0)
            self._disable_powered_controls()

    def _on_column_select(self, *_args):
        col1_active = self._col_select_var.get()
        voltage = 0.0 if col1_active else 5.0
        self.daq.write(config.COLUMN_SELECTOR_PIN, voltage)

        # Update P&ID canvas visual indicators
        col_num = 1 if col1_active else 2
        if col1_active:
            self._col1_lbl.config(bg="#2E7D32", fg="white")
            self._col1_indicator_val.set("COLUMN 1 (ACTIVE)")
            self._col2_lbl.config(bg="#B0BEC5", fg="#37474F")
            self._col2_indicator_val.set("COLUMN 2 (INACTIVE)")
        else:
            self._col1_lbl.config(bg="#B0BEC5", fg="#37474F")
            self._col1_indicator_val.set("COLUMN 1 (INACTIVE)")
            self._col2_lbl.config(bg="#2E7D32", fg="white")
            self._col2_indicator_val.set("COLUMN 2 (ACTIVE)")

        # Update active labels on the P&ID canvas
        if hasattr(self, "_active_dp_lbl_widget"):
            self._active_dp_lbl_widget.config(text=f"Column {col_num} Pressure Drop\n(Pa)")
        if hasattr(self, "_active_level_lbl_widget"):
            self._active_level_lbl_widget.config(text=f"Column {col_num} Level\n(mm)")

        # Update level panel bindings
        self._update_level_panel_bindings()
        self._set_loop_panel_states(self._main_power_on)

    def _update_level_panel_bindings(self):
        col1_active = self._col_select_var.get()
        active_key = "column1_level" if col1_active else "column2_level"
        loop = self.loops[active_key]

        # Update panel title
        self._level_panel_frame.config(text=f"Level Control - Column {1 if col1_active else 2}")

        # Update widget configurations to point to active loop variables
        widgets = self._simple_panel_widgets["level"]
        widgets["sp"].config(textvariable=loop.setpoint_var, from_=loop.setpoint_min, to=loop.setpoint_max)
        widgets["slider"].config(variable=loop.valve_position)
        widgets["pct_lbl"].config(textvariable=loop.rounded_valve_position)
        
        # update PID entries
        widgets["pid_Kc"].config(textvariable=loop.Kc_var)
        widgets["pid_Ti"].config(textvariable=loop.Ti_var)
        widgets["pid_Td"].config(textvariable=loop.Td_var)

        # Sync mode toggle variable
        self._level_mode_auto_var.set(loop.is_auto)

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
            text="Light Mode" if self._theme_mode.get() else "Dark Mode")
        
        try:
            self.style.theme_use(f"forest-{mode}")
        except Exception:
            pass
            
        bg = self.style.lookup(".", "background")
        self.root.configure(background=bg)
        self._canvas_outer.configure(bg=bg)
        self.root.update_idletasks()

    def _on_mousewheel(self, event):
        scroll = -event.delta * 3 if event.delta in (1, -1) \
                 else int(-1 * (event.delta / 120)) * 3
        self._canvas_outer.yview_scroll(scroll, "units")

    # ══════════════════════════════════════════════════════════════════
    # Periodic update loop
    # ══════════════════════════════════════════════════════════════════

    def _schedule_updates(self):
        self.root.after(UPDATE_INTERVAL_MS, self._update_all_sensors)
        self.root.after(UPDATE_INTERVAL_MS, self._update_all_loops)
        self.root.after(UPDATE_INTERVAL_MS, self._update_air_setpoint_output)

    def _update_all_sensors(self):
        # Update cold junction temperature for thermocouple compensation
        try:
            cj_k = self.daq.read("TEMPERATURE_DEVICE_K")
            config._cj_temp_c = cj_k - 273.15
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

        # Update active pressure drop variable
        col1_active = self._col_select_var.get()
        active_dp_key = "column1_pressure_drop" if col1_active else "column2_pressure_drop"
        if active_dp_key in self.sensors:
            self._active_pressure_drop_var.set(self.sensors[active_dp_key].value_var.get())

        self.root.after(UPDATE_INTERVAL_MS, self._update_all_sensors)

    def _update_all_loops(self):
        col1_active = self._col_select_var.get()

        for key, loop in self.loops.items():
            # Read process variable
            try:
                raw = self.daq.read(loop.input_pin)
                loop.set_measured(loop.apply_calibration(raw))
            except Exception:
                loop.set_error()

            # Column selector gate (only the active column's loop should write to DAC0)
            if key == "column1_level" and not col1_active:
                continue
            if key == "column2_level" and col1_active:
                continue

            # Output
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
                    self.daq.write(loop.output_pin, loop.get_manual_voltage())
            except Exception as exc:
                print(f"[Loop {key}] output error: {exc}")

        # Update water exit valve percentage label on P&ID dynamically
        active_level_key = "column1_level" if col1_active else "column2_level"
        self._water_exit_valve_percent_var.set(str(self.loops[active_level_key].rounded_valve_position.get()))

        # Update active level variable
        self._active_level_var.set(self.loops[active_level_key].measured_var.get())

        self.root.after(UPDATE_INTERVAL_MS, self._update_all_loops)

    def _update_air_setpoint_output(self):
        if hasattr(self, "_air_setpoint_var"):
            try:
                val = float(self._air_setpoint_var.get())
                voltage = val / config.AIR_SETPOINT_SCALE
                self.daq.write(config.AIR_SETPOINT_PIN, voltage)
            except Exception as exc:
                print(f"[Air setpoint] {exc}")
        self.root.after(UPDATE_INTERVAL_MS, self._update_air_setpoint_output)

    def _sync_air_valve_percent(self):
        try:
            val = float(self._air_setpoint_var.get())
            pct = round(val / 10.0)
            self._air_valve_percent_var.set(f"{pct}")
        except ValueError:
            self._air_valve_percent_var.set("0")
