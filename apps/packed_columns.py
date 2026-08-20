# apps/packed_columns.py
# Redesigned GUI Frame for Packed Columns.

import os
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk

from core.base_app import BaseAppFrame
from core.safety import SafetyState

CW, CH = 1300, 762

class PackedColumnsRedesignFrame(BaseAppFrame):
    """
    Redesigned GUI Frame for Packed Columns, displaying:
    - Left column: Connection, Column Selector, Data Logging, Apparatus Image, Theme toggle.
    - Right column: P&ID Canvas with overlays for sensor readouts.
    - Bottom row: Water, Level, and Air control panels.
    """

    def __init__(self, parent, config, daq, on_back=None):
        self.style = ttk.Style()
        self._loop_widgets = {}
        # 1. Initialize custom variables before constructor builds UI
        self._theme_mode = tk.IntVar(value=0)  # 0 = light, 1 = dark
        self._col_select_var = tk.BooleanVar(value=True)   # True = Column 1, False = Column 2
        
        # Dedicate a variable to display water exit valve percentage dynamically
        self._water_exit_valve_percent_var = tk.StringVar(value="0")

        # Air Flow control state variables
        self._air_setpoint_var = tk.StringVar(value="0")
        self._air_setpoint_double_var = tk.DoubleVar(value=0.0)
        self._air_valve_percent_var = tk.StringVar(value="0")

        # Active column overlays for canvas
        self._active_pressure_drop_var = tk.StringVar(value="---")
        self._active_level_var = tk.StringVar(value="---")

        # Bottom Panel state variables
        self._level_mode_auto_var = tk.BooleanVar(value=False)
        self._water_mode_auto_var = tk.BooleanVar(value=False)
        self._simple_panel_widgets = {}

        # Canvas overlays list
        self._overlay_cards = []

        super().__init__(parent, config, daq, on_back)

        # Sync air valve percent variable on setpoint write
        self._air_setpoint_var.trace_add("write", lambda *a: self._sync_air_valve_percent())
        
        # Sync air setpoint output to MANUAL_ANALOG_OUTPUTS
        self._manual_analog_vars["air_flowrate_setpoint"] = self._air_setpoint_var
        
        # Sync column selector switch variable
        self._switch_vars["column_selector"] = self._col_select_var

        # Initialize column selector state and bindings
        self._on_column_select()

    def _build_ui(self):
        # Configure layout weights
        self._sensor_widgets = {}

        # Header Bar
        self._build_header_bar()

        # Main Body container (scrollable frame)
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        # Canvas with scrollbars
        self._canvas_outer = tk.Canvas(body)
        self._canvas_outer.grid(row=0, column=0, sticky="nsew")

        v_scrollbar = ttk.Scrollbar(body, orient="vertical", command=self._canvas_outer.yview)
        v_scrollbar.grid(row=0, column=1, sticky="ns")

        h_scrollbar = ttk.Scrollbar(body, orient="horizontal", command=self._canvas_outer.xview)
        h_scrollbar.grid(row=1, column=0, sticky="ew")

        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self._canvas_outer.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        bg = self.style.lookup("TFrame", "background")
        self._canvas_outer.configure(bg=bg)

        self._sf = ttk.Frame(self._canvas_outer)
        self._sf_window = self._canvas_outer.create_window((0, 0), window=self._sf, anchor="nw")
        
        def _center_frame(event=None):
            cw = self._canvas_outer.winfo_width()
            ch = self._canvas_outer.winfo_height()
            fw = self._sf.winfo_reqwidth()
            fh = self._sf.winfo_reqheight()
            x = (cw - fw) // 2 if cw > fw else 0
            y = (ch - fh) // 2 if ch > fh else 0
            self._canvas_outer.coords(self._sf_window, x, y)
            self._canvas_outer.configure(scrollregion=self._canvas_outer.bbox("all"))

        self._sf.bind("<Configure>", _center_frame)
        self._canvas_outer.bind("<Configure>", _center_frame)
        
        self._sf.bind("<Enter>", lambda e: self.bind_all("<MouseWheel>", self._on_mousewheel))
        self._sf.bind("<Leave>", lambda e: self.unbind_all("<MouseWheel>"))

        # Build columns
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
            command=self._on_connection_choice
        )
        self._connect_dd.pack(fill="x", pady=(4, 4))

        self._connection_status = ttk.Label(ctrl, text="Not connected", padding=(4, 2))
        self._connection_status.pack(fill="x")

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
        self._toggle_logging_btn = self._log_btn

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
            command=self._on_theme_toggle
        )
        self._theme_btn.pack(fill="x")

    def _build_pid_canvas(self):
        outer = ttk.LabelFrame(self._sf, text="Piping and Instrumentation Diagram",
                               padding=(10, 10))
        outer.grid(row=0, column=1, columnspan=3, padx=5, pady=10, sticky="nsew")

        self._pid = tk.Canvas(outer, width=CW, height=CH, bg="white", highlightthickness=0)
        self._pid.pack(expand=True)

        try:
            workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            bg_path = os.path.join(workspace_dir, "PI diagrams", "packedcoloumn_pid.png")
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
        self._pid.create_window(346, 21, window=self._col1_lbl, anchor="center")

        self._col2_lbl = tk.Label(self._pid, textvariable=self._col2_indicator_val,
                                  font=("Helvetica", 11, "bold"), bg="#B0BEC5", fg="#37474F", padx=6, pady=4, relief="ridge")
        self._pid.create_window(821, 21, window=self._col2_lbl, anchor="center")

        overlays = [
            # Single active column readings in the center
            (576, 316, "Column 1 Pressure Drop\n(kPa)", self._active_pressure_drop_var, "dp"),
            (576, 426, "Column 1 Level\n(mm)", self._active_level_var, "level"),

            # Water Line readings (Right top)
            (1167, 48, "Water Flowrate\n(L/min)", lps["water_flow"].measured_var),
            (1167, 144, "Water Temp\n(°C)", s["water_temperature"].value_var),
            (937, 220, "Water Flow Valve\n(%)", lps["water_flow"].rounded_valve_position),

            # Water Exit Line reading (Left bottom)
            (156, 660, "Water Exit Valve\n(%)", self._water_exit_valve_percent_var),

            # Air Line readings (Right bottom)
            (684, 694, "Air Flowrate\n(SLPM)", s["air_flowrate"].value_var),
            (576, 117, "CO₂ Concentration\n(ppm)", s["co2_concentration"].value_var),
            (915, 715, "Air Valve\n(%)", self._air_valve_percent_var),
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

        # Mode switch, Slider, and Spinbox manual entry all on the same row
        row1_frame = ttk.Frame(f)
        row1_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=6)

        self._water_mode_auto_var.set(loop.is_auto)
        
        def _toggle():
            loop.is_auto = self._water_mode_auto_var.get()
            self._set_loop_panel_states(self._main_power_on)

        mode_btn = ttk.Checkbutton(row1_frame, text="MANUAL", style="Switch",
                                   variable=self._water_mode_auto_var, command=_toggle, state="disabled")
        mode_btn.pack(side="left", padx=(0, 6))
        widgets["mode"] = mode_btn

        slider = ttk.Scale(row1_frame, from_=0, to=100, variable=loop.valve_position, state="disabled")
        slider.pack(side="left", fill="x", expand=True, padx=6)
        widgets["slider"] = slider

        spinbox = ttk.Spinbox(row1_frame, from_=0, to=100, width=5,
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

        def _sync_spinbox(*_a, lp=loop):
            try:
                val = lp.rounded_valve_position.get()
                if abs(lp.valve_position.get() - val) > 0.01:
                    lp.valve_position.set(val)
            except Exception:
                pass
        loop.rounded_valve_position.trace_add("write", _sync_spinbox)

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
        pid_f.grid(row=2, column=0, columnspan=2, sticky="", padx=4, pady=(6, 4))

        for i, (name, var, lo, hi) in enumerate([
            ("Kc",       loop.Kc_var, -100.0, 100.0),
            ("Ti (min)", loop.Ti_var, 0.0,   100.0),
            ("Td",       loop.Td_var, 0.0,   10.0),
        ]):
            pair_f = ttk.Frame(pid_f)
            pair_f.pack(side="left", padx=6)
            ttk.Label(pair_f, text=name, font=("Helvetica", 8)).pack(side="left", padx=(0, 4))
            sb = ttk.Spinbox(pair_f, textvariable=var, from_=lo, to=hi, width=6, state="disabled", justify="center")
            sb.pack(side="left")
            widgets[f"pid_{name.split()[0]}"] = sb

        return widgets

    def _build_simple_level_panel_contents(self, frame) -> dict:
        loop = self.loops["column1_level"]
        widgets = {}

        # Setpoint
        ttk.Label(frame, text=f"Setpoint ({loop.unit})", wraplength=110).grid(row=0, column=0, sticky="w", padx=4, pady=4)
        sp = ttk.Spinbox(frame, from_=loop.setpoint_min, to=loop.setpoint_max,
                         textvariable=loop.setpoint_var, width=8, state="disabled")
        sp.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        widgets["sp"] = sp

        # Mode switch, Slider, and Spinbox manual entry all on the same row
        row1_frame = ttk.Frame(frame)
        row1_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=6)

        self._level_mode_auto_var.set(loop.is_auto)

        def _toggle():
            col1_active = self._col_select_var.get()
            active_key = "column1_level" if col1_active else "column2_level"
            self.loops[active_key].is_auto = self._level_mode_auto_var.get()
            self._set_loop_panel_states(self._main_power_on)

        mode_btn = ttk.Checkbutton(row1_frame, text="MANUAL", style="Switch",
                                   variable=self._level_mode_auto_var, command=_toggle, state="disabled")
        mode_btn.pack(side="left", padx=(0, 6))
        widgets["mode"] = mode_btn

        slider = ttk.Scale(row1_frame, from_=0, to=100, variable=loop.valve_position, state="disabled")
        slider.pack(side="left", fill="x", expand=True, padx=6)
        widgets["slider"] = slider

        spinbox = ttk.Spinbox(row1_frame, from_=0, to=100, width=5,
                              textvariable=loop.rounded_valve_position, state="disabled")
        spinbox.pack(side="right", padx=(6, 0))
        widgets["spinbox"] = spinbox

        def _sync_slider(*_a):
            try:
                col1_active = self._col_select_var.get()
                active_key = "column1_level" if col1_active else "column2_level"
                lp = self.loops[active_key]
                val = round(lp.valve_position.get())
                if lp.rounded_valve_position.get() != val:
                    lp.rounded_valve_position.set(val)
            except Exception:
                pass
        
        self.loops["column1_level"].valve_position.trace_add("write", _sync_slider)
        self.loops["column2_level"].valve_position.trace_add("write", _sync_slider)

        def _sync_spinbox_col1(*_a):
            try:
                lp = self.loops["column1_level"]
                val = lp.rounded_valve_position.get()
                if abs(lp.valve_position.get() - val) > 0.01:
                    lp.valve_position.set(val)
            except Exception:
                pass
        self.loops["column1_level"].rounded_valve_position.trace_add("write", _sync_spinbox_col1)

        def _sync_spinbox_col2(*_a):
            try:
                lp = self.loops["column2_level"]
                val = lp.rounded_valve_position.get()
                if abs(lp.valve_position.get() - val) > 0.01:
                    lp.valve_position.set(val)
            except Exception:
                pass
        self.loops["column2_level"].rounded_valve_position.trace_add("write", _sync_spinbox_col2)

        def _commit_spinbox(event=None):
            try:
                col1_active = self._col_select_var.get()
                active_key = "column1_level" if col1_active else "column2_level"
                lp = self.loops[active_key]
                val = int(spinbox.get())
                val = max(0, min(100, val))
                lp.valve_position.set(float(val))
                lp.rounded_valve_position.set(val)
            except ValueError:
                col1_active = self._col_select_var.get()
                active_key = "column1_level" if col1_active else "column2_level"
                lp = self.loops[active_key]
                spinbox.set(round(lp.valve_position.get()))
        
        spinbox.bind("<Return>", _commit_spinbox)
        spinbox.bind("<FocusOut>", _commit_spinbox)

        # PID constants row (centered)
        pid_f = ttk.Frame(frame)
        pid_f.grid(row=2, column=0, columnspan=2, sticky="", padx=4, pady=(6, 4))

        for i, name in enumerate(["Kc", "Ti", "Td"]):
            pair_f = ttk.Frame(pid_f)
            pair_f.pack(side="left", padx=6)
            label_text = name if name != "Ti" else "Ti (min)"
            ttk.Label(pair_f, text=label_text, font=("Helvetica", 8)).pack(side="left", padx=(0, 4))
            
            lo, hi = -100.0, 100.0
            if name == "Ti": lo, hi = 0.0, 100.0
            if name == "Td": lo, hi = 0.0, 10.0

            sb = ttk.Spinbox(pair_f, textvariable=getattr(loop, f"{name}_var"), from_=lo, to=hi, width=6, state="disabled", justify="center")
            sb.pack(side="left")
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

    def _set_initial_states(self):
        self._power_sw.configure(state="disabled")
        self._log_btn.configure(state="disabled")
        self._col1_radio.configure(state="disabled")
        self._col2_radio.configure(state="disabled")
        self._set_loop_panel_states(False)

    def _set_loop_panel_states(self, enabled):
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
                if "spinbox" in w_widgets:
                    w_widgets["spinbox"].configure(state="disabled")
            else:
                w_widgets["mode"].configure(text="MANUAL")
                w_widgets["sp"].configure(state="disabled")
                w_widgets["slider"].configure(state="normal")
                if "spinbox" in w_widgets:
                    w_widgets["spinbox"].configure(state="normal")
        else:
            for w in w_widgets.values():
                try: w.configure(state="disabled")
                except Exception: pass
            w_widgets["mode"].configure(text="MANUAL")

        # 2. Level panel states
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
                if "spinbox" in l_widgets:
                    l_widgets["spinbox"].configure(state="disabled")
            else:
                l_widgets["mode"].configure(text="MANUAL")
                l_widgets["sp"].configure(state="disabled")
                l_widgets["slider"].configure(state="normal")
                if "spinbox" in l_widgets:
                    l_widgets["spinbox"].configure(state="normal")
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
        super()._enable_powered_controls()
        self._log_btn.configure(state="normal")
        self._col1_radio.configure(state="normal")
        self._col2_radio.configure(state="normal")
        self._set_loop_panel_states(True)

    def _disable_powered_controls(self):
        super()._disable_powered_controls()
        self._log_btn.configure(state="disabled")
        self._col1_radio.configure(state="disabled")
        self._col2_radio.configure(state="disabled")
        self._set_loop_panel_states(False)

    def _on_connection_choice(self, choice):
        if choice == "USB":       self._connect("T7", "USB",      "ANY")
        elif choice == "Ethernet": self._connect("T7", "ETHERNET", self.config.ETHERNET_ADDRESS)
        elif choice == "Disconnect": self._disconnect()

    def _connect(self, model, connection, identifier):
        try:
            self.daq.connect(model, connection, identifier)
            self._connection_status.config(text="Connected", style="Green.TLabel")
            self._status_lbl.config(text="CONNECTED", foreground="green")
            self._power_sw.configure(state="normal")
            self._on_column_select()
        except Exception as exc:
            self._connection_status.config(text=f"Failed: {exc}", style="Red.TLabel")
            self._status_lbl.config(text="DISCONNECTED", foreground="red")

    def _disconnect(self):
        if self._main_power_on:
            self.daq.write(self.config.MAIN_POWER_PIN, 0)
            
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
            self.daq.safety.transition_to(SafetyState.ENABLED)
            self._power_sw.config(text="Main Power: ON")
            self.daq.write(self.config.MAIN_POWER_PIN, 1)
            self._enable_powered_controls()
            self._on_column_select() # Sync hardware state now that it's ENABLED
        else:
            self._power_sw.config(text="Main Power: OFF")
            self.daq.write(self.config.MAIN_POWER_PIN, 0)
            self._disable_powered_controls()
            self._col_select_var.set(True) # Fix column selector glitch
            self.daq.safety.transition_to(SafetyState.CONNECTED_SAFE)

    def _on_column_select(self, *_args):
        col1_active = self._col_select_var.get()
        voltage = 0.0 if col1_active else 5.0
        self.daq.write(self.config.COLUMN_SELECTOR_PIN, voltage)

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
            self._active_dp_lbl_widget.config(text=f"Column {col_num} Pressure Drop\n(kPa)")
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
        widgets["spinbox"].config(textvariable=loop.rounded_valve_position)
        
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
        self.config(background=bg)
        self._canvas_outer.configure(bg=bg)
        self.update_idletasks()

    def _on_mousewheel(self, event):
        scroll = -event.delta * 3 if event.delta in (1, -1) \
                 else int(-1 * (event.delta / 120)) * 3
        self._canvas_outer.yview_scroll(scroll, "units")

    def _update_all_sensors(self):
        super()._update_all_sensors()
        if not self._polling:
            return
        # Update active pressure drop variable
        col1_active = self._col_select_var.get()
        active_dp_key = "column1_pressure_drop" if col1_active else "column2_pressure_drop"
        if active_dp_key in self.sensors:
            self._active_pressure_drop_var.set(self.sensors[active_dp_key].value_var.get())

    def _update_all_loops(self):
        super()._update_all_loops()
        if not self._polling:
            return
        col1_active = self._col_select_var.get()
        active_level_key = "column1_level" if col1_active else "column2_level"
        if active_level_key in self.loops:
            self._water_exit_valve_percent_var.set(str(self.loops[active_level_key].rounded_valve_position.get()))
            self._active_level_var.set(self.loops[active_level_key].measured_var.get())

    def _sync_air_valve_percent(self):
        try:
            val = float(self._air_setpoint_var.get())
            pct = round(val / 150.0 * 100.0) # Scale based on max setpoint 150 SLPM
            self._air_valve_percent_var.set(f"{pct}")
        except ValueError:
            self._air_valve_percent_var.set("0")
