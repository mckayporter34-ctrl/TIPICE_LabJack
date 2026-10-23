import time
import sys
import threading
from labjack import ljm
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from flask import Flask, request

# Shared settings; credentials stay in environment variables or a local ignored file.
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.historian_config import INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET

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
    return 0.0 if 8.475 * v <= 4.05 else min(p_max, p_min + (v - v_min) * (p_max - p_min) / (2.360 - v_min))

def hx_flowrate_gpm(v, cj):
    if v < 0.472: return 0.0
    return 0.79 + (v - 0.472) * (79.00 - 0.79) / (2.360 - 0.472)

def hx_makeup_temp(v, cj):
    return (((4 + ((v * 8.475 - 4) / 16.0) * (176 - 4))) - 32) * 5 / 9

def hx_makeup_flow(v, cj):
    return max(0.0, ((v * 8.475 - 4) / 16.0) * 6.6)

def hx_level(v, cj):
    return 0.0 if 8.475 * v <= 4.05 else min(1.96, (v - 0.472) * 1.96 / (2.360 - 0.472))

# --- CALIBRATION FUNCTIONS for CatMeth ---
def catmeth_type_k_temp(v, cj):
    def temp_to_uv(t):
        coeffs = [-1.7600413686E+01, 3.8921204975E+01, 1.8558770032E-02, -9.9457592874E-05,
                  3.1840945719E-07, -5.6072844889E-10, 5.6075059059E-13, -3.2020720003E-16,
                  9.7151147152E-20, -1.2104721275E-23]
        return sum(c * (t ** i) for i, c in enumerate(coeffs))

    tc_uv = ((v - 1.25) / 51.0) * 1e6
    tot_uv = tc_uv + temp_to_uv(cj)
    coeffs = [0.0, 2.5083550E-02, 7.8601060E-08, -2.5031310E-10, 8.3152700E-14,
              -1.2280340E-17, 9.8040360E-22, -4.4130300E-26, 1.0577340E-30, -1.0527550E-35]
    return sum(c * (tot_uv ** i) for i, c in enumerate(coeffs))

def catmeth_flow_cal(v, cj, f_min, f_max):
    slope = (f_max - f_min) / (2.3589 - 0.545)
    return max(f_min, slope * v + (f_min - slope * 0.545))

# --- CALIBRATION FUNCTIONS for Packed Column ---
def packed_water_temp(v, cj):
    return (100.0 / (2.373 - 0.477)) * v + (-20.0 - 0.477 * (100.0 / (2.373 - 0.477)))

def packed_pressure_drop(v, cj):
    return 0.0 if 8.475 * v <= 4.05 else max(0.0, (v - 0.472) / (2.360 - 0.472) * 24.9)

def packed_level(v, cj):
    return max(0.0, ((v - 0.478) / 1.896) * 703.0)

def packed_water_flow(v, cj):
    return 26.35046 * v - 12.35837

def packed_air_flow(v, cj):
    return 527.53746 * v - 250.26377


