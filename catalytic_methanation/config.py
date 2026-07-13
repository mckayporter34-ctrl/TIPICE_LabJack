# config.py — Catalytic Methanation System Configuration
# =======================================================

from catalytic_methanation.app import CatalyticMethanationFrame

SYSTEM_NAME = "Catalytic Methanation"
LOGO_FILE   = "assets/tipice_logo.png"
LOG_FOLDER  = "CatalyticMethanation_LoggedData"

# Reference to the custom UI frame
FrameClass = CatalyticMethanationFrame

# LabJack connection
ETHERNET_ADDRESS = "10.8.112.99"

# Main physical power relay
MAIN_POWER_PIN = "FIO0"

# Pins for custom panels
GC_SELECT_PIN = "FIO2"       # 0.0V = Reactor Feed, 5.0V = Reactor Exhaust
HEATER_POWER_PIN = "FIO1"    # 5.0V = ON, 0.0V = OFF

# Layout Grid coordinates
CONTROLS_ROW = 0
CONTROLS_COL = 0

LOGO_ROW = 2
LOGO_COL = 0
LOGO_COLSPAN = 1

DATA_LOGGING_ROW = 0
DATA_LOGGING_COL = 1
DATA_LOGGING_COLSPAN = 1

# Manual Analog Outputs for the Gas setpoints
MANUAL_ANALOG_OUTPUTS = {
    "hydrogen_setpoint": {
        "label": "Hydrogen",
        "unit": "SLPM",
        "pin": "TDAC0",
        "scale": 10.0,       # 5V Max = 50 SLPM
        "min_val": 0.0,
        "max_val": 50.0,
        "default": 0.0
    },
    "co2_setpoint": {
        "label": "Carbon Dioxide",
        "unit": "SLPM",
        "pin": "TDAC1",
        "scale": 4.0,        # 5V Max = 20 SLPM
        "min_val": 0.0,
        "max_val": 20.0,
        "default": 0.0
    },
    "helium_setpoint": {
        "label": "Helium",
        "unit": "SLPM",
        "pin": "TDAC2",
        "scale": 2.0,        # 5V Max = 10 SLPM
        "min_val": 0.0,
        "max_val": 10.0,
        "default": 0.0
    }
}

# Read-only sensor definitions
SENSOR_CONFIGS = {
    "reactor_pressure_sensor": {
        "label":       "Reactor Pressure",
        "unit":        "psi",
        "pin":         "AIN0",
        "calibration": lambda v: v * 20.0,  # 0-5V -> 0-100 psi
    },
    "reactor_temp_sensor": {
        "label":       "Reactor Temperature",
        "unit":        "°C",
        "pin":         "AIN1",
        "calibration": lambda v: v * 100.0, # 0-5V -> 0-500 °C
    },
    "hydrogen_actual": {
        "label":       "H2 Actual Flow",
        "unit":        "SLPM",
        "pin":         "AIN2",
        "calibration": lambda v: v * 10.0,  # 0-5V -> 0-50 SLPM
    },
    "co2_actual": {
        "label":       "CO2 Actual Flow",
        "unit":        "SLPM",
        "pin":         "AIN3",
        "calibration": lambda v: v * 4.0,   # 0-5V -> 0-20 SLPM
    },
    "helium_actual": {
        "label":       "He Actual Flow",
        "unit":        "SLPM",
        "pin":         "AIN4",
        "calibration": lambda v: v * 2.0,   # 0-5V -> 0-10 SLPM
    }
}

# PID Control Loops
CONTROL_LOOP_CONFIGS = {
    "pressure": {
        "label":            "Reactor Pressure",
        "unit":             "psi",
        "input_pin":        "AIN0",
        "output_pin":       "DAC0",
        "calibration":      lambda v: v * 20.0,
        "setpoint_min":     0.0,
        "setpoint_max":     100.0,
        "default_setpoint": 14.7,
        "pid_defaults":     {"Kc": -5.0, "Ti": 0.01, "Td": 0.0},
    },
    "temperature": {
        "label":            "Temperature",
        "unit":             "°C",
        "input_pin":        "AIN1",
        "output_pin":       "DAC1",
        "calibration":      lambda v: v * 100.0,
        "setpoint_min":     0.0,
        "setpoint_max":     500.0,
        "default_setpoint": 0.0,
        "pid_defaults":     {"Kc": 3.0, "Ti": 5.0, "Td": 0.0},
        "gate_switch":      "heater_power",
        "gate_value":       True
    }
}

# Stack loop panels vertically in column 3
LOOP_ROWS = {
    "pressure":    0,
    "temperature": 1,
}

# CSV Data logging columns
LOG_COLUMNS = {
    "Reactor Pressure (psi)":        ("loop",   "pressure"),
    "Temperature (C)":               ("loop",   "temperature"),
    "H2 Actual Flow (SLPM)":         ("sensor", "hydrogen_actual"),
    "CO2 Actual Flow (SLPM)":        ("sensor", "co2_actual"),
    "He Actual Flow (SLPM)":         ("sensor", "helium_actual"),
}
