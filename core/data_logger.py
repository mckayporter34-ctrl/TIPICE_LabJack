# data_logger.py
# Background-thread CSV and InfluxDB data logger.

import csv
import os
import time
from datetime import datetime
from threading import Thread, Event

try:
    from influxdb_client import InfluxDBClient, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS
    INFLUX_AVAILABLE = True
except ImportError:
    INFLUX_AVAILABLE = False
    print("[Warning] influxdb_client not found — historian logging disabled.")

# --- INFLUXDB CONFIGURATION ---
INFLUX_URL = "http://10.5.112.172:8086"
INFLUX_TOKEN = "m4BUDV1JRzGaAq7Y6jF-f5i6z3qMD5cnwWA6nwPubak9h4WoO1qxE6qAdgAc5e_EoUqWgzxSpXfSvGVsppGrCA==" 
INFLUX_ORG = "BYUChemE"
INFLUX_BUCKET = "UOLab"


class DataLogger:
    """
    Writes sensor readings to a timestamped CSV file and pushes them to InfluxDB
    in a background thread.
    """

    def __init__(self, sources: dict, influx_sources: dict, folder: str, count_var, unit_op: str, experiment_id_var):
        self._sources        = sources          # {header: callable} for CSV
        self._influx_sources = influx_sources   # {field_name: callable} for InfluxDB
        self._folder         = folder
        self._count_var      = count_var
        self._unit_op        = unit_op
        self._run_id_var     = experiment_id_var

        self._is_logging  = False
        self._stop_event  = Event()
        self._interval    = 1.0

        # Initialize InfluxDB Client if available
        self._influx_client = None
        self._write_api = None
        if INFLUX_AVAILABLE:
            try:
                self._influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
                self._write_api = self._influx_client.write_api(write_options=SYNCHRONOUS)
            except Exception as e:
                print(f"[DataLogger] InfluxDB Connection Initialization Error: {e}")

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
        
        # Capture current Experiment ID value upon start
        self._active_run_id = self._run_id_var.get().strip() or "Unnamed_Run"
        
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
                
                # 1. Write Local CSV (Preserve 100% original functionality)
                row = [timestamp] + [fn() for fn in self._sources.values()]
                writer.writerow(row)
                csvfile.flush()

                # 2. Push to InfluxDB Historian
                if self._write_api:
                    try:
                        point = Point("process_data") \
                            .tag("run_id", self._active_run_id) \
                            .tag("unit_op", self._unit_op)

                        has_valid_fields = False
                        for field_name, fn in self._influx_sources.items():
                            val_str = fn()
                            if val_str not in ("---", "Error", "", None):
                                try:
                                    numeric_val = float(val_str)
                                    point.field(field_name, numeric_val)
                                    has_valid_fields = True
                                except (ValueError, TypeError):
                                    pass

                        if has_valid_fields:
                            self._write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
                    except Exception as e:
                        print(f"[DataLogger] InfluxDB Write Error: {e}")

                self._count_var.set(self._count_var.get() + 1)
                time.sleep(self._interval)

        print(f"[DataLogger] Logging stopped. Data saved to: {filepath}")

    def _make_filepath(self) -> str:
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename   = f"data_log_{timestamp}.csv"
        cwd = os.getcwd()
        return os.path.join(cwd, self._folder, filename)