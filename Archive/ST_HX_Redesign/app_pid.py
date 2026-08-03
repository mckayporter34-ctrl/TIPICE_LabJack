# app_pid.py — Shell and Tube Heat Exchanger — Animated P&ID Interface
# =====================================================================
# Layout:
#   Col 0        Col 1-4 (canvas)         Col 5-6 (right panels)
#   ──────────   ────────────────────────  ──────────────────────
#   Controls     Animated P&ID diagram     Level loop
#   Logging      with live sensor values   Flowrate loop
#   Image                                  Steam Pressure loop

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
ANIM_MS            = 40          # animation tick ~25 fps

# ── Canvas dimensions ──────────────────────────────────────────────────────────
CW, CH = 680, 480

# ── Equipment coordinate constants ────────────────────────────────────────────
HX_X1, HX_Y1, HX_X2, HX_Y2 = 145, 110, 265, 408

HX_W_TOP   = (205, HX_Y1)
HX_W_BOT   = (205, HX_Y2)
HX_S_IN    = (HX_X1, 222)
HX_S_OUT   = (HX_X1, 322)

STEAM_VLV  = (82, 222)
TOP_Y      = 45
RIGHT_X    = 590
MAKEUP_TOP = (RIGHT_X, 10)

TANK_CX, TANK_TY, TANK_BY = RIGHT_X, 158, 252

LVL_VLV    = (RIGHT_X, 322)
BOT_Y      = 445
PUMP_POS   = (458, BOT_Y)
FM_POS     = (335, BOT_Y)
FV_POS     = (205, BOT_Y)

# ── Pipe paths for animation particles ────────────────────────────────────────
WATER_PATH = [
    HX_W_TOP, (HX_W_TOP[0], TOP_Y), (RIGHT_X, TOP_Y),
    (RIGHT_X, TANK_TY), (RIGHT_X, TANK_BY),
    (RIGHT_X, LVL_VLV[1] - 15), (RIGHT_X, BOT_Y),
    PUMP_POS, FM_POS, FV_POS, HX_W_BOT, HX_W_TOP,
]
STEAM_IN_PATH  = [(20, HX_S_IN[1]),  STEAM_VLV, HX_S_IN]
STEAM_OUT_PATH = [HX_S_OUT, (20, HX_S_OUT[1])]

# ── Colors ────────────────────────────────────────────────────────────────────
C_WATER  = "#1565C0"
C_STEAM  = "#C62828"
C_PIPE   = "#455A64"
C_EQUIP  = "#ECEFF1"
C_STROKE = "#263238"
C_BG     = "#F5F7FA"
C_LBL_BG = "#FFFFFFCC"
C_LBL_FG = "#1A237E"


# ══════════════════════════════════════════════════════════════════════════════
# Flow animation particle
# ══════════════════════════════════════════════════════════════════════════════

class _Particle:
    def __init__(self, canvas, path, color, r=5, speed=3.5, offset=0.0):
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
# Main application
# ══════════════════════════════════════════════════════════════════════════════

