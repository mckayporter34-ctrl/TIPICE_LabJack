# shell_tube_hx_1.py — Shell and Tube Heat Exchanger #1 Configuration
# ===================================================================

SYSTEM_NAME = "Shell & Tube Heat Exchanger #1"
LOGO_FILE   = "assets/tipice_logo.png"
LOG_FOLDER  = "ShellTubeHX1_LoggedData"

from apps.shell_tube_hx import ShellTubeHXRedesignFrame
FrameClass = ShellTubeHXRedesignFrame

# LabJack connection
ETHERNET_ADDRESS = "10.8.112.12"

# Main physical power relay
MAIN_POWER_PIN = "DIO2"

# Layout Grid coordinates
CONTROLS_ROW = 0
CONTROLS_COL = 0

LOGO_ROW = 1
LOGO_COL = 0
LOGO_COLSPAN = 1

DATA_LOGGING_ROW = 0
DATA_LOGGING_COL = 1
DATA_LOGGING_COLSPAN = 2

# Apparatus diagram path & positioning
APPARATUS_IMAGE = "images/STHX1_apparatus.jpg"
APPARATUS_IMAGE_ROW = 2
APPARATUS_IMAGE_COL = 1
APPARATUS_IMAGE_COLSPAN = 2

# Digital System Switches (Controls panel)
SYSTEM_SWITCHES = [
    {
        "key": "pump",
        "label": "Pump",
        "type": "toggle",
        "pin": "DIO3",
        "active_value": 1.0,
        "inactive_value": 0.0,
        "default": False
    }
]

# LabJack AIN settings (applied on connection)
AIN_CONFIGS = {
    "AIN0": {"NEGATIVE_CH": 199, "RANGE": 10.0, "RESOLUTION_INDEX": 1},
    "AIN1": {"NEGATIVE_CH": 199, "RANGE": 10.0, "RESOLUTION_INDEX": 1},
    "AIN2": {"NEGATIVE_CH": 199, "RANGE": 10.0},
    "AIN3": {"NEGATIVE_CH": 199, "RANGE": 10.0},
    "AIN4": {"NEGATIVE_CH": 199, "RANGE": 10.0},
    "AIN5": {"NEGATIVE_CH": 199, "RANGE": 10.0},
    "AIN6": {"NEGATIVE_CH": 199, "RANGE": 10.0},
    "AIN7": {"NEGATIVE_CH": 199, "RANGE": 10.0},
}

# Internal cold junction register for thermocouple compensation
COLD_JUNCTION_REGISTER = "TEMPERATURE_DEVICE_K"

# Thermocouple calibration support
INAMP_GAIN     = 51.0
INAMP_OFFSET_V = 1.25
_cj_temp_c     = [25.0]  # Updated dynamically by base_app update loop

def _type_k_temp(amp_voltage_v):
    tc_voltage_v = (amp_voltage_v - INAMP_OFFSET_V) / INAMP_GAIN
    return _cj_temp_c[0] + tc_voltage_v / 41.276e-6

# Flowrate conversion (AIN4 LJTCS current loop)
_FLOW_Q_MIN = 0.79
_FLOW_Q_MAX = 79.00
_FLOW_V_MIN = 0.472
_FLOW_V_MAX = 2.360

def _flowrate_gpm(v):
    if v < _FLOW_V_MIN:
        return 0.0
    return _FLOW_Q_MIN + (v - _FLOW_V_MIN) * (_FLOW_Q_MAX - _FLOW_Q_MIN) / (_FLOW_V_MAX - _FLOW_V_MIN)

# Pressure conversion helper
_PRESSURE_V_MIN   = 0.472
_PRESSURE_V_MAX   = 2.360
_PRESSURE_ZERO_MA = 4.05

def _make_pressure_cal(p_min, p_max, V_min=_PRESSURE_V_MIN, V_max=_PRESSURE_V_MAX):
    return lambda v: (
        0.0 if 8.475 * v <= _PRESSURE_ZERO_MA
        else min(p_max, p_min + (v - V_min) * (p_max - p_min) / (V_max - V_min))
    )

# Read-only sensor definitions
SENSOR_CONFIGS = {
    "water_inlet_temp": {
        "label":       "Water Inlet Temp",
        "unit":        "°C",
        "pin":         "AIN1",
        "calibration": _type_k_temp,
    },
    "water_outlet_temp": {
        "label":       "Water Outlet Temp",
        "unit":        "°C",
        "pin":         "AIN0",
        "calibration": _type_k_temp,
    },
    "house_steam_pressure": {
        "label":       "House Steam Pressure",
        "unit":        "psig",
        "pin":         "TODO",
        "calibration": lambda v: v,  # TODO calibration
    },
    "tube_side_pressure_drop": {
        "label":       "Tube-Side Pressure Drop",
        "unit":        "psig",
        "pin":         "AIN6",
        "calibration": _make_pressure_cal(0.0, 15.0),
    },
    "makeup_temperature": {
        "label":       "Makeup Temperature",
        "unit":        "°C",
        "pin":         "AIN2",
        "calibration": lambda v: (((4 + ((v * 8.475 - 4) / 16.0) * (176 - 4))) - 32) * 5 / 9,
    },
    "makeup_flowrate": {
        "label":       "Makeup Flowrate",
        "unit":        "GPM",
        "pin":         "AIN3",
        "calibration": lambda v: max(0.0, ((v * 8.475 - 4) / 16.0) * 6.6),
    },
}

