import sys
import threading
import time
import math
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.runtime import require_python
require_python()
from flask import Flask, request
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from labjack import ljm

from core.historian_config import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET
from core.unit_ops import HISTORIAN_UNIT_OP_MAP

# --- CALIBRATION FUNCTIONS for NNF ---
def v_to_C_NNF(v, cj=None):
    return round(((55.28745157 * v) - 48.08422656), 2)


def v_to_gpm_NNF(v, cj=None):
    return round((((53.2187707 * v) - 25.35572892) * 0.264172), 2)


def v_to_wc_NNF(v, cj=None):
    return round(((3.125 * 8.475 * v) - 12.5), 2)


# --- CALIBRATION FUNCTIONS for ST_HX ---
def hx_type_k_temp(v, cj):
    return cj + ((v - 1.25) / 51.0) / 41.276e-6


def hx_pressure_cal(v, cj, p_min, p_max, v_min=0.472):
    return (
        0.0
        if 8.475 * v <= 4.05
        else min(p_max, p_min + (v - v_min) * (p_max - p_min) / (2.360 - v_min))
    )


def hx_flowrate_gpm(v, cj):
    if v < 0.472:
        return 0.0
    return 0.79 + (v - 0.472) * (79.00 - 0.79) / (2.360 - 0.472)


def hx_makeup_temp(v, cj):
    return (((4 + ((v * 8.475 - 4) / 16.0) * (176 - 4))) - 32) * 5 / 9


def hx_makeup_flow(v, cj):
    return max(0.0, ((v * 8.475 - 4) / 16.0) * 6.6)


def hx_level(v, cj):
    return (
        0.0
        if 8.475 * v <= 4.05
        else min(1.96, (v - 0.472) * 1.96 / (2.360 - 0.472))
    )


# --- CALIBRATION FUNCTIONS for CatMeth ---
def catmeth_type_k_temp(v, cj):
    def temp_to_uv(t):
        coeffs = [
            -1.7600413686e01,
            3.8921204975e01,
            1.8558770032e-02,
            -9.9457592874e-05,
            3.1840945719e-07,
            -5.6072844889e-10,
            5.6075059059e-13,
            -3.2020720003e-16,
            9.7151147152e-20,
            -1.2104721275e-23,
        ]
        return sum(c * (t**i) for i, c in enumerate(coeffs))

    tc_uv = ((v - 1.25) / 51.0) * 1e6
    tot_uv = tc_uv + temp_to_uv(cj)
    coeffs = [
        0.0,
        2.5083550e-02,
        7.8601060e-08,
        -2.5031310e-10,
        8.3152700e-14,
        -1.2280340e-17,
        9.8040360e-22,
        -4.4130300e-26,
        1.0577340e-30,
        -1.0527550e-35,
    ]
    return sum(c * (tot_uv**i) for i, c in enumerate(coeffs))


def catmeth_flow_cal(v, cj, f_min, f_max):
    slope = (f_max - f_min) / (2.3589 - 0.545)
    return max(f_min, slope * v + (f_min - slope * 0.545))


# --- CALIBRATION FUNCTIONS for Packed Column ---
def packed_water_temp(v, cj):
    return (100.0 / (2.373 - 0.477)) * v + (
        -20.0 - 0.477 * (100.0 / (2.373 - 0.477))
    )


def packed_pressure_drop(v, cj):
    return (
        0.0
        if 8.475 * v <= 4.05
        else max(0.0, (v - 0.472) / (2.360 - 0.472) * 24.9)
    )


def packed_level(v, cj):
    return max(0.0, ((v - 0.478) / 1.896) * 703.0)


def packed_water_flow(v, cj):
    return 26.35046 * v - 12.35837


def packed_air_flow(v, cj):
    return 527.53746 * v - 250.26377


