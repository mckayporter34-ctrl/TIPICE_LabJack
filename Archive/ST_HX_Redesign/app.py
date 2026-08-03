# app.py — Shell and Tube Heat Exchanger — Redesigned P&ID Interface
# ===================================================================

import os
import math
import time
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

import config
from sensor import Sensor
from control_loop import ControlLoop
from pid_controller import PIDController
from labjack_interface import LabJackInterface
from data_logger import DataLogger

UPDATE_INTERVAL_MS = 500
DT_MINUTES         = UPDATE_INTERVAL_MS / 1000 / 60
ANIM_MS            = 100          # animation tick ~25 fps

# ── Canvas dimensions (scaled for 1680x1050 monitor) ──────────────────────────
CW, CH = 1300, 600

# ── Colors ────────────────────────────────────────────────────────────────────
C_WATER  = "#1565C0"
C_STEAM  = "#C62828"
C_PIPE   = "#455A64"
C_EQUIP  = "#ECEFF1"
C_STROKE = "#263238"
C_BG     = "#F5F7FA"

# ── Pipe paths for animation particles (scaled by 0.6 dynamically) ────────────
WATER_PATH_1504 = [
    (424, 292),  # HX outlet (top)
    (424, 237),  # top pipe left turn
    (1241, 237), # top pipe right turn
    (1241, 393), # Tank inlet
    (1241, 543), # Tank outlet (bottom)
    (1241, 689), # bottom pipe right corner
    (1071, 689), # pump inlet
    (1036, 670), # pump outlet
    (777, 670),  # flowmeter inlet
    (760, 685),  # flowmeter outlet
    (582, 685),  # flow control valve inlet
    (581, 688),  # flow control valve outlet
    (424, 688),  # HX bottom pipe corner
    (424, 528),  # HX bottom inlet
    (424, 291),  # through HX back to top
]

STEAM_PATH_1504 = [
    (50, 378),   # steam source
    (155, 378),  # steam control valve
    (160, 378),
    (355, 378),  # HX steam inlet
    (424, 378),  # HX middle
    (424,550),   # HX bottom
    (367,550),   #bottom out
    (50,550),    #dissapear
]


# Scale flow paths dynamically from 1504x924 space to active canvas size
SCALE_PATH_X = CW / 1504
SCALE_PATH_Y = CH / 924
WATER_PATH     = [(int(x * SCALE_PATH_X), int(y * SCALE_PATH_Y)) for x, y in WATER_PATH_1504]
STEAM_PATH  = [(int(x * SCALE_PATH_X), int(y * SCALE_PATH_Y)) for x, y in STEAM_PATH_1504]


# ══════════════════════════════════════════════════════════════════════════════
# Flow animation particle
# ══════════════════════════════════════════════════════════════════════════════

class _Particle:
    def __init__(self, canvas, path, color, r=4, speed=2.5, offset=0.0):
        self.canvas = canvas
        self.path   = path
        self.r      = r
        self.speed  = speed
        self._len   = self._total()
        self.prog   = offset * self._len
        x, y = self._at(self.prog)
        self._id = canvas.create_oval(
            x-r, y-r, x+r, y+r,
            fill=color, outline='', state='hidden', tags='particle'
        )

    def _total(self):
        t = 0.0
        for i in range(len(self.path) - 1):
            t += math.hypot(self.path[i+1][0] - self.path[i][0],
                            self.path[i+1][1] - self.path[i][1])
        return max(t, 1.0)

    def _at(self, d):
        r = d % self._len
        for i in range(len(self.path) - 1):
            seg = math.hypot(self.path[i+1][0] - self.path[i][0],
                             self.path[i+1][1] - self.path[i][1])
            if seg < 0.001:
                continue
            if r <= seg:
                t = r / seg
                return (self.path[i][0] + t * (self.path[i+1][0] - self.path[i][0]),
                        self.path[i][1] + t * (self.path[i+1][1] - self.path[i][1]))
            r -= seg
        return self.path[-1]

    def step(self):
        self.prog = (self.prog + self.speed) % self._len
        x, y = self._at(self.prog)
        r = self.r
        self.canvas.coords(self._id, x-r, y-r, x+r, y+r)

    def show(self): self.canvas.itemconfig(self._id, state='normal')
    def hide(self): self.canvas.itemconfig(self._id, state='hidden')


# ══════════════════════════════════════════════════════════════════════════════
# Main application class
# ══════════════════════════════════════════════════════════════════════════════

