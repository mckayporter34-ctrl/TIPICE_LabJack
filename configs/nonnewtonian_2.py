"""Pipe Viscometer #2 (CB217A-Paul).

Source: Development/New_system_implementation.xlsx, NONNEWTONIAN_2,
rows 3, 5, 7, 11 and 19. Flow range, pump wiring, valve voltage range and
InAmp gain/offset were confirmed by the user on October 21, 2026.
Temperature now uses a direct AIN0–AIN1 differential thermocouple input
as requested on October 28, 2026.
"""

from pathlib import Path

from apps.nonnewtonian import NonNewtonianFrame
from core.numeric_entry import finite_number

FrameClass = NonNewtonianFrame
SYSTEM_NAME = "Non-Newtonian Fluids #2"
DEVICE_MANAGER_ENABLED = False  # Development system: connect without student checkout.
_ROOT = Path(__file__).resolve().parents[1]
LOGO_FILE = str(_ROOT / "assets" / "tipice_logo.png")
PID_IMAGE = str(_ROOT / "PI diagrams" / "NonNewtonaion_2_V1.png")
LOG_FOLDER = "NonNewtonian2_LoggedData"
MAIN_POWER_PIN = ""
ETHERNET_ADDRESS = ""  # Not supplied; Ethernet selection prompts for it.
OUTPUT_LABEL = "Valve"
# The valve can be positioned manually without running the pump.
MANUAL_OUTPUT_REQUIRES_PUMP = False

FLOW_MIN_GPM = 0.0
FLOW_MAX_GPM = 45.0
PUMP_PIN = "FIO0"
PUMP_ACTIVE_VALUE = 1.0
PUMP_INACTIVE_VALUE = 0.0
VALVE_V_MIN = 0.0
VALVE_V_MAX = 5.0

# Direct Type K thermocouple: positive to AIN0, negative to AIN1.
# Use the T7 temperature for cold-junction compensation.
COLD_JUNCTION_REGISTER = "TEMPERATURE_DEVICE_K"
_cj_temp_c = [float("nan")]
TEMPERATURE_FILTER_TIME_CONSTANT_S = 5.0

CURRENT_V_MIN = 0.472
CURRENT_V_MAX = 2.360


def _flowrate(voltage):
    return FLOW_MIN_GPM + (finite_number(voltage) - CURRENT_V_MIN) * (FLOW_MAX_GPM - FLOW_MIN_GPM) / (CURRENT_V_MAX - CURRENT_V_MIN)


def _pressure_drop_wc(voltage):
    return (finite_number(voltage) - CURRENT_V_MIN) * 50.0 / (CURRENT_V_MAX - CURRENT_V_MIN)


def _temperature_c(voltage):
    from labjack import ljm

    tc_volts = finite_number(voltage)  # AIN0 already returns AIN0 minus AIN1.
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
        "filter_time_constant_s": TEMPERATURE_FILTER_TIME_CONSTANT_S,
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
        "pid_defaults": {"Kc": 0.05, "Ti": 0.02, "Td": 0.0},
    },
}
AIN_CONFIGS = {
    "AIN0": {"NEGATIVE_CH": 1, "RANGE": 0.1, "RESOLUTION_INDEX": 8},
    "AIN2": {"NEGATIVE_CH": 199, "RANGE": 10, "RESOLUTION_INDEX": 1},
    "AIN3": {"NEGATIVE_CH": 199, "RANGE": 10, "RESOLUTION_INDEX": 1},
}
# Overlay anchors are pixels in the 2356 × 948 source diagram.
DIAGRAM_READOUTS = [
    ("pressure_drop", "Pressure Drop (in WC)", 1932, 284, "s"),
    ("fluid_temperature", "Fluid Temperature (°C)", 840, 916, "n"),
    ("flowrate", "Flowrate (GPM)", 1188, 916, "n"),
    ("output", "Valve Command (%)", 1272, 272, "s"),
]
PUMP_STATUS_POSITION = (868, 432)
LOG_COLUMNS = {
    "Fluid Temperature Filtered (C)": ("sensor", "fluid_temperature"),
    "Fluid Temperature Raw (C)": ("sensor_raw", "fluid_temperature"),
    "Pressure Drop (in WC)": ("sensor", "pressure_drop"),
    "Flowrate (GPM)": ("loop", "flowrate"),
    "Flow Setpoint (GPM)": ("loop_setpoint", "flowrate"),
    "Valve Command (%)": ("loop_valve", "flowrate"),
    "Flow Kc (V/GPM)": ("loop_kc", "flowrate"),
    "Flow Ti (min)": ("loop_ti", "flowrate"),
    "Flow Td (min)": ("loop_td", "flowrate"),
}