# --- MACHINE CONFIGURATIONS ---
MACHINE_CONFIGS = {
    "NNF1": {
        "ip": "10.8.112.140",
        "interval": 600.0,
        "cj_register": None,
        "sensors": [
            ("AIN0", "temp_c", v_to_C_NNF),
            ("AIN1", "flow_gpm", v_to_gpm_NNF),
            ("AIN2", "pressure_wc", v_to_wc_NNF),
        ],
    },
    "STHX1": {
        "ip": "10.8.112.12",
        "interval": 600.0,
        "cj_register": "TEMPERATURE_DEVICE_K",
        "sensors": [
            ("AIN1", "water_inlet_temp", hx_type_k_temp),
            ("AIN0", "water_outlet_temp", hx_type_k_temp),
            (
                "AIN8",
                "house_steam_pressure",
                lambda v, cj: hx_pressure_cal(v, cj, 0.0, 150.0, 0.479),
            ),
            (
                "AIN6",
                "tube_side_pressure_drop",
                lambda v, cj: hx_pressure_cal(v, cj, 0.0, 15.0),
            ),
            ("AIN2", "makeup_temperature", hx_makeup_temp),
            ("AIN3", "makeup_flowrate", hx_makeup_flow),
            ("AIN5", "level", hx_level),
            ("AIN4", "flowrate", hx_flowrate_gpm),
            (
                "AIN7",
                "steam_pressure",
                lambda v, cj: hx_pressure_cal(v, cj, 0.0, 150.0, 0.479),
            ),
        ],
    },
    "STHX2": {
        "ip": "10.8.112.29",
        "interval": 600.0,
        "cj_register": "TEMPERATURE_DEVICE_K",
        "sensors": [
            ("AIN1", "water_inlet_temp", hx_type_k_temp),
            ("AIN0", "water_outlet_temp", hx_type_k_temp),
            (
                "AIN6",
                "tube_side_pressure_drop",
                lambda v, cj: hx_pressure_cal(v, cj, 0.0, 15.0),
            ),
            ("AIN2", "makeup_temperature", hx_makeup_temp),
            ("AIN3", "makeup_flowrate", hx_makeup_flow),
            ("AIN5", "level", hx_level),
            ("AIN4", "flowrate", hx_flowrate_gpm),
            (
                "AIN7",
                "steam_pressure",
                lambda v, cj: hx_pressure_cal(v, cj, 0.0, 150.0, 0.479),
            ),
        ],
    },
    "STHX3": {
        "ip": "10.8.112.113",
        "interval": 600.0,
        "cj_register": "TEMPERATURE_DEVICE_K",
        "sensors": [
            ("AIN1", "water_inlet_temp", hx_type_k_temp),
            ("AIN0", "water_outlet_temp", hx_type_k_temp),
            (
                "AIN6",
                "tube_side_pressure_drop",
                lambda v, cj: hx_pressure_cal(v, cj, 0.0, 15.0),
            ),
            ("AIN2", "makeup_temperature", hx_makeup_temp),
            ("AIN3", "makeup_flowrate", hx_makeup_flow),
            ("AIN5", "level", hx_level),
            ("AIN4", "flowrate", hx_flowrate_gpm),
            (
                "AIN7",
                "steam_pressure",
                lambda v, cj: hx_pressure_cal(v, cj, 0.0, 150.0, 0.479),
            ),
        ],
    },
    "CatMeth1": {
        "ip": "10.8.112.17",
        "interval": 600.0,
        "cj_register": "TEMPERATURE_DEVICE_K",
        "sensors": [
            ("AIN0", "reactor_temp_sensor", catmeth_type_k_temp),
            (
                "AIN2",
                "reactor_pressure_sensor",
                lambda v, cj: max(0.0, 15.8898 * v - 7.68),
            ),
            ("AIN1", "heater_temp_sensor", catmeth_type_k_temp),
            (
                "AIN3",
                "hydrogen_actual",
                lambda v, cj: catmeth_flow_cal(v, cj, 0.0, 50.0),
            ),
            (
                "AIN4",
                "co2_actual",
                lambda v, cj: catmeth_flow_cal(v, cj, 0.0, 10.0),
            ),
            (
                "AIN5",
                "helium_actual",
                lambda v, cj: catmeth_flow_cal(v, cj, 0.0, 200.0),
            ),
        ],
    },
    "CatMeth2": {
        "ip": "10.8.112.13",
        "interval": 600.0,
        "cj_register": "TEMPERATURE_DEVICE_K",
        "sensors": [
            ("AIN0", "reactor_temp_sensor", catmeth_type_k_temp),
            (
                "AIN2",
                "reactor_pressure_sensor",
                lambda v, cj: max(0.0, 15.8898 * v + 4.84),
            ),
            ("AIN1", "heater_temp_sensor", catmeth_type_k_temp),
            (
                "AIN3",
                "hydrogen_actual",
                lambda v, cj: catmeth_flow_cal(v, cj, 0.0, 50.0),
            ),
            (
                "AIN4",
                "co2_actual",
                lambda v, cj: catmeth_flow_cal(v, cj, 0.0, 10.0),
            ),
            (
                "AIN5",
                "helium_actual",
                lambda v, cj: catmeth_flow_cal(v, cj, 0.0, 200.0),
            ),
        ],
    },
    "PC": {
        "ip": "10.8.112.59",
        "interval": 600.0,
        "cj_register": None,
        "sensors": [
            ("AIN0", "air_flowrate", packed_air_flow),
            ("AIN6", "water_temperature", packed_water_temp),
            ("AIN2", "column1_pressure_drop", packed_pressure_drop),
            ("AIN3", "column2_pressure_drop", packed_pressure_drop),
            ("AIN1", "water_flow", packed_water_flow),
            ("AIN4", "column1_level", packed_level),
            ("AIN5", "column2_level", packed_level),
        ],
    },
}

