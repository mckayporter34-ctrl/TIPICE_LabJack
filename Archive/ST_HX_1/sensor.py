# sensor.py
# Holds the Sensor dataclass — one instance per read-only sensor channel.
# The GUI, logger, and update loop all reference these objects instead of
# scattered individual StringVar / pin-name pairs on the app class.

import tkinter as tk
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Sensor:
    """
    Represents a single read-only sensor channel.

    Attributes
    ----------
    key          : Unique identifier string matching the key in SENSOR_CONFIGS.
    label        : Human-readable display name (e.g. "Water Temp").
    unit         : Engineering unit string shown in the GUI (e.g. "°C").
    pin          : LabJack register name to read from (e.g. "AIN6").
                   Set to "" to mark the channel as unassigned; the display
                   will show "Error" until a real pin is provided.
    calibration  : Callable that converts a raw voltage (float) to the
                   engineering value (float).
    value_var    : tkinter StringVar holding the latest formatted reading.
                   Widgets bind directly to this — no polling needed in the UI.
    """
    key:         str
    label:       str
    unit:        str
    pin:         str
    calibration: Callable[[float], float]

    # Created automatically — no need to pass these in.
    value_var: tk.StringVar = field(default_factory=tk.StringVar)

    def __post_init__(self):
        self.value_var.set("---")

    # ------------------------------------------------------------------
    # Convenience helpers used by the update loop in app.py
    # ------------------------------------------------------------------

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
        """Push an error marker into value_var (channel unread / disconnected)."""
        self.value_var.set("Error")
