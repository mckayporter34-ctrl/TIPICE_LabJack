"""Pipe Viscometer #2 (CB217A-Paul).

Source: Development/New_system_implementation.xlsx, NONNEWTONIAN_2,
rows 3, 5, 7, 11 and 19. Flow range, pump wiring, valve voltage range and
InAmp gain/offset were confirmed by the user on October 21, 2026.
"""

from pathlib import Path

from apps.nonnewtonian import NonNewtonianFrame
from core.numeric_entry import finite_number

FrameClass = NonNewtonianFrame
SYSTEM_NAME = "Non-Newtonian Fluids #2"
_ROOT = Path(__file__).resolve().parents[1]
LOGO_FILE = str(_ROOT / "assets" / "tipice_logo.png")
PID_IMAGE = str(_ROOT / "PI diagrams" / "NonNewtonaion_2_V1.png")
LOG_FOLDER = "NonNewtonian2_LoggedData"
MAIN_POWER_PIN = ""
ETHERNET_ADDRESS = ""  # Not supplied; Ethernet selection prompts for it.
OUTPUT_LABEL = "Valve"

FLOW_MIN_GPM = 0.0
FLOW_MAX_GPM = 45.0
PUMP_PIN = "FIO0"
PUMP_ACTIVE_VALUE = 1.0
PUMP_INACTIVE_VALUE = 0.0
VALVE_V_MIN = 0.0
VALVE_V_MAX = 5.0

# Confirmed InAmp3 configuration; use the T7 temperature for compensation.
INAMP_GAIN = 51.0
INAMP_OFFSET_V = 1.25
COLD_JUNCTION_REGISTER = "TEMPERATURE_DEVICE_K"
_cj_temp_c = [float("nan")]

CURRENT_V_MIN = 0.472
CURRENT_V_MAX = 2.360


def _flowrate(voltage):
    return FLOW_MIN_GPM + (finite_number(voltage) - CURRENT_V_MIN) * (FLOW_MAX_GPM - FLOW_MIN_GPM) / (CURRENT_V_MAX - CURRENT_V_MIN)


def _pressure_drop_wc(voltage):
    return (finite_number(voltage) - CURRENT_V_MIN) * 50.0 / (CURRENT_V_MAX - CURRENT_V_MIN)


def _temperature_c(voltage):
    from labjack import ljm

    tc_volts = (finite_number(voltage) - INAMP_OFFSET_V) / INAMP_GAIN
    cj_kelvin = finite_number(_cj_temp_c[0]) + 273.15
    return ljm.tcVoltsToTemp(6004, tc_volts, cj_kelvin) - 273.15


SYSTEM_SWITCHES = [
    {"key": "pump", "label": "Pump", "type": "toggle", "pin": PUMP_PIN,
     "active_value": PUMP_ACTIVE_VALUE, "inactive_value": PUMP_INACTIVE_VALUE,
     "default": False},
]
SENSOR_CONFIGS = {
    "fluid_temperature": {
        "label": "Fluid Temperature", "unit": "°C", "pin": "AIN0",
        "calibration": _temperature_c,
    },
    "pressure_drop": {
        "label": "Pressure Drop", "unit": "in WC", "pin": "AIN3",
        "calibration": _pressure_drop_wc,
    },
}
CONTROL_LOOP_CONFIGS = {
    "flowrate": {
        "label": "Flowrate", "unit": "GPM",
        "input_pin": "AIN2", "output_pin": "DAC0", "calibration": _flowrate,
        "output_min": VALVE_V_MIN, "output_max": VALVE_V_MAX,
        "setpoint_min": FLOW_MIN_GPM,
        "setpoint_max": FLOW_MAX_GPM,
        "default_setpoint": 0.0,
        # Initial positive action assumes increasing signal opens the valve.
        # Commission the gain, direction, and integral time on the apparatus.
        "pid_defaults": {"Kc": 0.1, "Ti": 1.0, "Td": 0.0},
    },
}
AIN_CONFIGS = {
    pin: {"NEGATIVE_CH": 199, "RANGE": 10.0, "RESOLUTION_INDEX": 8 if pin == "AIN0" else 1}
    for pin in ("AIN0", "AIN2", "AIN3")
}
DIAGRAM_READOUTS = [
    ("pressure_drop", "Pressure Drop (in WC)", 483, 71, "s"),
    ("fluid_temperature", "Fluid Temperature (°C)", 210, 229, "ne"),
    ("flowrate", "Flowrate (GPM)", 297, 229, "nw"),
    ("output", "Valve Command (%)", 318, 91, "s"),
]
LOG_COLUMNS = {
    "Fluid Temperature (C)": ("sensor", "fluid_temperature"),
    "Pressure Drop (in WC)": ("sensor", "pressure_drop"),
    "Flowrate (GPM)": ("loop", "flowrate"),
    "Flow Setpoint (GPM)": ("loop_setpoint", "flowrate"),
    "Valve Command (%)": ("loop_valve", "flowrate"),
    "Flow Kc (V/GPM)": ("loop_kc", "flowrate"),
    "Flow Ti (min)": ("loop_ti", "flowrate"),
    "Flow Td (min)": ("loop_td", "flowrate"),
}
