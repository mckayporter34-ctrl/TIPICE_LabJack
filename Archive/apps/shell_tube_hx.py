# apps/shell_tube_hx.py
# Redesigned GUI Frame for Shell & Tube Heat Exchanger.

import os
import math
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

from core.base_app import BaseAppFrame

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
    (424, 550),  # HX bottom
    (367, 550),  # bottom out
    (50, 550),   # disappear
]

SCALE_PATH_X = CW / 1504
SCALE_PATH_Y = CH / 924
WATER_PATH = [(int(x * SCALE_PATH_X), int(y * SCALE_PATH_Y)) for x, y in WATER_PATH_1504]
STEAM_PATH = [(int(x * SCALE_PATH_X), int(y * SCALE_PATH_Y)) for x, y in STEAM_PATH_1504]


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


class ShellTubeHXRedesignFrame(BaseAppFrame):
    """
    Redesigned GUI Frame for Shell & Tube Heat Exchanger, displaying:
    - Left column: Connection, Main Power, Pump control, Flow animation test, Data Logging, Apparatus Image, Theme toggle.
    - Right column: P&ID Canvas with overlays for sensor readouts.
    - Bottom row: Level, Flowrate, and Steam Pressure control panels.
    """

    ANIM_MS = 100          # animation tick ~25 fps

    def __init__(self, parent, config, daq, on_back=None):
        self.style = ttk.Style()
        self._loop_widgets = {}
        # 1. Initialize custom variables before constructor builds UI
        self._theme_mode      = tk.IntVar(value=0)
        self._pump_on         = False
        self._pump_var        = tk.BooleanVar(value=False)
        self._pump_status_str = tk.StringVar(value="OFF")
        self._anim_test_var    = tk.BooleanVar(value=True)

        self._simple_panel_widgets = {}
        self._btn_map_ref          = {}
        self._overlay_cards        = []
        self._particles            = []

        super().__init__(parent, config, daq, on_back)

        # Sync pump variable in switch variables
        self._switch_vars["pump"] = self._pump_var

        self._create_particles()
        self._update_pump_indicator()

        # Start animation loop
        self._animate()

    def _build_ui(self):
        self._sensor_widgets = {}

        # Header Bar
        self._build_header_bar()

        # Main Body container (scrollable frame)
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        # Canvas with scrollbars
        self._canvas_outer = tk.Canvas(body)
        self._canvas_outer.pack(side="left", fill="both", expand=True)
        
        v_sb = ttk.Scrollbar(body, orient="vertical", command=self._canvas_outer.yview)
        v_sb.pack(side="right", fill="y")
        h_sb = ttk.Scrollbar(self, orient="horizontal", command=self._canvas_outer.xview)
        h_sb.pack(side="bottom", fill="x")

        self._canvas_outer.configure(yscrollcommand=v_sb.set, xscrollcommand=h_sb.set)
        bg = self.style.lookup("TFrame", "background")
        self._canvas_outer.configure(bg=bg)

        self._sf = ttk.Frame(self._canvas_outer)
        self._canvas_outer.create_window((0, 0), window=self._sf, anchor="nw")
        
        self._sf.bind("<Configure>", lambda e: self._canvas_outer.configure(
            scrollregion=self._canvas_outer.bbox("all")))
        
        self._sf.bind("<Enter>", lambda e: self.bind_all("<MouseWheel>", self._on_mousewheel))
        self._sf.bind("<Leave>", lambda e: self.unbind_all("<MouseWheel>"))

        self._build_left_column()
        self._build_pid_canvas()
        self._build_horizontal_panels()

    def _build_left_column(self):
        col = ttk.Frame(self._sf)
        col.grid(row=0, column=0, rowspan=2, padx=(10, 5), pady=10, sticky="nsew")

        # Controls panel
        ctrl = ttk.LabelFrame(col, text="Controls", padding=(30, 15))
        ctrl.pack(fill="x", pady=(0, 8))

        self._connect_dd = ttk.OptionMenu(
            ctrl, self._connection_var, "Connect to LabJack",
            "USB", "Ethernet", "Disconnect",
            command=self._on_connection_choice)
        self._connect_dd.pack(fill="x", pady=(4, 4))

        self._connection_status = ttk.Label(ctrl, text="Not connected", padding=(4, 2))
        self._connection_status.pack(fill="x")

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
        self._toggle_logging_btn = self._log_btn

        r = ttk.Frame(log)
        r.pack(fill="x", pady=2)
        ttk.Label(r, text="Interval (s)").pack(side="left")
        ttk.Spinbox(r, from_=0.1, to=100.0, textvariable=self._log_interval_var, width=5).pack(side="right")

        r2 = ttk.Frame(log)
        r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="Count").pack(side="left")
        ttk.Entry(r2, textvariable=self._data_point_count, state="disabled", width=6).pack(side="right")

        # Apparatus image panel
        img_f = ttk.LabelFrame(col, text="Apparatus Image", padding=10)
        img_f.pack(fill="x", pady=(0, 8))
        try:
            img_file = getattr(self.config, "APPARATUS_IMAGE", None)
            if img_file:
                if not os.path.isabs(img_file):
                    workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    img_path = os.path.join(workspace_dir, img_file)
                else:
                    img_path = img_file

                if os.path.exists(img_path):
                    img2 = Image.open(img_path)
                    img2.thumbnail((200, 160))
                    self._appar_img = ImageTk.PhotoImage(img2)
                    ttk.Label(img_f, image=self._appar_img, anchor="center").pack()
                else:
                    print(f"Apparatus image not found at: {img_path}")
                    ttk.Label(img_f, text="No Image Found", anchor="center").pack()
            else:
                ttk.Label(img_f, text="No Image Configured", anchor="center").pack()
        except Exception as e:
            print(f"Error loading photo: {e}")
            ttk.Label(img_f, text="No Image Found", anchor="center").pack()

        # Theme toggle
        self._theme_btn = ttk.Checkbutton(
            col, text="Dark Mode", style="ToggleButton",
            command=self._on_theme_toggle)
        self._theme_btn.pack(fill="x")

    def _build_pid_canvas(self):
        outer = ttk.LabelFrame(self._sf, text="Piping and Instrumentation Diagram",
                               padding=(10, 10))
        outer.grid(row=0, column=1, columnspan=3, padx=5, pady=10, sticky="nsew")

        self._pid = tk.Canvas(outer, width=CW, height=CH, bg="white", highlightthickness=0)
        self._pid.pack(expand=True)

        try:
            workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            bg_path = os.path.join(workspace_dir, "PI diagrams", "PI_diagram.png")
            self._bg_img_raw = Image.open(bg_path)
            self._bg_img_resized = self._bg_img_raw.resize((CW, CH), Image.Resampling.LANCZOS)
            self._bg_img = ImageTk.PhotoImage(self._bg_img_resized)
            self._pid.create_image(0, 0, anchor="nw", image=self._bg_img)
        except Exception as e:
            print(f"Error loading P&ID background image: {e}")
            self._pid.create_text(CW//2, CH//2, text="P&ID Diagram Image Not Found", font=("Helvetica", 16))

        # Pump lighted indicator
        self._pump_indicator = self._pid.create_oval(
            970+7, 485+7, 970+7, 485+7,
            fill="#F44336", outline="#263238", width=1
        )

        self._create_sensor_overlays()

    def _create_sensor_overlays(self):
        s = self.sensors
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
            card = tk.Frame(self._pid, bg="white", padx=0, pady=0, bd=0)
            lbl = tk.Label(card, text=label, font=("Helvetica", 12, "bold"),
                           bg="white", fg="#263238", anchor="center")
            lbl.pack(fill="x", padx=0, pady=0)
            
            entry = ttk.Entry(card, textvariable=var, state="disabled", width=8,
                              justify="center", font=("Helvetica", 12, "bold"))
            entry.pack(fill="x", padx=0, pady=(2, 4))
            
            self._pid.create_window(x, y, window=card, anchor="center")
            self._overlay_cards.append(card)

    def _build_horizontal_panels(self):
        order = ["level", "flowrate", "steam_pressure"]
        for idx, key in enumerate(order):
            if key in self.loops:
                w = self._build_simple_loop_panel(self._sf, key, self.loops[key], row=1, col=idx+1)
                self._simple_panel_widgets[key] = w

    def _build_simple_loop_panel(self, parent, key, loop, row, col) -> dict:
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

        # Mode switch, Slider, and Spinbox manual entry all on the same row.
        row2_frame = ttk.Frame(f)
        row2_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=4, pady=6)

        mode_var = tk.BooleanVar(value=loop.is_auto)
        
        def _toggle(lp=loop, k=key, var=mode_var):
            lp.is_auto = var.get()
            self._set_loop_panel_states(self._main_power_on)

        mode_btn = ttk.Checkbutton(row2_frame, text="MANUAL", style="Switch",
                                   variable=mode_var, command=_toggle,
                                   state="disabled")
        mode_btn.pack(side="left", padx=(0, 6))
        widgets["mode"] = mode_btn
        self._btn_map_ref[key] = mode_btn

        slider = ttk.Scale(row2_frame, from_=0, to=100,
                           variable=loop.valve_position, state="disabled")
        slider.pack(side="left", fill="x", expand=True, padx=6)
        widgets["slider"] = slider

        spinbox = ttk.Spinbox(row2_frame, from_=0, to=100, width=5,
                              textvariable=loop.rounded_valve_position, state="disabled")
        spinbox.pack(side="right", padx=(6, 0))
        widgets["spinbox"] = spinbox

        def _sync_slider(*_a, lp=loop):
            try:
                val = round(lp.valve_position.get())
                if lp.rounded_valve_position.get() != val:
                    lp.rounded_valve_position.set(val)
            except Exception:
                pass
        loop.valve_position.trace_add("write", _sync_slider)

        def _commit_spinbox(event=None, lp=loop, sb=spinbox):
            try:
                val = int(sb.get())
                val = max(0, min(100, val))
                lp.valve_position.set(float(val))
                lp.rounded_valve_position.set(val)
            except ValueError:
                sb.set(round(lp.valve_position.get()))
        
        spinbox.bind("<Return>", _commit_spinbox)
        spinbox.bind("<FocusOut>", _commit_spinbox)

        # PID constants in a row (centered)
        pid_f = ttk.Frame(f)
        pid_f.grid(row=3, column=0, columnspan=2, sticky="",
                   padx=4, pady=(6, 4))

        for i, (name, var, lo, hi) in enumerate([
            ("Kc",      loop.Kc_var, -1000, 1000),
            ("Ti (min)", loop.Ti_var, 0,    1000),
            ("Td",      loop.Td_var, 0,     100),
        ]):
            pair_f = ttk.Frame(pid_f)
            pair_f.pack(side="left", padx=6)
            ttk.Label(pair_f, text=name, font=("Helvetica", 8)).pack(side="left", padx=(0, 4))
            sb = ttk.Spinbox(pair_f, textvariable=var, from_=lo, to=hi,
                             width=6, state="disabled", justify="center")
            sb.pack(side="left")
            widgets[f"pid_{name.split()[0]}"] = sb

        return widgets

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
        if not self._polling:
            return
        anim_enabled = self._anim_test_var.get()
        
        flow_detected = False
        if "flowrate" in self.loops:
            try:
                flow_val = self.loops["flowrate"].get_measured()
                if flow_val is not None and float(flow_val) > 0.05:
                    flow_detected = True
            except Exception:
                pass

        water_on = anim_enabled and flow_detected
        steam_on = anim_enabled and flow_detected

        # First 12 are water, next 6 are steam
        for i, p in enumerate(self._particles):
            is_water = i < 12
            active   = water_on if is_water else steam_on
            if active:
                p.show()
                p.step()
            else:
                p.hide()

        self._pid.tag_raise("particle")
        self.after(self.ANIM_MS, self._animate)

    def _set_initial_states(self):
        self._power_sw.configure(state="disabled")
        self._pump_sw.configure(state="disabled")
        self._log_btn.configure(state="disabled")
        self._set_loop_panel_states(False)
        self._update_pump_indicator()

    def _set_loop_panel_states(self, enabled):
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
                    if "spinbox" in widgets:
                        widgets["spinbox"].configure(state="disabled")
                    try:
                        loop.pid.initialize(loop.get_manual_voltage())
                    except Exception:
                        loop.pid.reset()
                else:
                    widgets["mode"].configure(text="MANUAL")
                    widgets["sp"].configure(state="disabled")
                    widgets["slider"].configure(state="normal")
                    if "spinbox" in widgets:
                        widgets["spinbox"].configure(state="normal")
                    loop.pid.reset()
            else:
                for w in widgets.values():
                    try: w.configure(state="disabled")
                    except Exception: pass
                widgets["mode"].configure(text="MANUAL")

    def _update_pump_indicator(self):
        color = "#4CAF50" if self._pump_on and self._main_power_on else "#F44336"
        self._pid.itemconfig(self._pump_indicator, fill=color)

    def _enable_powered_controls(self):
        super()._enable_powered_controls()
        self._pump_sw.configure(state="normal")
        self._log_btn.configure(state="normal")
        self._set_loop_panel_states(True)
        self._update_pump_indicator()

    def _disable_powered_controls(self):
        super()._disable_powered_controls()
        self._pump_sw.configure(state="disabled")
        self._log_btn.configure(state="disabled")
        self._set_loop_panel_states(False)
        
        if self._pump_on:
            self._pump_on = False
            self._pump_var.set(False)
            self._pump_sw.config(text="Pump: OFF")
            self.daq.write(self.config.SYSTEM_SWITCHES[0]["pin"], 0)
            self._pump_status_str.set("OFF")

        self._update_pump_indicator()

    def _on_anim_test_toggle(self):
        state = self._anim_test_var.get()
        self._anim_test_sw.config(text=f"Flow Animation: {'ON' if state else 'OFF'}")

    def _on_connection_choice(self, choice):
        if choice == "USB":       self._connect("T7", "USB",      "ANY")
        elif choice == "Ethernet": self._connect("T7", "ETHERNET", self.config.ETHERNET_ADDRESS)
        elif choice == "Disconnect": self._disconnect()

    def _configure_ain_channels(self):
        ain_configs = getattr(self.config, "AIN_CONFIGS", {})
        for ch, settings in ain_configs.items():
            for reg, val in settings.items():
                self.daq.write(f"{ch}_{reg}", val)

    def _connect(self, model, connection, identifier):
        try:
            self.daq.connect(model, connection, identifier)
            self._configure_ain_channels()
            self._connection_status.config(text="Connected", style="Green.TLabel")
            self._status_lbl.config(text="CONNECTED", foreground="green")
            self._power_sw.configure(state="normal")
        except Exception as exc:
            self._connection_status.config(text=f"Failed: {exc}", style="Red.TLabel")
            self._status_lbl.config(text="DISCONNECTED", foreground="red")

    def _disconnect(self):
        self.daq.disconnect()
        self._connection_status.config(text="Disconnected", style="Green.TLabel")
        self._status_lbl.config(text="DISCONNECTED", foreground="red")
        self._power_sw.configure(state="disabled")
        self._main_power_on = False
        self._main_power_var.set(False)
        self._power_sw.config(text="Main Power: OFF")
        self._disable_powered_controls()

    def _on_power_toggle(self):
        self._main_power_on = not self._main_power_on
        if self._main_power_on:
            self._power_sw.config(text="Main Power: ON")
            self.daq.write(self.config.MAIN_POWER_PIN, 1)
            self._enable_powered_controls()
        else:
            self._power_sw.config(text="Main Power: OFF")
            self.daq.write(self.config.MAIN_POWER_PIN, 0)
            self._disable_powered_controls()

    def _on_pump_toggle(self):
        self._pump_on = not self._pump_on
        if self._pump_on:
            self._pump_sw.config(text="Pump: ON")
            self.daq.write(self.config.SYSTEM_SWITCHES[0]["pin"], 1)
            self._pump_status_str.set("ON")
        else:
            self._pump_sw.config(text="Pump: OFF")
            self.daq.write(self.config.SYSTEM_SWITCHES[0]["pin"], 0)
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
        
        try:
            self.style.theme_use(f"forest-{mode}")
        except Exception:
            pass
            
        bg = self.style.lookup(".", "background")
        self.config(background=bg)
        self._canvas_outer.configure(bg=bg)
        self.update_idletasks()

    def _on_mousewheel(self, event):
        scroll = -event.delta * 3 if event.delta in (1, -1) \
                 else int(-1 * (event.delta / 120)) * 3
        self._canvas_outer.yview_scroll(scroll, "units")
