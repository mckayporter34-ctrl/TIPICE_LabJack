# app.py — Custom UI and control logic for Catalytic Methanation apparatus
# =======================================================================

import tkinter as tk
from tkinter import ttk
from core.base_app import BaseAppFrame


class CatalyticMethanationFrame(BaseAppFrame):
    """
    Custom frame subclass for Catalytic Methanation, implementing:
    1. A GC Analysis Stream panel (Reactor Feed vs Reactor Exhaust)
    2. A Gas Flow Rate panel (Hydrogen, CO2, Helium setpoints and actuals)
    3. A Heater Power control panel with ON/OFF switch and a custom LED indicator.
    """

    def __init__(self, parent, config, daq, on_back=None):
        # 1. Initialize custom Tkinter variables before super class calls _build_ui()
        self._gc_stream_var = tk.StringVar(value="Feed")
        self._heater_power_var = tk.BooleanVar(value=False)
        self._gc_widgets = []
        self._heater_canvas = None
        self._heater_led = None
        self._heater_indicator_lbl = None
        self._heater_switch = None

        # 2. Define gas UI variables decoupled from self._manual_analog_vars
        self._gas_ui_vars = {
            "hydrogen_setpoint": tk.StringVar(value="0.0"),
            "co2_setpoint": tk.StringVar(value="0.0"),
            "helium_setpoint": tk.StringVar(value="0.0")
        }
        self._override_var = tk.BooleanVar(value=False)

        super().__init__(parent, config, daq, on_back)

    def _build_ui(self):
        # 2. Call the base class UI builder. This sets up the header, main body canvas,
        # controls, logo, data logging panel, and standard control loops.
        super()._build_ui()

        # Hide the main power switch entirely from the grid
        self._power_switch.grid_remove()

        # 3. Build our custom panels on the scrollable frame self._sf
        # GC Analysis Stream Panel in Col 1, Row 1
        self._build_gc_select_panel(self._sf, row=1, col=1)

        # Heater Power Panel in Col 1, Row 2
        self._build_heater_power_panel(self._sf, row=2, col=1)

        # Gas Flow Rates Panel in Col 2, Row 0 (spanning 2 rows)
        self._build_gas_flow_rates_panel(self._sf, row=0, col=2, rowspan=2)

    def _build_gc_select_panel(self, parent, row, col, columnspan=1):
        f = ttk.LabelFrame(parent, text="GC Analysis Stream", padding=(20, 15))
        f.grid(row=row, column=col, columnspan=columnspan, padx=(10, 10), pady=(10, 10), sticky="nsew")

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

    def _build_heater_power_panel(self, parent, row, col, columnspan=1):
        f = ttk.LabelFrame(parent, text="Heater Control", padding=(20, 15))
        f.grid(row=row, column=col, columnspan=columnspan, padx=(10, 10), pady=(10, 10), sticky="nsew")

        self._heater_switch = ttk.Checkbutton(
            f, text="Heater Power: OFF", style="Switch",
            variable=self._heater_power_var,
            command=self._on_heater_toggle
        )
        self._heater_switch.grid(row=0, column=0, padx=5, pady=10, sticky="w")
        
        # Add to main switch widgets for enablement tracking
        self._switch_widgets.append((self._heater_switch, "Heater Power"))
        self._switch_vars["heater_power"] = self._heater_power_var

        # LED Indicator Row
        ind_frame = ttk.Frame(f)
        ind_frame.grid(row=1, column=0, padx=5, pady=5, sticky="w")

        # Resolve background dynamically to match theme
        bg_color = "#161b22"  # standard panel bg
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
        f = ttk.LabelFrame(parent, text="Gas Flow Rates", padding=(20, 15))
        f.grid(row=row, column=col, columnspan=columnspan, rowspan=rowspan, padx=(10, 10), pady=(10, 10), sticky="nsew")

        # Headers
        ttk.Label(f, text="Gas", font=("Helvetica", 10, "bold")).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Label(f, text="Setpoint", font=("Helvetica", 10, "bold")).grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(f, text="Actual", font=("Helvetica", 10, "bold")).grid(row=0, column=2, padx=5, pady=5)
        ttk.Label(f, text="Unit", font=("Helvetica", 10, "bold")).grid(row=0, column=3, padx=5, pady=5, sticky="w")

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
            ttk.Label(f, text=cfg["label"], font=("Helvetica", 9, "bold")).grid(row=row_idx, column=0, padx=5, pady=12, sticky="w")

            # Setpoint Spinbox (bound to UI variable)
            ui_var = self._gas_ui_vars[sp_key]
            ui_var.set(str(cfg["default"]))

            # Hardware target variable (read by BaseAppFrame loop)
            self._manual_analog_vars[sp_key] = tk.StringVar(value=str(cfg["default"]))

            sb = ttk.Spinbox(
                f, from_=cfg["min_val"], to=cfg["max_val"], textvariable=ui_var,
                width=7, state="disabled"
            )
            sb.grid(row=row_idx, column=1, padx=5, pady=12)
            self._manual_analog_widgets.append(sb)

            # Actual value display
            entry = ttk.Entry(f, textvariable=sensor.value_var, state="readonly", width=8, justify="center")
            entry.grid(row=row_idx, column=2, padx=5, pady=12)
            self._sensor_widgets[act_key] = {"entry": entry}

            # Unit
            ttk.Label(f, text=cfg["unit"]).grid(row=row_idx, column=3, padx=5, pady=12, sticky="w")

        # Instruction Text / Constraints labels
        ttk.Label(f, text="Required Parameters:", font=("Helvetica", 9, "bold")).grid(
            row=4, column=0, columnspan=4, padx=5, pady=(15, 2), sticky="w"
        )
        ttk.Label(f, text="• Total flow rate must be exactly 200 sccm.", font=("Helvetica", 9)).grid(
            row=5, column=0, columnspan=4, padx=5, pady=2, sticky="w"
        )
        ttk.Label(f, text="• H₂ flow rate must be above stoichiometric (H₂ > 4 × CO₂).", font=("Helvetica", 9)).grid(
            row=6, column=0, columnspan=4, padx=5, pady=2, sticky="w"
        )

        # Override Limits Checkbutton
        self._override_cb = ttk.Checkbutton(
            f, text="Override Limits", variable=self._override_var, state="disabled"
        )
        self._override_cb.grid(row=7, column=0, columnspan=4, padx=5, pady=(10, 5), sticky="w")
        self._manual_analog_widgets.append(self._override_cb)

        # Apply Changes Button
        self._apply_btn = ttk.Button(f, text="Apply Changes", command=self._apply_gas_changes, state="disabled")
        self._apply_btn.grid(row=8, column=0, columnspan=4, padx=5, pady=(10, 5), sticky="ew")
        self._manual_analog_widgets.append(self._apply_btn)

    # ══════════════════════════════════════════════════════════════════
    # State change overrides (enabling/disabling and zeroing)
    # ══════════════════════════════════════════════════════════════════

    def _set_initial_states(self):
        super()._set_initial_states()
        self._set_gc_widgets_state("disabled")
        self._heater_switch.configure(state="disabled")

        # Visual LED state
        self._heater_canvas.itemconfig(self._heater_led, fill="#484f58", outline="#30363d")
        self._heater_indicator_lbl.config(text="HEATER INACTIVE", foreground="")

    def _connect(self, model, connection, identifier):
        super()._connect(model, connection, identifier)
        if self.daq.is_connected:
            self._main_power_on = True
            self._main_power_var.set(True)
            self._enable_powered_controls()

    def _enable_powered_controls(self):
        super()._enable_powered_controls()
        self._set_gc_widgets_state("normal")
        self._heater_switch.configure(state="normal")

        # Synchronize physical outputs with UI variable settings
        self._on_gc_stream_change()
        self._on_heater_toggle()

    def _disable_powered_controls(self):
        # Reset UI control variables to defaults
        self._gc_stream_var.set("Feed")
        self._heater_power_var.set(False)

        # Reset gas UI variables to 0.0
        for var in self._gas_ui_vars.values():
            var.set("0.0")

        # Reset override limits checkbutton
        self._override_var.set(False)

        # Update labels and indicators
        self._heater_switch.config(text="Heater Power: OFF")
        self._heater_canvas.itemconfig(self._heater_led, fill="#484f58", outline="#30363d")
        self._heater_indicator_lbl.config(text="HEATER INACTIVE", foreground="")

        super()._disable_powered_controls()

        # Disable custom widgets
        self._set_gc_widgets_state("disabled")
        self._heater_switch.configure(state="disabled")

        # Zero physical outputs specifically managed by this class
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

    # ══════════════════════════════════════════════════════════════════
    # Custom callbacks
    # ══════════════════════════════════════════════════════════════════

    def _on_gc_stream_change(self):
        if not self._main_power_on:
            return
        stream = self._gc_stream_var.get()
        # Feed is HIGH (5.0V), Exhaust is LOW (0.0V)
        val = 5.0 if stream == "Feed" else 0.0
        pins = getattr(self.config, "GC_SELECT_PINS", ["FIO5", "FIO6"])
        try:
            for pin in pins:
                self.daq.write(pin, val)
        except Exception as e:
            print(f"[GC Select] Error writing: {e}")

    def _on_heater_toggle(self):
        state = self._heater_power_var.get()
        self._heater_switch.config(text=f"Heater Power: {'ON' if state else 'OFF'}")

        # Update LED colors & text highlights
        if state:
            self._heater_canvas.itemconfig(self._heater_led, fill="#3fb950", outline="#2ea44f")
            self._heater_indicator_lbl.config(text="HEATER ACTIVE", foreground="#3fb950")
        else:
            self._heater_canvas.itemconfig(self._heater_led, fill="#484f58", outline="#30363d")
            self._heater_indicator_lbl.config(text="HEATER INACTIVE", foreground="")

        # Write to physical relay on LabJack
        pin = getattr(self.config, "HEATER_POWER_PIN", "FIO4")
        if self._main_power_on:
            try:
                self.daq.write(pin, 5.0 if state else 0.0)

                # If heater is turned OFF, immediately zero the Temperature loop output for safety
                if not state:
                    temp_loop = self.loops.get("temperature")
                    if temp_loop:
                        self.daq.write(temp_loop.output_pin, 0.0)
                        temp_loop.set_valve_display(0.0)
            except Exception as e:
                print(f"[Heater] Error writing to {pin}: {e}")

    def _apply_gas_changes(self):
        from tkinter import messagebox

        # 1. Parse flowrate values from UI Spinboxes
        try:
            h2 = float(self._gas_ui_vars["hydrogen_setpoint"].get())
            co2 = float(self._gas_ui_vars["co2_setpoint"].get())
            he = float(self._gas_ui_vars["helium_setpoint"].get())
        except ValueError:
            messagebox.showerror(
                "Validation Error",
                "All gas setpoints must be valid numbers."
            )
            return

        # 2. Check if limits override is active
        if not self._override_var.get():
            # Check if total flow rate is exactly 200 sccm (with 0.1 sccm tolerance)
            total = h2 + co2 + he
            if abs(total - 200.0) > 0.1:
                messagebox.showerror(
                    "Validation Error",
                    f"Total gas flow rate must be exactly 200 sccm.\n"
                    f"Current total: {total:.2f} sccm\n"
                    f"(H₂: {h2:.1f}, CO₂: {co2:.1f}, He: {he:.1f})"
                )
                return

            # Check if H2 flow rate is strictly above stoichiometric (H2 > 4 * CO2)
            stoich_limit = 4.0 * co2
            if h2 <= stoich_limit:
                messagebox.showerror(
                    "Validation Error",
                    f"H₂ flow rate must be above the stoichiometric amount (H₂ > 4 × CO₂).\n"
                    f"For {co2:.2f} sccm of CO₂, H₂ must be > {stoich_limit:.2f} sccm.\n"
                    f"Current H₂ flow: {h2:.2f} sccm"
                )
                return

        # 3. Apply UI variables to actual hardware control variables
        self._manual_analog_vars["hydrogen_setpoint"].set(str(h2))
        self._manual_analog_vars["co2_setpoint"].set(str(co2))
        self._manual_analog_vars["helium_setpoint"].set(str(he))

    # ══════════════════════════════════════════════════════════════════
    # Logging Extensions
    # ══════════════════════════════════════════════════════════════════

    def _build_logger(self):
        super()._build_logger()
        # Add custom data entries to the log output dictionary
        self.logger._sources["H2 Setpoint (SCCM)"] = lambda: self._manual_analog_vars["hydrogen_setpoint"].get()
        self.logger._sources["CO2 Setpoint (SCCM)"] = lambda: self._manual_analog_vars["co2_setpoint"].get()
        self.logger._sources["He Setpoint (SCCM)"] = lambda: self._manual_analog_vars["helium_setpoint"].get()
        self.logger._sources["GC Analysis Stream"] = lambda: self._gc_stream_var.get()
        self.logger._sources["Heater Power State"] = lambda: "ON" if self._heater_power_var.get() else "OFF"
