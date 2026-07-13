# control_loop.py
# Holds the ControlLoop dataclass — one instance per PID-controlled channel.
# Groups together all the state that was previously scattered across dozens of
# individual StringVar / DoubleVar / BooleanVar attributes on the app class.

import tkinter as tk
from dataclasses import dataclass, field
from typing import Callable, Optional

from pid_controller import PIDController


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
    extra_sensor_key  : Optional key into the sensors dict.  If provided, the
                        matching sensor's value_var is displayed inside this panel
                        (e.g. water temperature shown next to the flow control).
    """
    key:              str
    label:            str
    unit:             str
    input_pin:        str
    output_pin:       str
    calibration:      Callable[[float], float]
    setpoint_min:     float
    setpoint_max:     float
    pid:              PIDController
    extra_sensor_key: Optional[str] = None

    # ── tkinter state variables (auto-created) ────────────────────────────────
    setpoint_var:     tk.StringVar  = field(default_factory=lambda: tk.StringVar(value='0'))
    measured_var:     tk.StringVar  = field(default_factory=tk.StringVar)

    # valve_position  runs 0–100 (percent) and drives both the slider and
    # the vertical progress bar.  rounded_valve_position is the integer
    # copy kept in sync for the spinbox and the read-only entry widget.
    valve_position:         tk.DoubleVar = field(default_factory=tk.DoubleVar)
    rounded_valve_position: tk.IntVar    = field(default_factory=tk.IntVar)

    # PID tuning vars — bound to the Kc / Ti / Td spinboxes in the panel.
    Kc_var: tk.DoubleVar = field(default_factory=tk.DoubleVar)
    Ti_var: tk.DoubleVar = field(default_factory=tk.DoubleVar)
    Td_var: tk.DoubleVar = field(default_factory=tk.DoubleVar)

    # Mode flag: True = PID is active, False = operator controls slider manually.
    is_auto: bool = False

    def __post_init__(self):
        self.measured_var.set("---")
        # Seed the tuning spinboxes from the PIDController's initial values.
        self.Kc_var.set(self.pid.Kc)
        self.Ti_var.set(self.pid.Ti)
        self.Td_var.set(self.pid.Td)

    # ------------------------------------------------------------------
    # Helpers used by the update loop in app.py
    # ------------------------------------------------------------------

    def apply_calibration(self, raw_voltage: float) -> float:
        return self.calibration(raw_voltage)

    def set_measured(self, value: float, decimals: int = 2):
        self.measured_var.set(f"{value:.{decimals}f}")

    def set_error(self):
        self.measured_var.set("Error")

    def get_setpoint(self) -> Optional[float]:
        """Return the current setpoint as a float, or None if not parseable."""
        try:
            return float(self.setpoint_var.get())
        except ValueError:
            return None

    def get_measured(self) -> Optional[float]:
        """Return the current measurement as a float, or None if not parseable."""
        try:
            return float(self.measured_var.get())
        except ValueError:
            return None

    def get_manual_voltage(self) -> float:
        """Convert the 0–100 slider value to a 0–5 V output."""
        return 0.05 * self.rounded_valve_position.get()

    def sync_tuning_to_pid(self):
        """Push the current spinbox values into the PIDController object."""
        self.pid.update_tuning(
            Kc=self.Kc_var.get(),
            Ti=self.Ti_var.get(),
            Td=self.Td_var.get(),
        )

    def set_valve_display(self, voltage: float):
        """Convert a 0–5 V output back to 0–100 % for the progress bar / slider."""
        percent = voltage * 20.0      # 5 V → 100 %
        self.valve_position.set(percent)
        self.rounded_valve_position.set(round(percent))
