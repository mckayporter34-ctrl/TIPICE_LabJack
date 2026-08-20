# app.py — Catalytic Methanation Redesigned P&ID Interface
# ========================================================

import os
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
from core.base_app import BaseAppFrame
from core.safety import SafetyState

CW, CH = 990, 762

class CatalyticMethanationRedesignFrame(BaseAppFrame):
    """
    Redesigned GUI Frame for Catalytic Methanation, displaying:
    - Col 0: Connect panel, Data logging panel, Apparatus photo.
    - Col 1: Gas Flow Rates panel, Heater power panel, GC stream select panel.
    - Col 2-3: P&ID Canvas with overlays for sensor readouts, and simplified loop panels underneath.
    """

    def __init__(self, parent, config, daq, on_back=None):
        # 1. Initialize custom variables before constructor builds UI
        self._gc_stream_var = tk.StringVar(value="Feed")
        self._heater_power_var = tk.BooleanVar(value=False)
        self._override_var = tk.BooleanVar(value=False)
        
        self._gc_widgets = []
        self._heater_canvas = None
        self._heater_led = None
        self._heater_indicator_lbl = None
        self._heater_switch = None
        
        # Gas flow variables
        self._gas_ui_vars = {
            "hydrogen_setpoint": tk.StringVar(value="0.0"),
            "co2_setpoint": tk.StringVar(value="0.0"),
            "helium_setpoint": tk.StringVar(value="0.0")
        }
        
        # Overlay cards on canvas
        self._overlay_cards = []
        self._loop_toggle_funcs = {}

        super().__init__(parent, config, daq, on_back)

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

        # ── Leftmost Column (Col 0) ──
        # Connection, logging, and apparatus image tiles
        left_col = ttk.Frame(self._sf)
        left_col.grid(row=0, column=0, rowspan=2, padx=10, pady=10, sticky="nsew")
        left_col.rowconfigure(0, weight=1)
        left_col.rowconfigure(1, weight=1)
        left_col.rowconfigure(2, weight=1)

        # Connection panel
        self._build_controls_frame(left_col, row=0, col=0)
        self._power_switch.grid_remove() # Hide default power switch
        self._power_switch.master.grid_configure(pady=(0, 10))

        # Data logging panel
        self._build_data_logging_frame(left_col, row=1, col=0, columnspan=1)
        self._toggle_logging_btn.master.grid_configure(padx=(20, 10))

        # Apparatus image tile
        img_file = getattr(self.config, "APPARATUS_IMAGE", None)
        if img_file:
            # Resolve relative to workspace root if not absolute
            if not os.path.isabs(img_file):
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                resolved_img_file = os.path.join(base_dir, img_file)
            else:
                resolved_img_file = img_file
                
            if os.path.exists(resolved_img_file):
                self._build_apparatus_image(left_col, resolved_img_file, row=2, col=0, columnspan=1)

        # ── Next Column (Col 1) ──
        # Gas flow selector (Rates), Heater power, and GC panels
        mid_col = ttk.Frame(self._sf)
        mid_col.grid(row=0, column=1, rowspan=2, padx=10, pady=10, sticky="nsew")

        self._build_gas_flow_rates_panel(mid_col, row=0, col=0)
        self._build_heater_power_panel(mid_col, row=1, col=0)
        self._build_gc_select_panel(mid_col, row=2, col=0)

        # ── Right Column (Cols 2-3) ──
        # P&ID Diagram (Col 2-3, Row 0)
        self._build_pid_canvas(self._sf, row=0, col=2, columnspan=2)

        # Control loops underneath (Col 2 and Col 3, Row 1)
        self._build_horizontal_loops(self._sf, row=1, col=2)

    # ── Custom Panels ──────────────────────────────────────────────────────────

    def _build_gc_select_panel(self, parent, row, col, columnspan=1):
        f = ttk.LabelFrame(parent, text="GC Analysis Stream", padding=(10, 10))
        f.grid(row=row, column=col, columnspan=columnspan, padx=(5, 5), pady=(5, 5), sticky="nsew")

        self._gc_widgets = []

        r1 = ttk.Radiobutton(
            f, text="Reactor Feed", value="Feed",
            variable=self._gc_stream_var,
            command=self._on_gc_stream_change
        )
        r1.grid(row=0, column=0, padx=5, pady=8, sticky="w")
        self._gc_widgets.append(r1)

        r2 = ttk.Radiobutton(
            f, text="Reactor Exhaust", value="Exhaust",
            variable=self._gc_stream_var,
            command=self._on_gc_stream_change
        )
        r2.grid(row=1, column=0, padx=5, pady=8, sticky="w")
        self._gc_widgets.append(r2)

    def _build_apparatus_image(self, parent, img_path, row, col, columnspan):
        f = ttk.LabelFrame(parent, text="Apparatus Diagram", padding=(5, 5))
        f.grid(row=row, column=col, columnspan=columnspan, padx=(10, 5), pady=(5, 5), sticky="nsew")
        
        f.rowconfigure(0, weight=1)
        f.columnconfigure(0, weight=1)
        
        try:
            from PIL import Image, ImageTk
            has_pil = True
        except ImportError:
            has_pil = False

        if has_pil:
            try:
                img = Image.open(img_path)
                img = img.resize((200, 200))
                self._apparatus_photo = ImageTk.PhotoImage(img)
                lbl = ttk.Label(f, image=self._apparatus_photo, anchor="center")
                lbl.grid(row=0, column=0, padx=5, pady=5, sticky="")
            except Exception as e:
                print(f"Error loading apparatus image {img_path}: {e}")
                ttk.Label(f, text="[Image Not Found]").grid(row=0, column=0, padx=5, pady=5, sticky="")
        else:
            ttk.Label(f, text="[Install Pillow to view image]").grid(row=0, column=0, padx=5, pady=5, sticky="")

    def _build_heater_power_panel(self, parent, row, col, columnspan=1):
        f = ttk.LabelFrame(parent, text="Heater Control", padding=(10, 10))
        f.grid(row=row, column=col, columnspan=columnspan, padx=(5, 5), pady=(5, 5), sticky="nsew")

        self._heater_switch = ttk.Checkbutton(
            f, text="Heater Power: OFF", style="Switch",
            variable=self._heater_power_var,
            command=self._on_heater_toggle
        )
        self._heater_switch.grid(row=0, column=0, padx=5, pady=10, sticky="w")
        
        self._switch_widgets.append((self._heater_switch, "Heater Power"))
        self._switch_vars["heater_power"] = self._heater_power_var

        # LED Indicator Row
        ind_frame = ttk.Frame(f)
        ind_frame.grid(row=1, column=0, padx=5, pady=5, sticky="w")

        # Resolve background dynamically to match theme
        bg_color = "#161b22"
        try:
            temp = tk.Frame(f)
            bg_color = temp.cget("bg")
            temp.destroy()
        except Exception:
            pass

        self._heater_canvas = tk.Canvas(
            ind_frame, width=16, height=16, bg=bg_color, highlightthickness=0
        )
        self._heater_canvas.grid(row=0, column=0, padx=(0, 8), sticky="w")
        self._heater_led = self._heater_canvas.create_oval(
            2, 2, 14, 14, fill="#484f58", outline="#30363d"
        )

        self._heater_indicator_lbl = ttk.Label(
            ind_frame, text="HEATER INACTIVE", font=("Helvetica", 9, "bold")
        )
        self._heater_indicator_lbl.grid(row=0, column=1, sticky="w")

    def _build_gas_flow_rates_panel(self, parent, row, col, columnspan=1, rowspan=1):
        f = ttk.LabelFrame(parent, text="Gas Flow Rates", padding=(10, 10))
        f.grid(row=row, column=col, columnspan=columnspan, rowspan=rowspan, padx=(5, 5), pady=(0, 5), sticky="nsew")

        # Headers
        ttk.Label(f, text="Gas", font=("Helvetica", 12, "bold")).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Label(f, text="Setpoint", font=("Helvetica", 12, "bold")).grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(f, text="Actual", font=("Helvetica", 12, "bold")).grid(row=0, column=2, padx=5, pady=5)
        ttk.Label(f, text="Unit", font=("Helvetica", 12, "bold")).grid(row=0, column=3, padx=5, pady=5, sticky="w")

        gases = [
            ("hydrogen_setpoint", "hydrogen_actual"),
            ("co2_setpoint", "co2_actual"),
            ("helium_setpoint", "helium_actual")
        ]

        for idx, (sp_key, act_key) in enumerate(gases):
            cfg = self.config.MANUAL_ANALOG_OUTPUTS.get(sp_key)
            sensor = self.sensors.get(act_key)
            if not cfg or not sensor:
                continue

            row_idx = idx + 1

            # Gas name
            ttk.Label(f, text=cfg["label"], font=("Helvetica", 10, "bold"), wraplength=70).grid(row=row_idx, column=0, padx=5, pady=12, sticky="w")

            # Setpoint Spinbox
            ui_var = self._gas_ui_vars[sp_key]
            ui_var.set(str(cfg["default"]))

            self._manual_analog_vars[sp_key] = tk.StringVar(value=str(cfg["default"]))

            sb = ttk.Spinbox(
                f, from_=cfg["min_val"], to=cfg["max_val"], textvariable=ui_var,
                width=7, state="disabled"
            )
            sb.grid(row=row_idx, column=1, padx=5, pady=12)
            self._manual_analog_widgets.append(sb)

            # Actual value entry
            entry = ttk.Entry(f, textvariable=sensor.value_var, state="readonly", width=8, justify="center")
            entry.grid(row=row_idx, column=2, padx=5, pady=12)
            self._sensor_widgets[act_key] = {"entry": entry}

            # Unit
            ttk.Label(f, text=cfg["unit"]).grid(row=row_idx, column=3, padx=5, pady=12, sticky="w")

        # Required parameters descriptions
        ttk.Label(f, text="Required Parameters:", font=("Helvetica", 11, "bold")).grid(
            row=4, column=0, columnspan=4, padx=5, pady=(15, 2), sticky="w"
        )
        ttk.Label(f, text="• Total flow rate must be exactly 200 sccm.", font=("Helvetica", 11), wraplength=250).grid(
            row=5, column=0, columnspan=4, padx=5, pady=2, sticky="w"
        )
        ttk.Label(f, text="• H₂ flow rate must be above stoichiometric (H₂ > 4 × CO₂) unless CO₂ is 0.", font=("Helvetica", 11), wraplength=250).grid(
            row=6, column=0, columnspan=4, padx=5, pady=2, sticky="w"
        )

        # Apply Changes Button
        self._apply_btn = ttk.Button(f, text="Apply Changes", command=self._apply_gas_changes, state="disabled")
        self._apply_btn.grid(row=7, column=0, columnspan=4, padx=5, pady=(10, 5), sticky="ew")
        self._manual_analog_widgets.append(self._apply_btn)

    # ── P&ID Canvas & Sensor Overlays ──────────────────────────────────────────

    def _build_pid_canvas(self, parent, row, col, columnspan):
        outer = ttk.LabelFrame(parent, text="Piping and Instrumentation Diagram", padding=(10, 10))
        outer.grid(row=row, column=col, columnspan=columnspan, padx=10, pady=10, sticky="nsew")

        self._pid = tk.Canvas(outer, width=CW, height=CH, bg="white", highlightthickness=0)
        self._pid.pack(expand=True)

        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            bg_path = os.path.join(base_dir, "PI diagrams", "catalytic_methanation_pid.png")
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
        
        # Approximate overlay locations (x, y, label, variable)
        overlays = [
            (198, 35, f"H₂ Flow ({s['hydrogen_actual'].unit})", s["hydrogen_actual"].value_var),
            (198, 291, f"CO₂ Flow ({s['co2_actual'].unit})", s["co2_actual"].value_var),
            (198, 540, f"He Flow ({s['helium_actual'].unit})", s["helium_actual"].value_var),
            (736, 222, f"Reactor Temperature ({s['reactor_temp_sensor'].unit})", s["reactor_temp_sensor"].value_var),
            (736, 388, f"Heater Temperature ({s['heater_temp_sensor'].unit})", s["heater_temp_sensor"].value_var),
            (655, 575, f"Pressure ({s['reactor_pressure_sensor'].unit})", s["reactor_pressure_sensor"].value_var),
            (753, 720, "Pressure Valve (%)", self.loops["pressure"].rounded_valve_position),
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

    # ── Control Loops (Simplified tiles side-by-side) ──────────────────────────

    def _build_horizontal_loops(self, parent, row, col):
        self._loop_widgets = {}
        # Pressure loop in Column 2, Temperature loop in Column 3
        self._loop_widgets["pressure"] = self._build_simple_loop_panel(
            parent, "pressure", self.loops["pressure"], row=row, col=col
        )
        self._loop_widgets["temperature"] = self._build_simple_loop_panel(
            parent, "temperature", self.loops["temperature"], row=row, col=col+1
        )

    def _build_simple_loop_panel(self, parent, key, loop, row, col):
        f = ttk.LabelFrame(parent, text=loop.label, padding=(12, 8))
        f.grid(row=row, column=col, padx=8, pady=(5, 20), sticky="nsew")
        f.columnconfigure(1, weight=1)

        widgets = {}

        # Setpoint
        ttk.Label(f, text=f"Setpoint ({loop.unit})",
                  wraplength=110).grid(row=0, column=0, sticky="w", padx=4, pady=4)
        sp = ttk.Spinbox(f, from_=loop.setpoint_min, to=loop.setpoint_max,
                         textvariable=loop.setpoint_var, width=8,
                         state="disabled")
        sp.grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        widgets["setpoint_spinbox"] = sp

        # Measured Value
        ttk.Label(f, text=f"Measured ({loop.unit})",
                  wraplength=110).grid(row=1, column=0, sticky="w", padx=4, pady=4)
        meas = ttk.Entry(f, textvariable=loop.measured_var, width=8,
                         state="disabled")
        meas.grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        widgets["measured_entry"] = meas

        # Mode switch, Slider, and Spinbox manual entry all on the same row
        row2_frame = ttk.Frame(f)
        row2_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=4, pady=6)

        mode_var = tk.BooleanVar(value=loop.is_auto)

        mode_btn = ttk.Checkbutton(row2_frame, text="MANUAL", style="Switch",
                                   variable=mode_var, command=None,
                                   state="disabled")
        mode_btn.pack(side="left", padx=(0, 6))
        widgets["mode_switch"] = mode_btn

        slider = ttk.Scale(row2_frame, from_=0, to=100,
                           variable=loop.valve_position, state="disabled")
        slider.pack(side="left", fill="x", expand=True, padx=6)
        widgets["scale"] = slider

        spinbox = ttk.Spinbox(row2_frame, from_=0, to=100, width=5,
                              textvariable=loop.rounded_valve_position, state="disabled")
        spinbox.pack(side="right", padx=(6, 0))
        widgets["manual_spinbox"] = spinbox

        def _sync_slider(*_a):
            try:
                val = round(loop.valve_position.get())
                if loop.rounded_valve_position.get() != val:
                    loop.rounded_valve_position.set(val)
            except Exception:
                pass
        loop.valve_position.trace_add("write", _sync_slider)

        def _sync_spinbox(*_a):
            try:
                val = loop.rounded_valve_position.get()
                if abs(loop.valve_position.get() - val) > 0.01:
                    loop.valve_position.set(val)
            except Exception:
                pass
        loop.rounded_valve_position.trace_add("write", _sync_spinbox)

        def _commit_spinbox(event=None):
            try:
                val = int(spinbox.get())
                val = max(0, min(100, val))
                loop.valve_position.set(float(val))
                loop.rounded_valve_position.set(val)
            except ValueError:
                spinbox.set(round(loop.valve_position.get()))

        spinbox.bind("<Return>", _commit_spinbox)
        spinbox.bind("<FocusOut>", _commit_spinbox)

        def _toggle(user_initiated=False):
            if user_initiated and key == "pressure" and not mode_var.get():
                from tkinter.simpledialog import askstring
                pwd = askstring("Password Required", "Enter password to enable manual mode:", show='*')
                if pwd != "dietcoke":
                    mode_var.set(True)
                    return

            loop.is_auto = mode_var.get()
            if loop.is_auto:
                mode_btn.config(text="AUTO")
                if self._main_power_on:
                    sp.config(state="normal")
                    slider.config(state="disabled")
                    spinbox.config(state="disabled")
                    try:
                        loop.pid.initialize(loop.get_manual_voltage())
                    except Exception:
                        loop.pid.reset()
            else:
                mode_btn.config(text="MANUAL")
                if self._main_power_on:
                    sp.config(state="disabled")
                    slider.config(state="normal")
                    spinbox.config(state="normal")
                    loop.pid.reset()

        mode_btn.config(command=lambda: _toggle(user_initiated=True))

        # PID constants in a row (centered)
        pid_f = ttk.Frame(f)
        pid_f.grid(row=3, column=0, columnspan=2, sticky="",
                   padx=4, pady=(6, 4))

        for i, (name, var, lo, hi) in enumerate([
            ("Kc",       loop.Kc_var, -1000, 1000),
            ("Ti (min)", loop.Ti_var, 0,    1000),
            ("Td",       loop.Td_var, 0,     100),
        ]):
            pair_f = ttk.Frame(pid_f)
            pair_f.pack(side="left", padx=6)
            ttk.Label(pair_f, text=name, font=("Helvetica", 8)).pack(side="left", padx=(0, 4))
            sb = ttk.Spinbox(pair_f, textvariable=var, from_=lo, to=hi,
                             width=6, state="disabled", justify="center")
            sb.pack(side="left")
            widgets[f"{name.split()[0]}_spinbox"] = sb

        self._loop_toggle_funcs[key] = _toggle
        return widgets

    # ── State control overrides ────────────────────────────────────────────────

    def _set_initial_states(self):
        super()._set_initial_states()
        self._set_gc_widgets_state("disabled")
        self._heater_switch.configure(state="disabled")
        self._heater_canvas.itemconfig(self._heater_led, fill="#484f58", outline="#30363d")
        self._heater_indicator_lbl.config(text="HEATER INACTIVE", foreground="")

    def _connect(self, model, connection, identifier):
        super()._connect(model, connection, identifier)
        if self.daq.is_connected:
            self._main_power_on = True
            self._main_power_var.set(True)
            self.daq.safety.transition_to(SafetyState.ENABLED)
            self._enable_powered_controls()

    def _enable_powered_controls(self):
        super()._enable_powered_controls()
        self._set_gc_widgets_state("normal")
        self._heater_switch.configure(state="normal")

        # Synchronize outputs
        self._on_gc_stream_change()
        self._on_heater_toggle()

        # Synchronize loop setpoints vs manual sliders
        for func in self._loop_toggle_funcs.values():
            func()

    def _disable_powered_controls(self):
        self._gc_stream_var.set("Feed")
        self._heater_power_var.set(False)

        for var in self._gas_ui_vars.values():
            var.set("0.0")

        self._heater_switch.config(text="Heater Power: OFF")
        self._heater_canvas.itemconfig(self._heater_led, fill="#484f58", outline="#30363d")
        self._heater_indicator_lbl.config(text="HEATER INACTIVE", foreground="")

        super()._disable_powered_controls()

        self._set_gc_widgets_state("disabled")
        self._heater_switch.configure(state="disabled")

        if self.daq.is_connected:
            # Zero gas setpoint outputs
            for key in ["hydrogen_setpoint", "co2_setpoint", "helium_setpoint"]:
                cfg = self.config.MANUAL_ANALOG_OUTPUTS.get(key)
                if cfg:
                    self.daq.write(cfg["pin"], 0.0)

            # Zero GC stream select pins
            gc_pins = getattr(self.config, "GC_SELECT_PINS", ["FIO5", "FIO6"])
            for pin in gc_pins:
                self.daq.write(pin, 0.0)

            # Zero heater relay pin
            heater_pin = getattr(self.config, "HEATER_POWER_PIN", "FIO4")
            self.daq.write(heater_pin, 0.0)

    def _set_gc_widgets_state(self, state):
        for w in self._gc_widgets:
            w.configure(state=state)

    # ── Custom Event Callbacks ─────────────────────────────────────────────────

    def _on_gc_stream_change(self):
        if not self._main_power_on:
            return
        stream = self._gc_stream_var.get()
        val = 5.0 if stream == "Feed" else 0.0
        pins = getattr(self.config, "GC_SELECT_PINS", ["FIO5", "FIO6"])
        try:
            for pin in pins:
                self.daq.write(pin, val)
        except Exception as e:
            print(f"[GC Select] Error writing: {e}")

    def _on_heater_toggle(self):
        state = self._heater_power_var.get()
        
        if state:
            try:
                h2 = float(self.sensors["hydrogen_actual"].value_var.get())
                co2 = float(self.sensors["co2_actual"].value_var.get())
                he = float(self.sensors["helium_actual"].value_var.get())
                total = h2 + co2 + he
            except Exception:
                total = 0.0
                
            if total < 195.0:
                self._heater_power_var.set(False)
                messagebox.showwarning("Warning", "Gas Flow Insufficient. Begin gas flow to turn on heater.")
                return

        self._heater_switch.config(text=f"Heater Power: {'ON' if state else 'OFF'}")

        if state:
            self._heater_canvas.itemconfig(self._heater_led, fill="#3fb950", outline="#2ea44f")
            self._heater_indicator_lbl.config(text="HEATER ACTIVE", foreground="#3fb950")
        else:
            self._heater_canvas.itemconfig(self._heater_led, fill="#484f58", outline="#30363d")
            self._heater_indicator_lbl.config(text="HEATER INACTIVE", foreground="")

        pin = getattr(self.config, "HEATER_POWER_PIN", "FIO4")
        if self._main_power_on:
            try:
                self.daq.write(pin, 5.0 if state else 0.0)
                if not state:
                    temp_loop = self.loops.get("temperature")
                    if temp_loop:
                        self.daq.write(temp_loop.output_pin, 0.0)
                        temp_loop.set_valve_display(0.0)
            except Exception as e:
                print(f"[Heater] Error writing to {pin}: {e}")

    def _apply_gas_changes(self):
        try:
            h2 = float(self._gas_ui_vars["hydrogen_setpoint"].get())
            co2 = float(self._gas_ui_vars["co2_setpoint"].get())
            he = float(self._gas_ui_vars["helium_setpoint"].get())
        except ValueError:
            messagebox.showerror("Validation Error", "All gas setpoints must be valid numbers.")
            return

        total = h2 + co2 + he
        validation_error = None
        
        if total > 0.0:
            if abs(total - 200.0) > 0.1:
                validation_error = (
                    f"Total gas flow rate must be exactly 200 sccm.\n"
                    f"Current total: {total:.2f} sccm\n"
                    f"(H₂: {h2:.1f}, CO₂: {co2:.1f}, He: {he:.1f})"
                )
            else:
                stoich_limit = 4.0 * co2
                if h2 <= stoich_limit and not (co2 == 0.0 and h2 == 0.0):
                    validation_error = (
                        f"H₂ flow rate must be above the stoichiometric amount (H₂ > 4 × CO₂).\n"
                        f"For {co2:.2f} sccm of CO₂, H₂ must be > {stoich_limit:.2f} sccm.\n"
                        f"Current H₂ flow: {h2:.2f} sccm"
                    )

        if validation_error:
            from tkinter import Toplevel, Label, Entry, Button, StringVar
            top = Toplevel()
            top.title("Validation Error")
            top.grab_set()
            Label(top, text=validation_error, justify="left").pack(padx=20, pady=10)
            Label(top, text="Enter password to override:").pack(padx=20, pady=(0, 5))
            pwd_var = StringVar()
            entry = Entry(top, textvariable=pwd_var, show='*')
            entry.pack(padx=20, pady=5)
            
            def on_submit():
                if pwd_var.get() == "dietcoke":
                    top.destroy()
                    self._manual_analog_vars["hydrogen_setpoint"].set(str(h2))
                    self._manual_analog_vars["co2_setpoint"].set(str(co2))
                    self._manual_analog_vars["helium_setpoint"].set(str(he))
                else:
                    messagebox.showerror("Error", "Incorrect password", parent=top)
            
            def on_cancel():
                top.destroy()
                
            btn_frame = ttk.Frame(top)
            btn_frame.pack(pady=10)
            Button(btn_frame, text="Override", command=on_submit).pack(side="left", padx=5)
            Button(btn_frame, text="Cancel", command=on_cancel).pack(side="left", padx=5)
            return

        self._manual_analog_vars["hydrogen_setpoint"].set(str(h2))
        self._manual_analog_vars["co2_setpoint"].set(str(co2))
        self._manual_analog_vars["helium_setpoint"].set(str(he))

    # ── Logging Extensions ─────────────────────────────────────────────────────

    def _build_logger(self):
        super()._build_logger()
        self.logger._sources["GC Analysis Stream"] = lambda: self._gc_stream_var.get()
        self.logger._sources["Heater Power State"] = lambda: "ON" if self._heater_power_var.get() else "OFF"

    def _on_mousewheel(self, event):
        scroll = -event.delta * 3 if event.delta in (1, -1) \
                 else int(-1 * (event.delta / 120)) * 3
        self._canvas_outer.yview_scroll(scroll, "units")
