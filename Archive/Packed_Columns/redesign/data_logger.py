# data_logger.py
# Background-thread CSV data logger.

import csv
import os
import time
from datetime import datetime
from threading import Thread, Event

class DataLogger:
    """
    Writes sensor readings to a timestamped CSV file in a background thread.
    """

    def __init__(self, sources: dict, folder: str, count_var):
        self._sources   = sources       # {header: callable}
        self._folder    = folder
        self._count_var = count_var

        self._is_logging  = False
        self._stop_event  = Event()
        self._interval    = 1.0         # seconds between rows; caller may set this

    @property
    def is_logging(self) -> bool:
        return self._is_logging

    def set_interval(self, seconds: float):
        self._interval = max(0.1, float(seconds))

    def start(self):
        if self._is_logging:
            return
        self._is_logging = True
        self._stop_event.clear()
        self._count_var.set(0)
        Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._is_logging = False
        self._stop_event.set()

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
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, self._folder, filename)