class ShellTubeHXPIDApp:
    BASE_WIDTH  = 1600
    BASE_HEIGHT = 900

    def __init__(self):
        self.root = tk.Tk()
        self.root.geometry("1400x920")
        self.root.title(config.SYSTEM_NAME + " — P&ID View")
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

        self._simple_panel_widgets = {}
        self._overlay_ids          = {}   # overlay text canvas item IDs
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
        self.root.columnconfigure(0, weight=0)
        for i in range(1, 5): self.root.columnconfigure(i, weight=1)
        for i in range(5, 7): self.root.columnconfigure(i, weight=0)
        self.root.rowconfigure(0, weight=1)
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
        self._build_right_panels()

    # ── Left column ────────────────────────────────────────────────────────────

    def _build_left_column(self):
        col = ttk.Frame(self._sf)
        col.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")

        # Controls
        ctrl = ttk.LabelFrame(col, text="Controls", padding=(15, 8))
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

        # Data logging
        log = ttk.LabelFrame(col, text="Data Logging", padding=(15, 8))
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

        # Logo + theme
        logo_f = tk.LabelFrame(col, borderwidth=0, relief="flat")
        logo_f.pack(fill="x", pady=(0, 8))
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            img = Image.open(os.path.join(base_dir, config.LOGO_FILE))
            img.thumbnail((160, 80))
            self._logo_img = ImageTk.PhotoImage(img)
            ttk.Label(logo_f, image=self._logo_img).pack()
        except Exception:
            ttk.Label(logo_f, text="BYU TIPICE",
                      font=("Helvetica", 14, "bold")).pack()
        self._logo_frame = logo_f

        # Apparatus image
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            img2 = Image.open(os.path.join(base_dir, "assets", "apparatus.png"))
            img2.thumbnail((200, 160))
            self._appar_img = ImageTk.PhotoImage(img2)
            ttk.Label(col, image=self._appar_img).pack(pady=(0, 8))
        except Exception:
            pass

        self._theme_btn = ttk.Checkbutton(
            col, text="Dark Mode", style="ToggleButton",
            command=self._on_theme_toggle)
        self._theme_btn.pack(fill="x")

    # ── P&ID canvas ────────────────────────────────────────────────────────────

    def _build_pid_canvas(self):
        outer = ttk.LabelFrame(self._sf, text="P&ID — Shell & Tube Heat Exchanger",
                               padding=(5, 5))
        outer.grid(row=0, column=1, columnspan=4, padx=5, pady=10, sticky="nsew")

        self._pid = tk.Canvas(outer, width=CW, height=CH, bg=C_BG,
                              highlightthickness=1, highlightbackground="#B0BEC5")
        self._pid.pack()

        self._draw_static()
        self._create_sensor_overlays()

    def _draw_static(self):
        c = self._pid

        # ── Water pipes (blue) ─────────────────────────────────────────────────
        pw = dict(fill=C_WATER, width=4)

        # HX top → up → right
        c.create_line(HX_W_TOP[0], HX_W_TOP[1],
                      HX_W_TOP[0], TOP_Y, RIGHT_X, TOP_Y, **pw)
        # Makeup inlet (top right)
        c.create_line(MAKEUP_TOP[0], MAKEUP_TOP[1],
                      MAKEUP_TOP[0], TOP_Y, **pw)
        # Right side down through tank
        c.create_line(RIGHT_X, TOP_Y, RIGHT_X, TANK_TY, **pw)
        c.create_line(RIGHT_X, TANK_BY, RIGHT_X, LVL_VLV[1]-18, **pw)
        c.create_line(RIGHT_X, LVL_VLV[1]+18, RIGHT_X, BOT_Y, **pw)
        # Bottom pipe
        c.create_line(RIGHT_X, BOT_Y, HX_W_BOT[0], BOT_Y, **pw)
        # Up into HX bottom
        c.create_line(FV_POS[0], BOT_Y, HX_W_BOT[0], HX_W_BOT[1], **pw)

        # ── Steam pipes (red) ──────────────────────────────────────────────────
        ps = dict(fill=C_STEAM, width=4)
        # Inlet
        c.create_line(20, HX_S_IN[1], STEAM_VLV[0]-15, HX_S_IN[1], **ps)
        c.create_line(STEAM_VLV[0]+15, HX_S_IN[1], HX_S_IN[0], HX_S_IN[1], **ps)
        # Arrow on steam inlet
        ax, ay = HX_S_IN[0]-8, HX_S_IN[1]
        c.create_polygon(ax, ay-5, ax+10, ay, ax, ay+5,
                         fill=C_STEAM, outline='')
        # Outlet
        c.create_line(HX_S_OUT[0], HX_S_OUT[1], 20, HX_S_OUT[1], **ps)
        # Arrow on steam outlet
        bx, by = 28, HX_S_OUT[1]
        c.create_polygon(bx, by-5, bx-10, by, bx, by+5,
                         fill=C_STEAM, outline='')

        # ── Equipment symbols ──────────────────────────────────────────────────
        self._draw_hx(c)
        self._draw_valve(c, *STEAM_VLV, color=C_STEAM)  # steam control valve
        self._draw_valve(c, *LVL_VLV)                    # level control valve
        self._draw_valve(c, *FV_POS)                     # flow control valve
        self._draw_tank(c)
        self._draw_pump(c, *PUMP_POS)
        self._draw_flowmeter(c, *FM_POS)

        # ── Flow direction arrows on water pipes ───────────────────────────────
        # Top pipe: left → right
        c.create_polygon(RIGHT_X-80, TOP_Y-4, RIGHT_X-60, TOP_Y,
                         RIGHT_X-80, TOP_Y+4, fill=C_WATER, outline='')
        # Right side: top → down
        c.create_polygon(RIGHT_X-4, TANK_TY+50, RIGHT_X, TANK_TY+66,
                         RIGHT_X+4, TANK_TY+50, fill=C_WATER, outline='')
        # Bottom pipe: right → left
        c.create_polygon(FM_POS[0]+30, BOT_Y-4, FM_POS[0]+10, BOT_Y,
                         FM_POS[0]+30, BOT_Y+4, fill=C_WATER, outline='')

    def _draw_hx(self, c):
        x1, y1, x2, y2 = HX_X1, HX_Y1, HX_X2, HX_Y2
        # Main shell
        c.create_rectangle(x1, y1, x2, y2,
                           fill=C_EQUIP, outline=C_STROKE, width=2)
        # Top and bottom header caps
        c.create_rectangle(x1+12, y1, x2-12, y1+28,
                           fill="#CFD8DC", outline=C_STROKE, width=2)
        c.create_rectangle(x1+12, y2-28, x2-12, y2,
                           fill="#CFD8DC", outline=C_STROKE, width=2)
        # Tube lines
        for y in range(y1+38, y2-28, 18):
            c.create_line(x1+4, y, x2-4, y,
                          fill="#90A4AE", width=1, dash=(4, 3))
        # Label
        c.create_text((x1+x2)//2, (y1+y2)//2, text="Shell &\nTube HX",
                      font=("Helvetica", 8, "italic"), fill="#546E7A",
                      justify="center")

    def _draw_valve(self, c, cx, cy, size=16, color=C_STROKE):
        # Bow-tie valve symbol
        c.create_polygon(cx-size, cy-size, cx+size, cy-size, cx, cy,
                         fill=C_EQUIP, outline=color, width=2)
        c.create_polygon(cx-size, cy+size, cx+size, cy+size, cx, cy,
                         fill=C_EQUIP, outline=color, width=2)
        # Actuator square on top
        c.create_rectangle(cx-9, cy-size-14, cx+9, cy-size,
                           fill="#B0BEC5", outline=color, width=1)

    def _draw_pump(self, c, cx, cy, r=22):
        c.create_oval(cx-r, cy-r, cx+r, cy+r,
                      fill=C_EQUIP, outline=C_STROKE, width=2)
        c.create_text(cx, cy, text="C", font=("Helvetica", 13, "bold"),
                      fill=C_STROKE)

    def _draw_flowmeter(self, c, cx, cy, s=20):
        c.create_rectangle(cx-s, cy-s, cx+s, cy+s,
                           fill=C_EQUIP, outline=C_STROKE, width=2)
        c.create_text(cx, cy, text="M", font=("Helvetica", 13, "bold"),
                      fill=C_STROKE)

    def _draw_tank(self, c):
        hw = 38    # half-width at top
        nw = 8     # half-width at bottom (nozzle)
        tx, ty, by = TANK_CX, TANK_TY, TANK_BY
        # Funnel / vessel shape
        c.create_polygon(tx-hw, ty, tx+hw, ty,
                         tx+nw, by, tx-nw, by,
                         fill=C_EQUIP, outline=C_STROKE, width=2)
        # Fill level indicator (static visual)
        fill_y = ty + int((by - ty) * 0.55)
        frac = 0.55
        fw = hw - frac * (hw - nw)
        c.create_polygon(tx-fw, fill_y, tx+fw, fill_y,
                         tx+nw, by, tx-nw, by,
                         fill="#BBDEFB", outline='')
        # Redraw outline on top
        c.create_polygon(tx-hw, ty, tx+hw, ty,
                         tx+nw, by, tx-nw, by,
                         fill='', outline=C_STROKE, width=2)

    # ── Sensor value overlays ──────────────────────────────────────────────────

    def _create_sensor_overlays(self):
        """
        Create canvas text items for each sensor reading.
        Positions match the P&ID label locations in the schematic.
        """
        c = self._pid

        # Each entry: (tag_key, x, y, anchor, initial_label)
        overlays = [
            ("outlet_temp",     HX_X1 - 10,      HX_Y1 + 5,   "e",  "Outlet Temp"),
            ("inlet_temp",      HX_X1 - 10,      HX_Y2 - 5,   "e",  "Inlet Temp"),
            ("steam_pressure",  STEAM_VLV[0],    HX_S_IN[1]-30, "s", "Steam Pressure"),
            ("makeup_temp",     RIGHT_X + 12,    MAKEUP_TOP[1], "w", "Makeup Temp"),
            ("makeup_flow",     RIGHT_X + 12,    MAKEUP_TOP[1]+20, "w", "Makeup Flow"),
            ("level",           RIGHT_X + 12,    (TANK_TY+TANK_BY)//2, "w", "Level"),
            ("level_valve_pct", RIGHT_X + 12,    LVL_VLV[1],  "w",  "Valve %"),
            ("pump_status",     PUMP_POS[0],     BOT_Y - 28,  "s",  "Pump"),
            ("flowrate",        FM_POS[0],       BOT_Y - 28,  "s",  "Flowrate"),
            ("flow_valve_pct",  FV_POS[0] - 12, BOT_Y - 28,  "e",  "Valve %"),
        ]

        for tag, x, y, anchor, label in overlays:
            # Background pill
            bg = c.create_rectangle(0, 0, 1, 1,
                                    fill="white", outline="#90A4AE",
                                    width=1, tags=(tag + "_bg",))
            # Text
            txt = c.create_text(x, y, text=f"{label}\n---",
                                 anchor=anchor,
                                 font=("Helvetica", 7, "bold"),
                                 fill=C_LBL_FG,
                                 justify="center",
                                 tags=(tag,))
            # Size the background to the text
            self.root.update_idletasks()
            bb = c.bbox(txt)
            if bb:
                pad = 3
                c.coords(bg, bb[0]-pad, bb[1]-pad, bb[2]+pad, bb[3]+pad)
            # Keep bg behind text
            c.tag_lower(bg, txt)
            self._overlay_ids[tag] = (txt, bg)

    def _update_sensor_overlays(self):
        """Push latest sensor/loop values into the canvas text items."""
        c   = self._pid
        s   = self.sensors
        lps = self.loops

        def val(src, key, unit=""):
            try:
                v = src[key].value_var.get() if hasattr(src[key], "value_var") \
                    else src[key].measured_var.get()
                return f"{float(v):.2f} {unit}".strip()
            except Exception:
                return "---"

        updates = {
            "outlet_temp":     ("Outlet Temp\n" + val(s, "water_outlet_temp", "°C")),
            "inlet_temp":      ("Inlet Temp\n"  + val(s, "water_inlet_temp",  "°C")),
            "steam_pressure":  ("Steam P\n"     + val(lps, "steam_pressure",  "psig")),
            "makeup_temp":     ("Makeup T: "    + val(s, "makeup_temperature", "°C")),
            "makeup_flow":     ("Makeup F: "    + val(s, "makeup_flowrate",    "GPM")),
            "level":           ("Level\n"       + val(lps, "level",            "ft")),
            "level_valve_pct": (f"Valve %\n{lps['level'].rounded_valve_position.get()}%"),
            "pump_status":     (f"Pump\n{'ON' if self._pump_on else 'OFF'}"),
            "flowrate":        ("Flow\n"        + val(lps, "flowrate",         "GPM")),
            "flow_valve_pct":  (f"Valve %\n{lps['flowrate'].rounded_valve_position.get()}%"),
        }

        for tag, text in updates.items():
            if tag not in self._overlay_ids:
                continue
            txt_id, bg_id = self._overlay_ids[tag]
            c.itemconfig(txt_id, text=text)
            bb = c.bbox(txt_id)
            if bb:
                pad = 3
                c.coords(bg_id, bb[0]-pad, bb[1]-pad, bb[2]+pad, bb[3]+pad)

    # ── Right control panels ───────────────────────────────────────────────────

    def _build_right_panels(self):
        right = ttk.Frame(self._sf)
        right.grid(row=0, column=5, columnspan=2,
                   padx=(5, 10), pady=10, sticky="nsew")

        order = ["level", "flowrate", "steam_pressure"]
        for i, key in enumerate(order):
            if key in self.loops:
                w = self._build_simple_loop_panel(right, key, self.loops[key], row=i)
                self._simple_panel_widgets[key] = w

    def _build_simple_loop_panel(self, parent, key, loop, row):
        """
        Compact control panel: setpoint, manual/auto switch,
        manual slider, and PID constants. No measured value
        display (shown on the P&ID diagram instead).
        """
        f = ttk.LabelFrame(parent, text=loop.label, padding=(12, 8))
        f.grid(row=row, column=0, padx=4, pady=5, sticky="nsew")
        f.columnconfigure(1, weight=1)

        widgets = {}

        # Setpoint
        ttk.Label(f, text=f"Setpoint ({loop.unit})",
                  wraplength=110).grid(row=0, column=0, sticky="w", padx=4)
        sp = ttk.Spinbox(f, from_=loop.setpoint_min, to=loop.setpoint_max,
                         textvariable=loop.setpoint_var, width=8,
                         state="disabled")
        sp.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        widgets["sp"] = sp

        # Mode switch
        def _toggle(lp=loop, k=key):
            lp.is_auto = not lp.is_auto
            if lp.is_auto:
                btn_map[k].config(text="AUTO")
                try:
                    lp.pid.initialize(lp.get_manual_voltage())
                except Exception:
                    lp.pid.reset()
            else:
                btn_map[k].config(text="MANUAL")
                lp.pid.reset()

        mode_var = tk.BooleanVar(value=False)
        mode_btn = ttk.Checkbutton(f, text="MANUAL", style="Switch",
                                   variable=mode_var, command=_toggle,
                                   state="disabled")
        mode_btn.grid(row=1, column=0, columnspan=2,
                      sticky="ew", padx=4, pady=4)
        widgets["mode"] = mode_btn
        if not hasattr(self, "_btn_refs"):
            self._btn_refs = {}
        self._btn_refs[key] = mode_btn
        if not hasattr(self, "_btn_map_ref"):
            self._btn_map_ref = {}
        self._btn_map_ref[key] = mode_btn

        # Manual slider
        ttk.Label(f, text="Manual Output (%)").grid(
            row=2, column=0, sticky="w", padx=4)
        slider_frame = ttk.Frame(f)
        slider_frame.grid(row=2, column=1, sticky="ew", padx=4)
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
        pid_f.grid(row=3, column=0, columnspan=2, sticky="ew",
                   padx=4, pady=(6, 2))

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
        N_WATER = 9
        N_STEAM = 4
        for i in range(N_WATER):
            self._particles.append(
                _Particle(self._pid, WATER_PATH, C_WATER,
                          r=5, speed=4.0, offset=i/N_WATER))
        for i in range(N_STEAM):
            self._particles.append(
                _Particle(self._pid, STEAM_IN_PATH, C_STEAM,
                          r=5, speed=3.0, offset=i/N_STEAM))
            self._particles.append(
                _Particle(self._pid, STEAM_OUT_PATH, C_STEAM,
                          r=5, speed=3.0, offset=i/N_STEAM))

        # Raise all static drawing items above particles so labels
        # and equipment are always visible
        self._pid.tag_raise("particle")

    def _animate(self):
        water_on = self._pump_on and self._main_power_on
        steam_on = self._main_power_on

        for i, p in enumerate(self._particles):
            is_water = i < 9
            active   = water_on if is_water else steam_on
            if active:
                p.show()
                p.step()
            else:
                p.hide()

        self._update_sensor_overlays()

        # Bring overlays above particles so they're always readable
        for tag, (txt_id, bg_id) in self._overlay_ids.items():
            self._pid.tag_raise(bg_id)
            self._pid.tag_raise(txt_id)

        self.root.after(ANIM_MS, self._animate)

    # ══════════════════════════════════════════════════════════════════
    # Enable / disable
    # ══════════════════════════════════════════════════════════════════

    def _set_initial_states(self):
        self._power_sw.configure(state="disabled")
        self._pump_sw.configure(state="disabled")
        self._log_btn.configure(state="disabled")
        for key, widgets in self._simple_panel_widgets.items():
            for w in widgets.values():
                try: w.configure(state="disabled")
                except Exception: pass

    def _enable_powered_controls(self):
        self._pump_sw.configure(state="normal")
        self._log_btn.configure(state="normal")
        for key, widgets in self._simple_panel_widgets.items():
            for role, w in widgets.items():
                state = "readonly" if role == "measured" else "normal"
                try: w.configure(state=state)
                except Exception: pass

    def _disable_powered_controls(self):
        self._pump_sw.configure(state="disabled")
        self._log_btn.configure(state="disabled")
        for key, widgets in self._simple_panel_widgets.items():
            for w in widgets.values():
                try: w.configure(state="disabled")
                except Exception: pass
        if hasattr(self, "logger") and self.logger.is_logging:
            self.logger.stop()
            self._logging_text_var.set("Start Logging")
            self._data_point_count.set(0)
        if self._pump_on:
            self._pump_on = False
            self._pump_var.set(False)
            self._pump_sw.config(text="Pump: OFF")
            self.daq.write(config.PUMP_SWITCH_PIN, 0)

    # ══════════════════════════════════════════════════════════════════
    # Event callbacks
    # ══════════════════════════════════════════════════════════════════

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
        else:
            self._pump_sw.config(text="Pump: OFF")
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
            text="Light Mode" if self._theme_mode.get() else "Dark Mode")
        self.style.theme_use(f"forest-{mode}")
        bg = self.style.lookup(".", "background")
        self.root.configure(background=bg)
        self._logo_frame.configure(background=bg)
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
        # Cold junction for thermocouples
        try:
            cj_k = self.daq.read(config.COLD_JUNCTION_REGISTER)
            config._cj_temp_c[0] = cj_k - 273.15
        except Exception:
            pass

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
