# control_loop.py
# Holds the ControlLoop dataclass — one instance per PID-controlled channel.
# Groups together all the state that was previously scattered across dozens of
# individual StringVar / DoubleVar / BooleanVar attributes on the app class.

import tkinter as tk
from dataclasses import dataclass, field
from typing import Callable, Optional, List

from core.pid_controller import PIDController
from core.numeric_entry import finite_number


@dataclass
class ControlLoop:
    """
    Represents one closed-loop PID control channel.

    The loop reads from `input_pin`, runs a PID controller, and writes the
    output voltage to `output_pin`.  It also exposes tkinter variables that
    the GUI widgets bind to directly — setpoint entry, live measurement
    display, valve position slider, and PID tuning spinboxes.

    Attributes
    ----------
    key               : Unique identifier matching the key in CONTROL_LOOP_CONFIGS.
    label             : Human-readable panel title shown in the GUI.
    unit              : Engineering unit for setpoint and measurement (e.g. "L/min").
    input_pin         : LabJack register to read the process variable from.
    output_pin        : LabJack register to write the control voltage to.
    calibration       : Callable converting raw voltage → engineering units.
    setpoint_min/max  : Spinbox limits for the operator setpoint entry.
    pid               : PIDController instance (created from pid_defaults in config).
    extra_sensor_keys : Optional list of keys into the sensors dict. If provided,
                        the matching sensors' value_vars are displayed inside this panel.
    extra_sensor_key  : Backwards compatibility string for a single extra sensor.
    """
    key:               str
    label:             str
    unit:              str
    input_pin:         str
    output_pin:        str
    calibration:      Callable[[float], float]
    setpoint_min:     float
    setpoint_max:     float
    pid:              PIDController
    extra_sensor_keys: Optional[List[str]] = None
    extra_sensor_key:  Optional[str] = None

    # ── tkinter state variables (auto-created) ────────────────────────────────
    setpoint_var:     tk.StringVar  = field(default_factory=lambda: tk.StringVar(value='0'))
    measured_var:     tk.StringVar  = field(default_factory=tk.StringVar)

    # valve_position  runs 0–100 (percent) and drives both the slider and
    # the vertical progress bar.  rounded_valve_position is the integer
    # copy kept in sync for the spinbox and the read-only entry widget.
    valve_position:         tk.DoubleVar = field(default_factory=tk.DoubleVar)
    rounded_valve_position: tk.IntVar    = field(default_factory=tk.IntVar)

    # PID tuning vars — bound to the Kc / Ti / Td spinboxes in the panel.
    Kc_var: tk.StringVar = field(default_factory=tk.StringVar)
    Ti_var: tk.StringVar = field(default_factory=tk.StringVar)
    Td_var: tk.StringVar = field(default_factory=tk.StringVar)

    # Mode flag: True = PID is active, False = operator controls slider manually.
    is_auto: bool = False

    def __post_init__(self):
        self.measured_var.set("---")
        # Seed the tuning spinboxes from the PIDController's initial values.
        self.Kc_var.set(self.pid.Kc)
        self.Ti_var.set(self.pid.Ti)
        self.Td_var.set(self.pid.Td)

        # Normalize to list of extra sensor keys
        if self.extra_sensor_keys is None:
            if self.extra_sensor_key is not None:
                self.extra_sensor_keys = [self.extra_sensor_key]
            else:
                self.extra_sensor_keys = []

    # ------------------------------------------------------------------
    # Helpers used by the update loop in app.py
    # ------------------------------------------------------------------

    def apply_calibration(self, raw_voltage: float) -> float:
        return self.calibration(raw_voltage)

    def set_measured(self, value: float, decimals: int = 2):
        self.measured_var.set(f"{finite_number(value):.{decimals}f}")

    def set_error(self):
        self.measured_var.set("Error")

    def get_setpoint(self) -> Optional[float]:
        """Return the current setpoint as a float, or None if not parseable."""
        try:
            return finite_number(self.setpoint_var.get())
        except (ValueError, TypeError, OverflowError, tk.TclError):
            return None

    def get_measured(self) -> Optional[float]:
        """Return the current measurement as a float, or None if not parseable."""
        try:
            return finite_number(self.measured_var.get())
        except (ValueError, TypeError, OverflowError, tk.TclError):
            return None

    def get_manual_voltage(self) -> float:
        """Map bounded percent to the configured PID output range (default 0–5 V)."""
        percent = max(0.0, min(100.0, finite_number(self.rounded_valve_position.get())))
        return self.pid.output_min + percent / 100.0 * (self.pid.output_max - self.pid.output_min)

    def sync_tuning_to_pid(self):
        """Push the current spinbox values into the PIDController object."""
        self.pid.update_tuning(
            Kc=finite_number(self.Kc_var.get()),
            Ti=finite_number(self.Ti_var.get()),
            Td=finite_number(self.Td_var.get()),
        )

    def set_valve_display(self, voltage: float):
        """Map the configured output range back to a bounded percent display."""
        span = self.pid.output_max - self.pid.output_min
        percent = max(0.0, min(100.0, (finite_number(voltage) - self.pid.output_min) / span * 100.0))
        self.valve_position.set(percent)
        self.rounded_valve_position.set(round(percent))
