"""CSV and historian logging with snapshots collected on the UI thread."""

import csv
import logging
import math
import os
from datetime import datetime
from queue import Queue, Full
from threading import Thread
from time import time_ns

from core.historian_config import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET

try:
    from influxdb_client import InfluxDBClient, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS
    INFLUX_AVAILABLE = True
except ImportError:
    INFLUX_AVAILABLE = False


class DataLogger:
    """Read sources through a Tk scheduler; send plain values to the writer.

    A failed source is recorded as ``Error`` without discarding the rest of the
    row. ``numeric_sources`` identifies columns that must contain finite numbers;
    other columns may contain text (for example GC stream or heater state).
    """

    def __init__(self, sources: dict, folder: str, count_var, scheduler=None,
                 numeric_sources=(), on_error=None, *, influx_sources=None,
                 unit_op="DefaultUnit", experiment_id_var=None):
        self._sources = sources
        self._folder = folder
        self._count_var = count_var
        self._scheduler = scheduler if scheduler is not None else count_var._root
        self._numeric_sources = set(numeric_sources)
        self._on_error = on_error
        self._interval = 1.0
        self._is_logging = False
        self._thread = None
        self._capture_id = None
        self._status_id = None
        self._row_count = 0
        self.last_error = None
        self.source_errors = {}
        self.filepath = None
        self._influx_sources = influx_sources or {}
        self._unit_op = unit_op
        self._run_id_var = experiment_id_var
        self._influx_thread = None
        self.last_influx_error = None

    @property
    def is_logging(self) -> bool:
        return self._is_logging

    def set_interval(self, seconds: float):
        seconds = float(seconds)
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("Logging interval must be a finite, positive number.")
        self._interval = max(0.1, seconds)

    def start(self):
        if self._is_logging:
            return
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("The previous log file is still finishing. Try again shortly.")

        # Read the Tk variable once on the UI thread, before any workers start.
        run_id = self._run_id_var.get().strip() if self._run_id_var is not None else ""
        self._active_run_id = run_id or "Unnamed_Run"

        # Open before starting so permission/disk errors reach the GUI immediately.
        self.filepath = self._make_filepath()
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        csvfile = open(self.filepath, "x", newline="", encoding="utf-8")
        try:
            writer = csv.writer(csvfile)
            self._headers = tuple(self._sources)
            writer.writerow(["Time", *self._headers])
            csvfile.flush()
        except Exception:
            csvfile.close()
            raise

        self._queue = Queue()
        self._row_count = 0
        self.last_error = None
        self.source_errors = {}
        self.last_influx_error = None
        self._count_var.set(0)
        self._is_logging = True
        influx_queue = None
        if self._influx_sources and INFLUX_AVAILABLE and INFLUX_TOKEN:
            # A slow/unavailable historian must not stall local CSV logging.
            influx_queue = Queue(maxsize=100)
            self._influx_thread = Thread(
                target=self._run_influx, args=(influx_queue, self._active_run_id), daemon=True)
            self._influx_thread.start()
        self._thread = Thread(target=self._run, args=(csvfile, writer, self._queue, influx_queue),
                              daemon=True)
        self._thread.start()
        self._capture_row()
        self._sync_status()

    def stop(self):
        self._is_logging = False
        for attr in ("_capture_id", "_status_id"):
            callback_id = getattr(self, attr)
            if callback_id is not None:
                self._scheduler.after_cancel(callback_id)
                setattr(self, attr, None)
        if self._thread is not None and self._thread.is_alive():
            # FIFO sentinel lets the writer finish rows already captured.
            self._queue.put(None)
            self._thread.join(timeout=1.0)
        self._count_var.set(self._row_count)

    def _read_cell(self, header):
        try:
            value = self._sources[header]()
            if header in self._numeric_sources:
                if not math.isfinite(float(value)):
                    raise ValueError("non-finite numeric value")
            elif isinstance(value, (int, float)) and not math.isfinite(value):
                raise ValueError("non-finite numeric value")
            # Convert here so even a broken __str__ cannot kill the writer.
            cell = str(value) if value is not None else "Error"
            self.source_errors.pop(header, None)
            return cell
        except Exception as exc:
            error = str(exc)
            if self.source_errors.get(header) != error:
                logging.warning("DataLogger source %s: %s", header, error)
            self.source_errors[header] = error
            return "Error"

    def _capture_row(self):
        self._capture_id = None
        if not self._is_logging:
            return
        row = [datetime.now().strftime("%H:%M:%S")]
        row.extend(self._read_cell(header) for header in self._headers)
        fields = {}
        for name, source in self._influx_sources.items():
            try:
                value = float(source())
                if math.isfinite(value):
                    fields[name] = value
            except Exception:
                # Faulty historian channels must not interrupt CSV capture.
                continue
        self._queue.put((row, fields, time_ns()))
        self._capture_id = self._scheduler.after(
            round(self._interval * 1000), self._capture_row)

    def _sync_status(self):
        self._status_id = None
        self._count_var.set(self._row_count)
        if self._is_logging:
            self._status_id = self._scheduler.after(100, self._sync_status)
        elif self.last_error and self._on_error:
            self._on_error(self.last_error)

    def _run(self, csvfile, writer, queue, influx_queue):
        try:
            with csvfile:
                while True:
                    snapshot = queue.get()
                    if snapshot is None:
                        break
                    row, fields, timestamp = snapshot
                    writer.writerow(row)
                    csvfile.flush()
                    self._row_count += 1
                    if influx_queue is not None and fields:
                        try:
                            influx_queue.put_nowait((fields, timestamp))
                        except Full:
                            self.last_influx_error = "Historian backlog full; local CSV is still being saved."
        except Exception as exc:
            self.last_error = f"Could not save data to {self.filepath}: {exc}"
            logging.exception("DataLogger file write failed")
        finally:
            self._is_logging = False
            if influx_queue is not None:
                # Make room for the stop signal even during a network outage.
                while True:
                    try:
                        influx_queue.put_nowait(None)
                        break
                    except Full:
                        influx_queue.get_nowait()

    def _run_influx(self, queue, run_id):
        client = None
        try:
            client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN,
                                    org=INFLUX_ORG, timeout=2000, retries=0)
            write_api = client.write_api(write_options=SYNCHRONOUS)
            while True:
                snapshot = queue.get()
                if snapshot is None:
                    break
                fields, timestamp = snapshot
                try:
                    point = Point("process_data").tag("run_id", run_id).tag("unit_op", self._unit_op)
                    for name, value in fields.items():
                        point.field(name, value)
                    point.time(timestamp, WritePrecision.NS)
                    write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
                    self.last_influx_error = None
                except Exception as exc:
                    self.last_influx_error = str(exc)
                    logging.warning("Historian write failed; local CSV continues: %s", exc)
        except Exception as exc:
            self.last_influx_error = str(exc)
            logging.warning("Historian initialization failed; local CSV continues: %s", exc)
        finally:
            if client is not None:
                client.close()

    def _make_filepath(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return os.path.join(os.getcwd(), self._folder, f"data_log_{timestamp}.csv")
