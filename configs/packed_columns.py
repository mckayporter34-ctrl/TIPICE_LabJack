# packed_columns.py — Packed Columns System Configuration
# =======================================================

SYSTEM_NAME = "Packed Columns"
LOGO_FILE   = "assets/tipice_logo.png"
LOG_FOLDER  = "PackedColumns_LoggedData"

from apps.packed_columns import PackedColumnsRedesignFrame
FrameClass = PackedColumnsRedesignFrame

# LabJack connection
ETHERNET_ADDRESS = "10.8.112.59"

# Main physical power relay
MAIN_POWER_PIN = "FIO6"
COLUMN_SELECTOR_PIN = "FIO7"
AIR_SETPOINT_PIN    = "TDAC0"
AIR_SETPOINT_SCALE  = 200.0

# Layout Grid coordinates
CONTROLS_ROW = 0
CONTROLS_COL = 0

DATA_LOGGING_ROW = 1
DATA_LOGGING_COL = 0
DATA_LOGGING_COLSPAN = 2

LOGO_ROW = 2
LOGO_COL = 0
LOGO_COLSPAN = 2

# Apparatus diagram path & positioning
APPARATUS_IMAGE = "images/Packedcol_main_apparatus.jpg"
APPARATUS_IMAGE_ROW = 3
APPARATUS_IMAGE_COL = 0
APPARATUS_IMAGE_COLSPAN = 2

# Digital System Switches (Controls panel)
SYSTEM_SWITCHES = [
    {
        "key": "column_selector",
        "label": "Column Selector",
        "type": "radio",
        "pin": "FIO7",
        # Maps BooleanVar state to physical LabJack output voltages:
        # True  (Column 1) -> 0 V
        # False (Column 2) -> 5 V
        "options": [
            ("Column 1 (White)", True, 0.0),
            ("Column 2 (Blue)", False, 5.0)
        ],
        "default": True
    }
]

# Manual Analog Outputs
MANUAL_ANALOG_OUTPUTS = {
    "air_flowrate_setpoint": {
        "label": "Air Flowrate",
        "unit": "SLPM",
        "pin": "TDAC0",
        "scale": 200.0,       # Setpoint (SLPM) / scale = Voltage
        "min_val": 0.0,
        "max_val": 150.0,
        "default": 0.0
    }
}

# Layout panel for Manual Outputs + air-side sensors
MANUAL_ANALOG_OUTPUTS_PANEL = {
    "title": "Air Flow",
    "row": 0,
    "col": 1,
    "columnspan": 1,
    "outputs": ["air_flowrate_setpoint"],
    "sensors": ["air_flowrate", "co2_concentration"]
}

# Read-only sensor definitions
SENSOR_CONFIGS = {
    "air_flowrate": {
        "label":       "Air Flowrate",
        "unit":        "SLPM",
        "pin":         "AIN0",
        "calibration": lambda v: 527.53746 * v - 250.26377,
    },
    "co2_concentration": {
        "label":       "Delta CO2 Concentration",
        "unit":        "ppm",
        "pin":         "",          # Unassigned
        "calibration": lambda v: v,
    },
    "water_temperature": {
        "label":       "Water Temp",
        "unit":        "°C",
        "pin":         "AIN6",
        "calibration": lambda v: (100.0 / (2.373 - 0.477)) * v
                                 + (-20.0 - 0.477 * (100.0 / (2.373 - 0.477))),
    },
    "column1_pressure_drop": {
        "label":       "Col 1 Pressure Drop",
        "unit":        "kPa",
        "pin":         "AIN2",
        "calibration": lambda v: 0.0 if 8.475 * v <= 4.05 else max(0.0, (v - 0.472) / (2.360 - 0.472) * 24.9)
    },
    "column2_pressure_drop": {
        "label":       "Col 2 Pressure Drop",
        "unit":        "kPa",
        "pin":         "AIN3",
        "calibration": lambda v: 0.0 if 8.475 * v <= 4.05 else max(0.0, (v - 0.472) / (2.360 - 0.472) * 24.9),
    },
}

# Group remaining read-only sensors on the GUI screen
SENSOR_PANELS = [
    {
        "title": "Sensor Inputs",
        "row": 1,
        "col": 1,
        "columnspan": 1,
        "columns": 1,
        "sensors": ["water_temperature", "column1_pressure_drop", "column2_pressure_drop"]
    }
]

# PID Control Loops
CONTROL_LOOP_CONFIGS = {
    "water_flow": {
        "label":            "Water",
        "unit":             "L/min",
        "input_pin":        "AIN1",
        "output_pin":       "DAC1",
        "calibration":      lambda v: 26.35046 * v - 12.35837,
        "setpoint_min":     0,
        "setpoint_max":     50,
        "default_setpoint": 0,
        "pid_defaults":     {"Kc": 0.14, "Ti": 0.06, "Td": 0.0},
        "extra_sensor_key": "water_temperature",
    },
    "column1_level": {
        "label":            "Column 1",
        "unit":             "mm",
        "input_pin":        "AIN4",
        "output_pin":       "DAC0",
        "calibration":     lambda v: max(0.0, ((v - 0.478) / 1.896) * 703.0),
        "setpoint_min":     0,
        "setpoint_max":     100,
        "default_setpoint": 0,
        "pid_defaults":     {"Kc": -0.05, "Ti": 2.0, "Td": 0.0},
        "extra_sensor_key": "column1_pressure_drop",
        "gate_switch":      "column_selector",
        "gate_value":       True  # Only active when Column Selector is Column 1
    },
    "column2_level": {
        "label":            "Column 2",
        "unit":             "mm",
        "input_pin":        "AIN5",
        "output_pin":       "DAC0",
        "calibration":      lambda v: max(0.0, ((v - 0.478) / 1.896) * 703.0),
        "setpoint_min":     0,
        "setpoint_max":     100,
        "default_setpoint": 0,
        "pid_defaults":     {"Kc": -0.05, "Ti": 2.0, "Td": 0.0},
        "extra_sensor_key": "column2_pressure_drop",
        "gate_switch":      "column_selector",
        "gate_value":       False # Only active when Column Selector is Column 2
    },
}

# Row positioning of control loops inside the grid (Col 3-5)
LOOP_ROWS = {
    "water_flow":    0,
    "column1_level": 1,
    "column2_level": 2,
}

# CSV Data logging columns
LOG_COLUMNS = {
    "Water Temp (C)":              ("sensor", "water_temperature"),
    "Water Flowrate (L/min)":      ("loop",   "water_flow"),
    "Air Flowrate (SLPM)":         ("sensor", "air_flowrate"),
    "Column 1 Pressure Drop (kPa)": ("sensor", "column1_pressure_drop"),
    "Column 2 Pressure Drop (kPa)": ("sensor", "column2_pressure_drop"),
}
