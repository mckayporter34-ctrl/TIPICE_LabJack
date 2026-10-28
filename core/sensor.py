# sensor.py
# Holds the Sensor dataclass — one instance per read-only sensor channel.
# The GUI, logger, and update loop all reference these objects instead of
# scattered individual StringVar / pin-name pairs on the app class.

import math
import tkinter as tk
from dataclasses import dataclass, field
from time import monotonic
from typing import Callable
from core.numeric_entry import finite_number


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
    filter_time_constant_s : Exponential filter time constant in seconds.
                   Zero (the default) leaves readings unfiltered.
    raw_value    : Latest calibrated, unfiltered engineering value, or None
                   before a valid sample and after a read error or reset.
    """
    key:         str
    label:       str
    unit:        str
    pin:         str
    calibration: Callable[[float], float]

    # Display variable and optional smoothing configuration.
    value_var: tk.StringVar = field(default_factory=tk.StringVar)
    filter_time_constant_s: float = 0.0
    raw_value: float | None = field(default=None, init=False)
    _filtered_value: float | None = field(default=None, init=False, repr=False)
    _last_sample_time: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.filter_time_constant_s = finite_number(self.filter_time_constant_s)
        if self.filter_time_constant_s < 0:
            raise ValueError("Filter time constant must be nonnegative.")
        self.reset()

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
        """Store the unfiltered reading and optionally smooth the displayed value.

        The filter uses monotonic sample times, independently of the log interval.
        Its first valid sample initializes the output without a startup ramp.
        """
        value = finite_number(engineering_value)
        filtered = value
        if self.filter_time_constant_s > 0:
            now = monotonic()
            if self._last_sample_time is not None:
                dt = max(0.0, now - self._last_sample_time)
                alpha = -math.expm1(-dt / self.filter_time_constant_s)
                filtered = self._filtered_value + alpha * (value - self._filtered_value)
            self._last_sample_time = now
        self.raw_value = value
        self._filtered_value = filtered
        self.value_var.set(f"{filtered:.{decimals}f}")

    def get_raw_value(self) -> float:
        """Return the latest calibrated, unfiltered reading for logging."""
        if self.raw_value is None:
            raise ValueError("No valid sensor reading.")
        return self.raw_value

    def reset(self):
        """Clear readings and filter history before a new connection or sample."""
        self.raw_value = None
        self._filtered_value = None
        self._last_sample_time = None
        self.value_var.set("---")

    def set_error(self):
        """Push an error marker into value_var (channel unread / disconnected)."""
        self.reset()
        self.value_var.set("Error")
