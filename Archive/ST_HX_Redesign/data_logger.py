# data_logger.py
# Background-thread CSV data logger.
#
# DataLogger knows nothing about specific sensors or column names — it
# receives those at construction time via the `sources` dict, which maps
# a CSV column header to a callable that returns the current string value.
# Adding or removing logged channels means only editing config.py, not
# touching any logger code.

import csv
import os
import time
from datetime import datetime
from threading import Thread, Event


class DataLogger:
    """
    Writes sensor readings to a timestamped CSV file in a background thread.

    Parameters
    ----------
    sources   : Ordered dict mapping CSV column header → callable() → str.
                Example:
                    {
                        "Water Temp (C)":    lambda: sensors["water_temperature"].value_var.get(),
                        "Air Flow (SLPM)":   lambda: sensors["air_flowrate"].value_var.get(),
                    }
    folder    : Directory name where CSV files are saved (relative to working directory).
                Created automatically if it does not exist.
    count_var : tkinter IntVar updated with the running row count so the GUI
                can display it live without any extra coupling.
    """

    def __init__(self, sources: dict, folder: str, count_var):
        self._sources   = sources       # {header: callable}
        self._folder    = folder
        self._count_var = count_var

        self._is_logging  = False
        self._stop_event  = Event()
        self._interval    = 1.0         # seconds between rows; caller may set this

    # ------------------------------------------------------------------
    # Public API called by the GUI toggle button
    # ------------------------------------------------------------------

    @property
    def is_logging(self) -> bool:
        return self._is_logging

    def set_interval(self, seconds: float):
        """Update the logging interval (takes effect on the next sleep cycle)."""
        self._interval = max(0.1, float(seconds))

    def start(self):
        """Start logging in a daemon background thread."""
        if self._is_logging:
            return
        self._is_logging = True
        self._stop_event.clear()
        self._count_var.set(0)
        Thread(target=self._run, daemon=True).start()

    def stop(self):
        """Signal the logging thread to finish and exit."""
        self._is_logging = False
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Background thread
    # ------------------------------------------------------------------

    def _run(self):
        filepath = self._make_filepath()
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        headers = ["Time"] + list(self._sources.keys())

        with open(filepath, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)

            while not self._stop_event.is_set():
                timestamp = datetime.now().strftime("%H:%M:%S")
                row = [timestamp] + [fn() for fn in self._sources.values()]
                writer.writerow(row)
                csvfile.flush()                       # write to disk immediately
                self._count_var.set(self._count_var.get() + 1)
                time.sleep(self._interval)

        print(f"[DataLogger] Logging stopped. Data saved to: {filepath}")

    def _make_filepath(self) -> str:
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename   = f"data_log_{timestamp}.csv"
        # Save in the folder relative to the current working directory (e.g. project root)
        cwd = os.getcwd()
        return os.path.join(cwd, self._folder, filename)