# Left side sensor panel layout
SENSOR_PANELS = [
    {
        "title": "Temperatures",
        "row": 1,
        "col": 1,
        "columnspan": 1,
        "columns": 1,
        "sensors": ["water_inlet_temp", "water_outlet_temp", "makeup_temperature"]
    },
    {
        "title": "Pressures",
        "row": 1,
        "col": 2,
        "columnspan": 1,
        "columns": 1,
        "sensors": ["tube_side_pressure_drop", "makeup_flowrate"]
    }
]

# PID Control Loops
CONTROL_LOOP_CONFIGS = {
    "level": {
        "label":            "Level",
        "unit":             "ft",
        "input_pin":        "AIN5",
        "output_pin":       "DAC0",
        "calibration":      lambda v: 0.0 if 8.475 * v <= 4.05 else min(1.96, 0.0 + (v - 0.472) * (1.96 - 0.0) / (2.360 - 0.472)),
        "setpoint_min":     0.0,
        "setpoint_max":     1.96,
        "default_setpoint": 0.0,
        "pid_defaults":     {"Kc": -75.0, "Ti": 0.005, "Td": 0.0},
        "extra_sensor_key": None,
    },
    "flowrate": {
        "label":            "Flowrate",
        "unit":             "GPM",
        "input_pin":        "AIN4",
        "output_pin":       "DAC1",
        "calibration":      _flowrate_gpm,
        "setpoint_min":     0.0,
        "setpoint_max":     79.00,
        "default_setpoint": 0.0,
        "pid_defaults":     {"Kc": 0.74, "Ti": 0.036, "Td": 0.0},
        "extra_sensor_key": None,
    },
    "steam_pressure": {
        "label":            "Steam Pressure",
        "unit":             "psig",
        "input_pin":        "AIN7",
        "output_pin":       "TDAC0",
        "calibration":      _make_pressure_cal(0.0, 150.0, V_min=0.479),
        "setpoint_min":     0.0,
        "setpoint_max":     150.0,
        "default_setpoint": 0.0,
        "pid_defaults":     {"Kc": 0.5, "Ti": 0.05, "Td": 0.0},
        "extra_sensor_key": "house_steam_pressure",
    },
}

# Row positioning of control loops inside the grid (Col 3-5)
LOOP_ROWS = {
    "level":          0,
    "flowrate":       1,
    "steam_pressure": 2,
}

# CSV Data logging columns
LOG_COLUMNS = {
    "Water Inlet Temp (C)":        ("sensor", "water_inlet_temp"),
    "Water Outlet Temp (C)":       ("sensor", "water_outlet_temp"),
    "Tube-Side dP (psig)":         ("sensor", "tube_side_pressure_drop"),
    "Makeup Temp (C)":             ("sensor", "makeup_temperature"),
    "Makeup Flowrate (L/min)":     ("sensor", "makeup_flowrate"),
    "Level (ft)":                  ("loop",   "level"),
    "Flowrate (GPM)":              ("loop",   "flowrate"),
    "Steam Pressure (psig)":       ("loop",   "steam_pressure"),
    "House Steam Pressure (psig)": ("sensor", "house_steam_pressure"),
    "Level Setpoint (ft)":         ("loop_setpoint", "level"),
    "Level Valve (%)":             ("loop_valve", "level"),
    "Level Kc":                    ("loop_kc", "level"),
    "Level Ti (min)":              ("loop_ti", "level"),
    "Level Td (min)":              ("loop_td", "level"),
    "Flowrate Setpoint (GPM)":     ("loop_setpoint", "flowrate"),
    "Flowrate Valve (%)":          ("loop_valve", "flowrate"),
    "Flowrate Kc":                 ("loop_kc", "flowrate"),
    "Flowrate Ti (min)":           ("loop_ti", "flowrate"),
    "Flowrate Td (min)":           ("loop_td", "flowrate"),
    "Steam Pressure Setpoint (psig)": ("loop_setpoint", "steam_pressure"),
    "Steam Pressure Valve (%)":    ("loop_valve", "steam_pressure"),
    "Steam Pressure Kc":           ("loop_kc", "steam_pressure"),
    "Steam Pressure Ti (min)":     ("loop_ti", "steam_pressure"),
    "Steam Pressure Td (min)":     ("loop_td", "steam_pressure"),
}