# --- LABJACK POLLING LOGIC ---
def run_historian_for_machine(name, config, write_api):
    print(f"[{name}] Thread started. Target IP: {config['ip']}")
    handle = None
    try:
        handle = ljm.openS("ANY", "TCP", config["ip"])
        while True:
            try:
                # Default cold junction temp (used if none provided by labjack)
                cj_temp = 25.0
                # Update cold junction if needed by the config
                cj_register = config.get("cj_register")
                if cj_register:
                    try:
                        cj_k = ljm.eReadName(handle, cj_register)
                        cj_temp = cj_k - 273.15
                    except Exception as e:
                        print(f"[{name}] CJ update error: {e}")

                point = Point("process_data").tag("unit_op", HISTORIAN_UNIT_OP_MAP.get(name, name))
                for register, label, func in config["sensors"]:
                    val_volt = ljm.eReadName(handle, register)
                    calibrated_val = func(val_volt, cj_temp)
                    point.field(label, calibrated_val)

                point.time(int(time.time()), WritePrecision.S)
                write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
                print(f"[{name}] Data synced. Next sample in {config['interval']}s")

            except Exception as e:
                print(f"[{name}] Connection error: {e}")
                try:
                    ljm.close(handle)
                    handle = ljm.openS("ANY", "TCP", config["ip"])
                except Exception:
                    pass

            time.sleep(config["interval"])

    finally:
        if handle is not None:
            ljm.close(handle)

# --- FLASK SERVER (for lab conditions from ESP32 & Checkout Management) ---
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
write_api = None

# Global state for machine checkouts
# Format: { 'unit_op_name': {'student_id': '...', 'last_seen': float} }
active_sessions = {}
session_lock = threading.Lock()
SESSION_TIMEOUT = 15  # Seconds before an unresponsive lock is cleared
STUDENTS_FILE = Path(os.environ.get("HISTORIAN_STUDENTS_FILE", Path(__file__).with_name("students.txt")))

def is_valid_student(student_id):
    try:
        with open(STUDENTS_FILE, "r") as f:
            valid_ids = [line.strip() for line in f.readlines()]
        return student_id in valid_ids
    except FileNotFoundError:
        print("Historian: students.txt not found. Denying all logins.")
        return False

def clean_stale_sessions():
    """Removes sessions that have not sent a heartbeat ping recently."""
    now = time.monotonic()
    stale = [uo for uo, data in active_sessions.items() if now - data['last_seen'] > SESSION_TIMEOUT]
    for uo in stale:
        del active_sessions[uo]
        print(f"Historian: {uo} lock expired due to timeout")

@app.route("/checkout", methods=["POST"])
def checkout_machine():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"status": "error", "message": "Expected a JSON object"}, 400
    student_id = data.get("student_id")
    unit_op = data.get("unit_op")
    force = data.get("force", False)

    if (not isinstance(student_id, str) or not student_id.strip() or
            not isinstance(unit_op, str) or not unit_op.strip() or not isinstance(force, bool)):
        return {"status": "error", "message": "Missing student_id or unit_op"}, 400

    if not is_valid_student(student_id):
        return {"status": "error", "message": "Invalid Student ID"}, 403

    with session_lock:
        clean_stale_sessions()
        current_data = active_sessions.get(unit_op)
        current_user = current_data['student_id'] if current_data else None

        # Deny if locked by someone else and not forced
        if current_user and current_user != student_id and not force:
            return {
                "status": "error",
                "message": f"Machine in use by {current_user}",
                "current_user": current_user
            }, 409

        # Grant, renew, or force override
        active_sessions[unit_op] = {'student_id': student_id, 'last_seen': time.monotonic()}
        action = "forcefully locked" if (current_user and current_user != student_id and force) else "locked"
        print(f"Historian: {unit_op} {action} by {student_id}")

    return {"status": "success", "message": "Lock granted"}, 200

@app.route("/release", methods=["POST"])
def release_machine():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"status": "error", "message": "Expected a JSON object"}, 400
    unit_op = data.get("unit_op")
    student_id = data.get("student_id")

    if not isinstance(unit_op, str) or not unit_op or not isinstance(student_id, str) or not student_id:
        return {"status": "error", "message": "Missing unit_op or student_id"}, 400

    with session_lock:
        clean_stale_sessions()
        current_data = active_sessions.get(unit_op)

        # Only release if the requester is the actual owner
        if current_data and current_data['student_id'] == student_id:
            del active_sessions[unit_op]
            print(f"Historian: {unit_op} released by {student_id}")
        else:
            print(f"Historian: Ignored release for {unit_op} from {student_id} (not active owner)")

    return {"status": "success", "message": "Processed"}, 200