class ShellTubeHXRedesignApp:
    BASE_WIDTH  = 1440
    BASE_HEIGHT = 800

    def __init__(self):
        self.root = tk.Tk()
        self.root.geometry("1600x900+1600+0") #Open on monitor 2  - change. 
        self.root.title(config.SYSTEM_NAME + " — Redesigned P&ID View")
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
        self._pump_status_str = tk.StringVar(value="OFF")

        self._logging_text_var = tk.StringVar(value="Start Logging")
        self._log_interval_var = tk.DoubleVar(value=1.0)
        self._data_point_count = tk.IntVar(value=0)

        # Flow animation control switches
        self._anim_test_var    = tk.BooleanVar(value=True)

        self._simple_panel_widgets = {}
        self._btn_map_ref          = {}
        self._overlay_cards        = []   # tkinter frame canvas widgets
        self._particles            = []

        self._configure_root()
        self._load_themes()
        self._build_ui()
        self._create_particles()
        self._set_initial_states()
        self._build_logger()
        self._schedule_updates()

        self.root.mainloop()

    # ══════════════════════════════════════════════════════════════════
    # Initialisation helpers
    # ══════════════════════════════════════════════════════════════════

    def _build_sensors(self):
        return {
            key: Sensor(key=key, label=cfg["label"], unit=cfg["unit"],
                        pin=cfg["pin"], calibration=cfg["calibration"])
            for key, cfg in config.SENSOR_CONFIGS.items()
        }

    def _build_control_loops(self):
        loops = {}
        for key, cfg in config.CONTROL_LOOP_CONFIGS.items():
            d = cfg.get("pid_defaults", {})
            loops[key] = ControlLoop(
                key=key, label=cfg["label"], unit=cfg["unit"],
                input_pin=cfg["input_pin"], output_pin=cfg["output_pin"],
                calibration=cfg["calibration"],
                setpoint_min=cfg.get("setpoint_min", 0),
                setpoint_max=cfg.get("setpoint_max", 100),
                pid=PIDController(Kc=d.get("Kc", 1.0), Ti=d.get("Ti", 1.0),
                                  Td=d.get("Td", 0.0),
                                  output_max=cfg.get("output_max", 5.0)),
                extra_sensor_key=cfg.get("extra_sensor_key"),
            )
            loops[key].setpoint_var.set(str(cfg.get("default_setpoint", 0)))
        return loops

    def _configure_root(self):
        # Column 0: Left Column (Controls & logging)
        # Columns 1, 2, 3: Canvas (top) and horizontal loop panels (bottom)
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.columnconfigure(2, weight=1)
        self.root.columnconfigure(3, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=0)
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
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
        self.logger = DataLogger(sources=sources, folder=config.LOG_FOLDER,
                                 count_var=self._data_point_count)

    # ══════════════════════════════════════════════════════════════════
    # UI construction
    # ══════════════════════════════════════════════════════════════════

    def _build_ui(self):
        container = ttk.Frame(self.root)
        container.pack(fill="both", expand=True)

        self._canvas_outer = tk.Canvas(container)
        self._canvas_outer.pack(side="left", fill="both", expand=True)
        
        v_sb = ttk.Scrollbar(container, orient="vertical",
                               command=self._canvas_outer.yview)
        v_sb.pack(side="right", fill="y")
        h_sb = ttk.Scrollbar(self.root, orient="horizontal",
                               command=self._canvas_outer.xview)
        h_sb.pack(side="bottom", fill="x")

        self._canvas_outer.configure(yscrollcommand=v_sb.set,
                                     xscrollcommand=h_sb.set)
        bg = self.style.lookup("TFrame", "background")
        self._canvas_outer.configure(bg=bg)

        self._sf = ttk.Frame(self._canvas_outer)
        self._canvas_outer.create_window((0, 0), window=self._sf, anchor="nw")
        self._sf.bind("<Configure>", lambda e: self._canvas_outer.configure(
            scrollregion=self._canvas_outer.bbox("all")))
        self._sf.bind("<Enter>",
            lambda e: self.root.bind_all("<MouseWheel>", self._on_mousewheel))
        self._sf.bind("<Leave>",
            lambda e: self.root.unbind_all("<MouseWheel>"))

        self._build_left_column()
        self._build_pid_canvas()
        self._build_horizontal_panels()

    # ── Left column ────────────────────────────────────────────────────────────

    def _build_left_column(self):
        col = ttk.Frame(self._sf)
        col.grid(row=0, column=0, rowspan=2, padx=(10, 5), pady=10, sticky="nsew")

        # Controls
        ctrl = ttk.LabelFrame(col, text="Controls", padding=(30, 15))
        ctrl.pack(fill="x", pady=(0, 8))

        self._connect_dd = ttk.OptionMenu(
            ctrl, self._connection_var, "Connect to LabJack",
            "USB", "Ethernet", "Disconnect",
            command=self._on_connection_choice)
        self._connect_dd.pack(fill="x", pady=(4, 4))

        self._status_lbl = ttk.Label(ctrl, text="Not connected", padding=(4, 2))
        self._status_lbl.pack(fill="x")

        self._power_sw = ttk.Checkbutton(
            ctrl, text="Main Power: OFF", style="Switch",
            variable=self._main_power_var, command=self._on_power_toggle)
        self._power_sw.pack(fill="x", pady=6)

        self._pump_sw = ttk.Checkbutton(
            ctrl, text="Pump: OFF", style="Switch",
            variable=self._pump_var, command=self._on_pump_toggle)
        self._pump_sw.pack(fill="x", pady=(0, 4))

        # Flow animation test mode switch
        self._anim_test_sw = ttk.Checkbutton(
            ctrl, text="Flow Animation: ON", style="Switch",
            variable=self._anim_test_var, command=self._on_anim_test_toggle)
        self._anim_test_sw.pack(fill="x", pady=(6, 4))

        # Data logging
        log = ttk.LabelFrame(col, text="Data Logging", padding=(30, 15))
        log.pack(fill="x", pady=(0, 8))

        self._log_btn = ttk.Checkbutton(
            log, textvariable=self._logging_text_var,
            style="ToggleButton", command=self._on_toggle_logging,
            padding=(15, 12), state="disabled")
        self._log_btn.pack(fill="x", pady=4)

        r = ttk.Frame(log); r.pack(fill="x", pady=2)
        ttk.Label(r, text="Interval (s)").pack(side="left")
        ttk.Spinbox(r, from_=0, to=100, textvariable=self._log_interval_var,
                    width=5).pack(side="right")

        r2 = ttk.Frame(log); r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="Count").pack(side="left")
        ttk.Entry(r2, textvariable=self._data_point_count,
                  state="disabled", width=6).pack(side="right")

        # Apparatus image panel
        img_f = ttk.LabelFrame(col, text="Apparatus Image", padding=10)
        img_f.pack(fill="x", pady=(0, 8))
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            img2 = Image.open(os.path.join(base_dir, "assets", "apparatus.png"))
            img2.thumbnail((200, 160))
            self._appar_img = ImageTk.PhotoImage(img2)
            ttk.Label(img_f, image=self._appar_img, anchor="center").pack()
        except Exception:
            ttk.Label(img_f, text="No Image Found", anchor="center").pack()

        # Theme toggle (no BYU/TIPICE logo is rendered)
        self._theme_btn = ttk.Checkbutton(
            col, text="Dark Mode", style="ToggleButton",
            command=self._on_theme_toggle)
        self._theme_btn.pack(fill="x")

    # ── P&ID canvas ────────────────────────────────────────────────────────────

    def _build_pid_canvas(self):
        # Spans columns 1 to 3 in row 0. Use tk.LabelFrame for custom background.
        outer = tk.LabelFrame(self._sf, text="P&ID — Shell & Tube Heat Exchanger Redesign",
                              bg="white", fg="#263238", font=("Helvetica", 10, "bold"),
                              bd=1, relief="solid", padx=10, pady=10)
        outer.grid(row=0, column=1, columnspan=3, padx=5, pady=10, sticky="nsew")

        # Canvas size scaled to CW, CH. Center it in the parent Frame.
        self._pid = tk.Canvas(outer, width=CW, height=CH, bg="white",
                              highlightthickness=0)
        self._pid.pack(expand=True)

        # Load and resize background P&ID image dynamically
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            bg_path = os.path.join(base_dir, "PI_diagram.png")
            self._bg_img_raw = Image.open(bg_path)
            self._bg_img_resized = self._bg_img_raw.resize((CW, CH), Image.Resampling.LANCZOS)
            self._bg_img = ImageTk.PhotoImage(self._bg_img_resized)
            self._pid.create_image(0, 0, anchor="nw", image=self._bg_img)
        except Exception as e:
            print(f"Error loading P&ID background image: {e}")
            self._pid.create_text(CW//2, CH//2, text="P&ID Diagram Image Not Found", font=("Helvetica", 16))

        # Pump lighted indicator (light circle next to the pump)
        self._pump_indicator = self._pid.create_oval(
            970+7, 485+7, 970+7, 485+7,
            fill="#F44336", outline="#263238", width=1
        )

        self._create_sensor_overlays()

    # ── Sensor value overlays ──────────────────────────────────────────────────

    def _create_sensor_overlays(self):
        """
        Embed actual entry-style boxes (Labels + Entries) directly onto the canvas.
        """
        s   = self.sensors
        lps = self.loops

        # Each entry: (x, y, label, textvariable)
        overlays = [
            (245, 162, f"{s['water_outlet_temp'].label} ({s['water_outlet_temp'].unit})", s['water_outlet_temp'].value_var),
            (245, 425, f"{s['water_inlet_temp'].label} ({s['water_inlet_temp'].unit})", s['water_inlet_temp'].value_var),
            (530, 244, f"{lps['steam_pressure'].label} ({lps['steam_pressure'].unit})", lps['steam_pressure'].measured_var),
            (174, 298, f"{lps['steam_pressure'].label} Valve (%)", lps['steam_pressure'].rounded_valve_position),
            (555, 336, f"{s['tube_side_pressure_drop'].label} ({s['tube_side_pressure_drop'].unit})", s['tube_side_pressure_drop'].value_var),
            (1180, 45,  f"{s['makeup_temperature'].label} ({s['makeup_temperature'].unit})", s['makeup_temperature'].value_var),
            (1175, 110, f"{s['makeup_flowrate'].label} ({s['makeup_flowrate'].unit})", s['makeup_flowrate'].value_var),
            (1205, 298, f"{lps['level'].label} ({lps['level'].unit})", lps['level'].measured_var),
            (1150, 495, f"{lps['level'].label} Valve (%)", lps['level'].rounded_valve_position),
            (896, 504, "Pump Status", self._pump_status_str),
            (672, 504, f"{lps['flowrate'].label} ({lps['flowrate'].unit})", lps['flowrate'].measured_var),
            (506, 504, f"{lps['flowrate'].label} Valve (%)", lps['flowrate'].rounded_valve_position),
        ]

        for x, y, label, var in overlays:
            # Create the card container with a white background to blend into the canvas
            card = tk.Frame(self._pid, bg="white", padx=0, pady=0,bd=0)
            
            # Label (increased font size by 50% from default, size 12, white background)
            lbl = tk.Label(card, text=label, font=("Helvetica", 12, "bold"),
                           bg="white", fg="#263238", anchor="center")
            lbl.pack(fill="x", padx=0, pady=(0, 0))
            
            # Entry box style (disabled read-only, matching other Heat Exchanger codes)
            entry = ttk.Entry(card, textvariable=var, state="disabled", width=8,
                              justify="center", font=("Helvetica", 12, "bold"))
            entry.pack(fill="x", padx=0, pady=(2, 4))
            
            # Embed the widget card into canvas
            self._pid.create_window(x, y, window=card, anchor="center")
            self._overlay_cards.append(card)

    # ── Horizontal bottom control panels ───────────────────────────────────────

    def _build_horizontal_panels(self):
        # Grid loop panels horizontally across the bottom row (row 1)
        # under columns 1, 2, and 3 respectively.
        order = ["level", "flowrate", "steam_pressure"]
        for idx, key in enumerate(order):
            if key in self.loops:
                w = self._build_simple_loop_panel(self._sf, key, self.loops[key], row=1, col=idx+1)
                self._simple_panel_widgets[key] = w

    def _build_simple_loop_panel(self, parent, key, loop, row, col):
        """
        Compact control panel gridded at the bottom side-by-side: 
        setpoint, manual/auto switch, manual slider, and PID constants.
        """
        f = ttk.LabelFrame(parent, text=loop.label, padding=(12, 8))
        f.grid(row=row, column=col, padx=8, pady=5, sticky="nsew")
        f.columnconfigure(1, weight=1)

        widgets = {}

        # Setpoint
        ttk.Label(f, text=f"Setpoint ({loop.unit})",
                  wraplength=110).grid(row=0, column=0, sticky="w", padx=4, pady=4)
        sp = ttk.Spinbox(f, from_=loop.setpoint_min, to=loop.setpoint_max,
                         textvariable=loop.setpoint_var, width=8,
                         state="disabled")
        sp.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        widgets["sp"] = sp

        # Measured Value
        ttk.Label(f, text=f"Measured ({loop.unit})",
                  wraplength=110).grid(row=1, column=0, sticky="w", padx=4, pady=4)
        meas = ttk.Entry(f, textvariable=loop.measured_var, width=8,
                         state="disabled")
        meas.grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        widgets["meas"] = meas

        # Mode switch
        mode_var = tk.BooleanVar(value=loop.is_auto)
        
        def _toggle(lp=loop, k=key, var=mode_var):
            lp.is_auto = var.get()
            self._set_loop_panel_states(self._main_power_on)

        mode_btn = ttk.Checkbutton(f, text="MANUAL", style="Switch",
                                   variable=mode_var, command=_toggle,
                                   state="disabled")
        mode_btn.grid(row=2, column=0, columnspan=2,
                      sticky="ew", padx=4, pady=6)
        widgets["mode"] = mode_btn
        self._btn_map_ref[key] = mode_btn

        # Manual slider
        ttk.Label(f, text="Manual Output (%)").grid(
            row=3, column=0, sticky="w", padx=4,pady=(4, 2))
        slider_frame = ttk.Frame(f)
        slider_frame.grid(row=3, column=1, sticky="ew", padx=4,pady=(4, 2))
        slider_frame.columnconfigure(0, weight=1)

        slider = ttk.Scale(slider_frame, from_=0, to=100,
                           variable=loop.valve_position, state="disabled")
        slider.grid(row=0, column=0, sticky="ew")

        def _sync_slider(*_a, lp=loop):
            lp.rounded_valve_position.set(round(lp.valve_position.get()))
        loop.valve_position.trace_add("write", _sync_slider)

        pct_lbl = ttk.Label(slider_frame,
                            textvariable=loop.rounded_valve_position, width=4)
        pct_lbl.grid(row=0, column=1, padx=(4, 0))
        widgets["slider"] = slider

        # PID constants in a row
        pid_f = ttk.Frame(f)
        pid_f.grid(row=4, column=0, columnspan=2, sticky="ew",
                   padx=4, pady=(6, 4))

        for i, (name, var, lo, hi) in enumerate([
            ("Kc",      loop.Kc_var, -1000, 1000),
            ("Ti (min)", loop.Ti_var, 0,    1000),
            ("Td",      loop.Td_var, 0,     100),
        ]):
            ttk.Label(pid_f, text=name, font=("Helvetica", 8)).grid(
                row=0, column=i, padx=3, sticky="w")
            sb = ttk.Spinbox(pid_f, textvariable=var, from_=lo, to=hi,
                             width=6, state="disabled")
            sb.grid(row=1, column=i, padx=3, pady=2, sticky="ew")
            widgets[f"pid_{name}"] = sb

        return widgets

    # ══════════════════════════════════════════════════════════════════
    # Flow animation
    # ══════════════════════════════════════════════════════════════════

    def _create_particles(self):
        N_WATER = 12
        N_STEAM = 6
        for i in range(N_WATER):
            self._particles.append(
                _Particle(self._pid, WATER_PATH, C_WATER,
                          r=4, speed=3.0, offset=i/N_WATER))
        for i in range(N_STEAM):
            self._particles.append(
                _Particle(self._pid, STEAM_PATH, C_STEAM,
                          r=4, speed=2.5, offset=i/N_STEAM))

        self._pid.tag_raise("particle")

    def _animate(self):
        anim_enabled = self._anim_test_var.get()
        if self._main_power_on:
            water_on = self._pump_on and anim_enabled
            steam_on = anim_enabled
        else:
            water_on = anim_enabled
            steam_on = anim_enabled

        # First 12 are water, next 12 are steam
        for i, p in enumerate(self._particles):
            is_water = i < 12
            active   = water_on if is_water else steam_on
            if active:
                p.show()
                p.step()
            else:
                p.hide()

        self._pid.tag_raise("particle")
        self.root.after(ANIM_MS, self._animate)

    # ══════════════════════════════════════════════════════════════════
    # Enable / disable panel states
    # ══════════════════════════════════════════════════════════════════

    def _set_initial_states(self):
        self._power_sw.configure(state="disabled")
        self._pump_sw.configure(state="disabled")
        self._log_btn.configure(state="disabled")
        self._set_loop_panel_states(False)
        self._update_pump_indicator()

    def _set_loop_panel_states(self, enabled):
        """Unified method to manage states of loop control panel widgets."""
        for key, widgets in self._simple_panel_widgets.items():
            loop = self.loops[key]
            if enabled:
                widgets["mode"].configure(state="normal")
                widgets["pid_Kc"].configure(state="normal")
                widgets["pid_Ti"].configure(state="normal")
                widgets["pid_Td"].configure(state="normal")
                
                if loop.is_auto:
                    widgets["mode"].configure(text="AUTO")
                    widgets["sp"].configure(state="normal")
                    widgets["slider"].configure(state="disabled")
                    try:
                        loop.pid.initialize(loop.get_manual_voltage())
                    except Exception:
                        loop.pid.reset()
                else:
                    widgets["mode"].configure(text="MANUAL")
                    widgets["sp"].configure(state="disabled")
                    widgets["slider"].configure(state="normal")
                    loop.pid.reset()
            else:
                for w in widgets.values():
                    try: w.configure(state="disabled")
                    except Exception: pass
                widgets["mode"].configure(text="MANUAL")

    def _update_pump_indicator(self):
        """Updates the fill color of the pump LED indicator circle."""
        color = "#4CAF50" if self._pump_on and self._main_power_on else "#F44336"
        self._pid.itemconfig(self._pump_indicator, fill=color)

    def _enable_powered_controls(self):
        self._pump_sw.configure(state="normal")
        self._log_btn.configure(state="normal")
        self._set_loop_panel_states(True)
        self._update_pump_indicator()

    def _disable_powered_controls(self):
        self._pump_sw.configure(state="disabled")
        self._log_btn.configure(state="disabled")
        self._set_loop_panel_states(False)
        
        if hasattr(self, "logger") and self.logger.is_logging:
            self.logger.stop()
            self._logging_text_var.set("Start Logging")
            self._data_point_count.set(0)
            
        if self._pump_on:
            self._pump_on = False
            self._pump_var.set(False)
            self._pump_sw.config(text="Pump: OFF")
            self.daq.write(config.PUMP_SWITCH_PIN, 0)
            self._pump_status_str.set("OFF")

        self._update_pump_indicator()

    # ══════════════════════════════════════════════════════════════════
    # Event callbacks
    # ══════════════════════════════════════════════════════════════════

    def _on_anim_test_toggle(self):
        state = self._anim_test_var.get()
        self._anim_test_sw.config(text=f"Flow Animation: {'ON' if state else 'OFF'}")

    def _on_connection_choice(self, choice):
        if choice == "USB":       self._connect("T7", "USB",      "ANY")
        elif choice == "Ethernet": self._connect("T7", "ETHERNET", config.ETHERNET_ADDRESS)
        elif choice == "Disconnect": self._disconnect()

    def _configure_ain_channels(self):
        for ch, settings in config.AIN_CONFIGS.items():
            for reg, val in settings.items():
                self.daq.write(f"{ch}_{reg}", val)

    def _connect(self, model, connection, identifier):
        try:
            self.daq.connect(model, connection, identifier)
            self._configure_ain_channels()
            self._status_lbl.config(text="Connected", style="Green.TLabel")
            self._power_sw.configure(state="normal")
        except Exception as exc:
            self._status_lbl.config(text=f"Failed: {exc}", style="Red.TLabel")

    def _disconnect(self):
        self.daq.disconnect()
        self._status_lbl.config(text="Disconnected", style="Green.TLabel")
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

    def _on_pump_toggle(self):
        self._pump_on = not self._pump_on
        if self._pump_on:
            self._pump_sw.config(text="Pump: ON")
            self.daq.write(config.PUMP_SWITCH_PIN, 1)
            self._pump_status_str.set("ON")
        else:
            self._pump_sw.config(text="Pump: OFF")
            self.daq.write(config.PUMP_SWITCH_PIN, 0)
            self._pump_status_str.set("OFF")
        self._update_pump_indicator()

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
        self.style.theme_use(f"forest-{mode}")
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
        self.root.after(ANIM_MS,            self._animate)

    def _update_all_sensors(self):
        # Update cold junction temperature for thermocouple compensation
        try:
            cj_k = self.daq.read(config.COLD_JUNCTION_REGISTER)
            config._cj_temp_c[0] = cj_k - 273.15
        except Exception:
            pass

        # Read and update all sensors
        for sensor in self.sensors.values():
            if not sensor.is_configured():
                sensor.set_error(); continue
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
                    self.daq.write(loop.output_pin, loop.get_manual_voltage())
            except Exception as exc:
                print(f"[Loop {key}] {exc}")

        self.root.after(UPDATE_INTERVAL_MS, self._update_all_loops)
