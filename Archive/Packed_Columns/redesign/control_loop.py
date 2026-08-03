# control_loop.py
# Holds the ControlLoop dataclass — one instance per PID-controlled channel.

import tkinter as tk
from dataclasses import dataclass, field
from typing import Callable, Optional

from pid_controller import PIDController

@dataclass
class ControlLoop:
    """
    Represents one closed-loop PID control channel.
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

    # tkinter state variables
    setpoint_var:     tk.StringVar  = field(default_factory=lambda: tk.StringVar(value='0'))
    measured_var:     tk.StringVar  = field(default_factory=tk.StringVar)
    valve_position:         tk.DoubleVar = field(default_factory=tk.DoubleVar)
    rounded_valve_position: tk.IntVar    = field(default_factory=tk.IntVar)
    Kc_var: tk.DoubleVar = field(default_factory=tk.DoubleVar)
    Ti_var: tk.DoubleVar = field(default_factory=tk.DoubleVar)
    Td_var: tk.DoubleVar = field(default_factory=tk.DoubleVar)

    is_auto: bool = False

    def __post_init__(self):
        self.measured_var.set("---")
        self.Kc_var.set(self.pid.Kc)
        self.Ti_var.set(self.pid.Ti)
        self.Td_var.set(self.pid.Td)

    def apply_calibration(self, raw_voltage: float) -> float:
        return self.calibration(raw_voltage)

    def set_measured(self, value: float, decimals: int = 2):
        self.measured_var.set(f"{value:.{decimals}f}")

    def set_error(self):
        self.measured_var.set("Error")

    def get_setpoint(self) -> Optional[float]:
        try:
            return float(self.setpoint_var.get())
        except ValueError:
            return None

    def get_measured(self) -> Optional[float]:
        try:
            return float(self.measured_var.get())
        except ValueError:
            return None

    def get_manual_voltage(self) -> float:
        return 0.05 * self.rounded_valve_position.get()

    def sync_tuning_to_pid(self):
        self.pid.update_tuning(
            Kc=self.Kc_var.get(),
            Ti=self.Ti_var.get(),
            Td=self.Td_var.get(),
        )

    def set_valve_display(self, voltage: float):
        percent = voltage * 20.0
        self.valve_position.set(percent)
        self.rounded_valve_position.set(round(percent))
