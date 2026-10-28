"""Air Flow Meters (CB217A-Peter).

Channel assignments and engineering ranges: Development/New_system_implementation.xlsx,
AIRFLOW, rows 3–44. See docs/airflow.md for commissioning assumptions.
"""

from pathlib import Path

from apps.airflow import AirflowFrame
from core.numeric_entry import finite_number

FrameClass = AirflowFrame
SYSTEM_NAME = "Air Flow Meters"
DEVICE_MANAGER_ENABLED = False  # Development system: connect without student checkout.
LOGO_FILE = str(Path(__file__).resolve().parents[1] / "assets" / "tipice_logo.png")
LOG_FOLDER = "AirFlow_LoggedData"
PID_IMAGE = str(Path(__file__).resolve().parents[1] / "PI diagrams" / "AirFlow_PID_V1.png")

# No relay or network address is supplied in the implementation workbook.
# Control Enable gates the valve output in software; it does not start the blower.
MAIN_POWER_PIN = ""
CONNECT_ENABLES_CONTROLS = True
ETHERNET_ADDRESS = ""
SYSTEM_SWITCHES = []

# Same InAmp3 gain used by the existing laboratory controllers. Verify fitted gain.
INAMP_GAIN = 51.0
INAMP_OFFSET_V = 1.25
COLD_JUNCTION_REGISTER = "TEMPERATURE_DEVICE_K"
_cj_temp_c = [float("nan")]


def _type_t_temp(amp_voltage_v):
    # LJM's Type T conversion includes nonlinear cold-junction compensation.
    # Import lazily so the GUI also opens on computers without the LJM driver.
    from labjack import ljm

    tc_v = (finite_number(amp_voltage_v) - INAMP_OFFSET_V) / INAMP_GAIN
    cj_k = finite_number(_cj_temp_c[0]) + 273.15
    return ljm.tcVoltsToTemp(6008, tc_v, cj_k) - 273.15


# LJTick-CurrentShunt: 4–20 mA -> 0.472–2.360 V (118 mV/mA).
CURRENT_V_MIN = 0.472
CURRENT_V_MAX = 2.360


def _current_cal(full_scale):
    def convert(voltage):
        # Preserve small negative/overrange readings instead of hiding them.
        return (finite_number(voltage) - CURRENT_V_MIN) * full_scale / (CURRENT_V_MAX - CURRENT_V_MIN)
    return convert


SENSOR_CONFIGS = {
    **{
        f"temperature_{i + 1}": {
            "label": f"Temperature {i + 1}", "unit": "°C", "pin": f"AIN{i}",
            "calibration": _type_t_temp,
        }
        for i in range(4)
    },
    "pitot_delta_p": {
        "label": "Pitot ΔP", "unit": "in WC", "pin": "AIN4", "calibration": _current_cal(2.5),
    },
    "pitot_entrance_pressure": {
        "label": "Pitot", "unit": "psi", "pin": "AIN5", "calibration": _current_cal(2.0),
    },
    "nozzle_delta_p": {
        "label": "Nozzle ΔP", "unit": "in WC", "pin": "AIN6", "calibration": _current_cal(10.0),
    },
    "nozzle_entrance_pressure": {
        "label": "Nozzle", "unit": "psi", "pin": "AIN7", "calibration": _current_cal(2.0),
    },
    "orifice_delta_p": {
        "label": "Orifice ΔP", "unit": "psi", "pin": "AIN8", "calibration": _current_cal(1.0),
    },
    "orifice_entrance_pressure": {
        "label": "Orifice", "unit": "psi", "pin": "AIN9", "calibration": _current_cal(2.0),
    },
    "rotameter_entrance_pressure": {
        "label": "Rotameter", "unit": "psi", "pin": "AIN10", "calibration": _current_cal(2.0),
    },
    "venturi_delta_p": {
        "label": "Venturi ΔP", "unit": "psi", "pin": "AIN12", "calibration": _current_cal(2.0),
    },
    "venturi_entrance_pressure": {
        "label": "Venturi", "unit": "psi", "pin": "AIN13", "calibration": _current_cal(2.0),
    },
}

CONTROL_LOOP_CONFIGS = {
    "flowrate": {
        "label": "Air Flow Control", "unit": "SCFM",
        "input_pin": "AIN11", "output_pin": "DAC0", "calibration": _current_cal(350.0),
        "setpoint_min": 0.0, "setpoint_max": 350.0, "default_setpoint": 80.0,
        "pid_defaults": {"Kc": -0.005, "Ti": 0.05, "Td": 0.0},
    },
}

AIN_CONFIGS = {
    f"AIN{i}": {"NEGATIVE_CH": 199, "RANGE": 10.0, "RESOLUTION_INDEX": 8 if i < 4 else 1}
    for i in range(14)
}

DELTA_P_KEYS = ("pitot_delta_p", "venturi_delta_p", "nozzle_delta_p", "orifice_delta_p")
ENTRANCE_PRESSURE_KEYS = (
    "pitot_entrance_pressure", "venturi_entrance_pressure", "nozzle_entrance_pressure",
    "orifice_entrance_pressure", "rotameter_entrance_pressure",
)

LOG_COLUMNS = {
    **{
        f"{cfg['label']} Entrance Pressure (psi)" if key in ENTRANCE_PRESSURE_KEYS
        else f"{cfg['label']} ({cfg['unit']})": ("sensor", key)
        for key, cfg in SENSOR_CONFIGS.items()
    },
    "Mass Flow Meter (SCFM)": ("loop", "flowrate"),
    "Flow Setpoint (SCFM)": ("loop_setpoint", "flowrate"),
    "Valve Command (%)": ("loop_valve", "flowrate"),
    "Flow Kc": ("loop_kc", "flowrate"),
    "Flow Ti (min)": ("loop_ti", "flowrate"),
    "Flow Td (min)": ("loop_td", "flowrate"),
}
