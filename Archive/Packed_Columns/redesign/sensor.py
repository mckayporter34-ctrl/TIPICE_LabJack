# sensor.py
# Holds the Sensor dataclass — one instance per read-only sensor channel.

import tkinter as tk
from dataclasses import dataclass, field
from typing import Callable

@dataclass
class Sensor:
    """
    Represents a single read-only sensor channel.
    """
    key:         str
    label:       str
    unit:        str
    pin:         str
    calibration: Callable[[float], float]

    # Created automatically
    value_var: tk.StringVar = field(default_factory=tk.StringVar)

    def __post_init__(self):
        self.value_var.set("---")

    def is_configured(self) -> bool:
        """Return True if a real pin is assigned."""
        return bool(self.pin)

    def apply_calibration(self, raw_voltage: float) -> float:
        """Run the calibration lambda and return the engineering value."""
        return self.calibration(raw_voltage)

    def set_value(self, engineering_value: float, decimals: int = 2):
        """Format and push a new reading into value_var."""
        self.value_var.set(f"{engineering_value:.{decimals}f}")

    def set_error(self):
        """Push an error marker into value_var."""
        self.value_var.set("Error")