# --- MACHINE CONFIGURATIONS ---
MACHINE_CONFIGS = {
    "NNF": {
        "ip": "10.8.112.140",
        "interval": 600.0,
        "cj_register": None,
        "sensors": [
            ("AIN0", "temp_c", v_to_C_NNF),
            ("AIN1", "flow_gpm", v_to_gpm_NNF),
            ("AIN2", "pressure_wc", v_to_wc_NNF)
        ]
    },
    "Shell_and_Tube_Heat_Exchanger_1": {
        "ip": "10.8.112.12",
        "interval": 600.0,
        "cj_register": "TEMPERATURE_DEVICE_K",
        "sensors": [
            ("AIN1", "water_inlet_temp", hx_type_k_temp),
            ("AIN0", "water_outlet_temp", hx_type_k_temp),
            ("AIN8", "house_steam_pressure", lambda v, cj: hx_pressure_cal(v, cj, 0.0, 150.0, 0.479)),
            ("AIN6", "tube_side_pressure_drop", lambda v, cj: hx_pressure_cal(v, cj, 0.0, 15.0)),
            ("AIN2", "makeup_temperature", hx_makeup_temp),
            ("AIN3", "makeup_flowrate", hx_makeup_flow),
            ("AIN5", "level", hx_level),
            ("AIN4", "flowrate", hx_flowrate_gpm),
            ("AIN7", "steam_pressure", lambda v, cj: hx_pressure_cal(v, cj, 0.0, 150.0, 0.479)),
        ]
    },
    "Shell_and_Tube_Heat_Exchanger_2": {
        "ip": "10.8.112.29",
        "interval": 600.0,
        "cj_register": "TEMPERATURE_DEVICE_K",
        "sensors": [
            ("AIN1", "water_inlet_temp", hx_type_k_temp),
            ("AIN0", "water_outlet_temp", hx_type_k_temp),
            ("AIN6", "tube_side_pressure_drop", lambda v, cj: hx_pressure_cal(v, cj, 0.0, 15.0)),
            ("AIN2", "makeup_temperature", hx_makeup_temp),
            ("AIN3", "makeup_flowrate", hx_makeup_flow),
            ("AIN5", "level", hx_level),
            ("AIN4", "flowrate", hx_flowrate_gpm),
            ("AIN7", "steam_pressure", lambda v, cj: hx_pressure_cal(v, cj, 0.0, 150.0, 0.479)),
        ]
    },
    "Shell_and_Tube_Heat_Exchanger_3": {
        "ip": "10.8.112.113",
        "interval": 600.0,
        "cj_register": "TEMPERATURE_DEVICE_K",
        "sensors": [
            ("AIN1", "water_inlet_temp", hx_type_k_temp),
            ("AIN0", "water_outlet_temp", hx_type_k_temp),
            ("AIN6", "tube_side_pressure_drop", lambda v, cj: hx_pressure_cal(v, cj, 0.0, 15.0)),
            ("AIN2", "makeup_temperature", hx_makeup_temp),
            ("AIN3", "makeup_flowrate", hx_makeup_flow),
            ("AIN5", "level", hx_level),
            ("AIN4", "flowrate", hx_flowrate_gpm),
            ("AIN7", "steam_pressure", lambda v, cj: hx_pressure_cal(v, cj, 0.0, 150.0, 0.479)),
        ]
    },
    "Catalytic_Methanation_1": {
        "ip": "10.8.112.17",
        "interval": 600.0,
        "cj_register": "TEMPERATURE_DEVICE_K",
        "sensors": [
            ("AIN0", "reactor_temp_sensor", catmeth_type_k_temp),
            ("AIN2", "reactor_pressure_sensor", lambda v, cj: max(0.0, 15.8898 * v - 7.68)),
            ("AIN1", "heater_temp_sensor", catmeth_type_k_temp),
            ("AIN3", "hydrogen_actual", lambda v, cj: catmeth_flow_cal(v, cj, 0.0, 50.0)),
            ("AIN4", "co2_actual", lambda v, cj: catmeth_flow_cal(v, cj, 0.0, 10.0)),
            ("AIN5", "helium_actual", lambda v, cj: catmeth_flow_cal(v, cj, 0.0, 200.0)),
        ]
    },
    "Catalytic_Methanation_2": {
        "ip": "10.8.112.13",
        "interval": 600.0,
        "cj_register": "TEMPERATURE_DEVICE_K",
        "sensors": [
            ("AIN0", "reactor_temp_sensor", catmeth_type_k_temp),
            ("AIN2", "reactor_pressure_sensor", lambda v, cj: max(0.0, 15.8898 * v + 4.84)),
            ("AIN1", "heater_temp_sensor", catmeth_type_k_temp),
            ("AIN3", "hydrogen_actual", lambda v, cj: catmeth_flow_cal(v, cj, 0.0, 50.0)),
            ("AIN4", "co2_actual", lambda v, cj: catmeth_flow_cal(v, cj, 0.0, 10.0)),
            ("AIN5", "helium_actual", lambda v, cj: catmeth_flow_cal(v, cj, 0.0, 200.0)),
        ]
    },
    "Packed_Columns": {
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
        ]
    }
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

                point = Point("process_data").tag("unit_op", name)

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
                except:
                    pass

            time.sleep(config["interval"])

    finally:
        if handle is not None:
            ljm.close(handle)

# --- FLASK SERVER (for lab conditions from ESP32) ---
app = Flask(__name__)

@app.route('/api/readings', methods=['POST'])
def handle_esp32_input():
    try:
        data = request.get_json()

        # Mapping ESP32 JSON fields to InfluxDB Point
        point = Point("process_data") \
            .tag("unit_op", data.get('unit_op', 'lab_conditions')) \
            .field("temperature", float(data.get('temperature'))) \
            .field("pressure", float(data.get('pressure'))) \
            .time(int(time.time()), WritePrecision.S)

        write_api.write(bucket=INFLUX_BUCKET, record=point)

        # Using .get() for device_id to avoid crashes if it's missing
        device = data.get('device_id', 'unknown_esp32')
        print(f"Historian: Synced lab_conditions from {device}")
        return {"status": "success"}, 200

    except Exception as e:
        print(f"Error processing ESP32 data: {e}")
        return {"status": "error", "message": str(e)}, 400

def start_flask():
    # host='0.0.0.0' allows external devices (ESP32) to connect
    # use_reloader=False prevents double-thread issues with LabJack LJM
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# --- MAIN SERVICE ---
if __name__ == "__main__":
    try:
        # Initialize InfluxDB Client
        client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
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
                daemon=True
            )
            t.start()

        # Keep the main thread alive while background threads work
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nShutting down historian...")
    finally:
        if 'client' in locals():
            client.close()