@app.route("/status", methods=["POST"])
def check_status():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"status": "error", "message": "Expected a JSON object"}, 400
    unit_op = data.get("unit_op")
    student_id = data.get("student_id")

    if not isinstance(unit_op, str) or not unit_op:
        return {"status": "error", "message": "Missing unit_op"}, 400

    with session_lock:
        clean_stale_sessions()
        current_data = active_sessions.get(unit_op)
        current_user = current_data['student_id'] if current_data else None

        # If the active owner is the one checking status, update their heartbeat
        if current_user and current_user == student_id:
            active_sessions[unit_op]['last_seen'] = time.monotonic()

    return {"status": "success", "current_user": current_user}, 200

@app.route("/api/time", methods=["GET"])
def server_time():
    return {"server_time_ns": time.time_ns()}, 200


@app.route("/api/process-data", methods=["POST"])
def handle_process_data():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"message": "Expected a JSON object"}, 400
    unit_op, student_id, run_id = (data.get(key) for key in ("unit_op", "student_id", "run_id"))
    if any(not isinstance(value, str) or not value.strip() or len(value) > 512
           or "\n" in value or "\r" in value for value in (unit_op, student_id, run_id)):
        return {"message": "Invalid unit_op, student_id or run_id"}, 400
    fields = data.get("fields")
    timestamp = data.get("timestamp_ns")
    if not isinstance(fields, dict) or not fields or len(fields) > 256:
        return {"message": "Expected 1 to 256 numeric fields"}, 400
    if type(timestamp) is not int or not 0 < timestamp < 9223372036854775807:
        return {"message": "Invalid nanosecond timestamp"}, 400
    point = Point("process_data").tag("unit_op", unit_op).tag("run_id", run_id)
    for name, value in fields.items():
        if (not isinstance(name, str) or not name or len(name) > 128 or
                name in ("time", "_field", "_measurement") or "\n" in name or "\r" in name or
                type(value) not in (int, float)):
            return {"message": "Invalid field name or numeric value"}, 400
        try:
            value = float(value)
        except (OverflowError, ValueError):
            return {"message": "Numeric values must be finite"}, 400
        if not math.isfinite(value):
            return {"message": "Numeric values must be finite"}, 400
        point.field(name, value)
    point.time(timestamp, WritePrecision.NS)
    # Keep ownership validation and submission atomic with respect to overrides.
    # Uploading does not renew the heartbeat; /status owns session liveness.
    with session_lock:
        clean_stale_sessions()
        owner = active_sessions.get(unit_op)
        if not owner or owner["student_id"] != student_id:
            return {"message": "No active session owned by this student"}, 403
        if write_api is None:
            return {"message": "Database writer is not initialized"}, 503
        try:
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        except Exception:
            app.logger.exception("Process data write failed")
            return {"message": "Database write failed; local CSV should be retained"}, 503
    return {"status": "success"}, 200


@app.route("/api/readings", methods=["POST"])
def handle_esp32_input():
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not data:
            return {"status": "error", "message": "Missing JSON body"}, 400

        point = (
            Point("process_data")
            .tag("unit_op", data.get("unit_op", "lab_conditions"))
            .field("temperature", float(data.get("temperature", 0.0)))
            .field("pressure", float(data.get("pressure", 0.0)))
            .time(int(time.time()), WritePrecision.S)
        )

        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        device = data.get("device_id", "unknown_esp32")
        print(f"Historian: Synced lab_conditions from {device}")
        return {"status": "success"}, 200

    except Exception as e:
        print(f"Error processing ESP32 data: {e}")
        return {"status": "error", "message": str(e)}, 400

def start_flask():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

# --- MAIN SERVICE ---
if __name__ == "__main__":
    client = None
    try:
        # Initialize InfluxDB Client
        if not INFLUX_TOKEN:
            raise RuntimeError("Set INFLUX_TOKEN in the environment or .historian.local.json")
        client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG,
                                timeout=2000, retries=0)
        write_api = client.write_api(write_options=SYNCHRONOUS)

        # 1. Start the Flask API thread for the ESP32
        api_thread = threading.Thread(target=start_flask, daemon=True)
        api_thread.start()
        print("Historian: API Listener started on port 5000")

        # 2. Start LabJack threads for each configured machine
        for machine_name, m_config in MACHINE_CONFIGS.items():
            t = threading.Thread(
                target=run_historian_for_machine,
                args=(machine_name, m_config, write_api),
                daemon=True,
            )
            t.start()

        # Keep the main thread alive while background threads work
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nShutting down historian...")
    finally:
        if client is not None:
            client.close()
