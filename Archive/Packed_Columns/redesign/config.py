# config.py — Packed Columns System Configuration
# =================================================

# ── System identity ────────────────────────────────────────────────────────────
SYSTEM_NAME = "Packed Columns Redesign"
LOGO_FILE   = "assets/tipice_logo.png"
LOG_FOLDER  = "PackedColumns_Redesign_LoggedData"

# ── LabJack connection ─────────────────────────────────────────────────────────
ETHERNET_ADDRESS = "10.8.112.59"

# ── Fixed digital / special analog outputs ────────────────────────────────────
MAIN_POWER_PIN      = "FIO6"   # Write 1 to turn system on, 0 to turn off
COLUMN_SELECTOR_PIN = "FIO7"   # 0 V = Column 1 active,  5 V = Column 2 active
AIR_SETPOINT_PIN    = "TDAC0"  # Analog output driving the air mass-flow controller
AIR_SETPOINT_SCALE  = 200.0    # SLPM ÷ AIR_SETPOINT_SCALE = voltage sent to MFC

# ── Read-only sensor displays ──────────────────────────────────────────────────
SENSOR_CONFIGS = {
    "air_flowrate": {
        "label":       "Air Flowrate",
        "unit":        "SLPM",
        "pin":         "AIN0",
        "calibration": lambda v: 527.53746 * v - 250.26377,
    },
    "co2_concentration": {
        "label":       "Delta CO2",
        "unit":        "ppm",
        "pin":         "AIN7",
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
        "unit":        "Pa",
        "pin":         "AIN2",
        "calibration": lambda v: max(0.0, (100.0 * (v - 0.476) / (2.373 - 0.476)) * 248.84),
    },
    "column2_pressure_drop": {
        "label":       "Col 2 Pressure Drop",
        "unit":        "Pa",
        "pin":         "AIN3",
        "calibration": lambda v: max(0.0, (100.0 * (v - 0.476) / (2.373 - 0.476)) * 248.84),
    },
}

# ── Closed-loop PID control channels ──────────────────────────────────────────
CONTROL_LOOP_CONFIGS = {
    "water_flow": {
        "label":            "Water Control",
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
        "label":            "Col 1 Level Control",
        "unit":             "mm",
        "input_pin":        "AIN4",
        "output_pin":       "DAC0",
        "calibration":      lambda v: max(0.0, ((v - 0.478) / 1.896) * 703.0),
        "setpoint_min":     0,
        "setpoint_max":     100,
        "default_setpoint": 0,
        "pid_defaults":     {"Kc": -0.05, "Ti": 2.0, "Td": 0.0},
        "extra_sensor_key": "column1_pressure_drop",
    },
    "column2_level": {
        "label":            "Col 2 Level Control",
        "unit":             "mm",
        "input_pin":        "AIN5",
        "output_pin":       "DAC0",
        "calibration":      lambda v: max(0.0, ((v - 0.478) / 1.896) * 703.0),
        "setpoint_min":     0,
        "setpoint_max":     100,
        "default_setpoint": 0,
        "pid_defaults":     {"Kc": -0.05, "Ti": 2.0, "Td": 0.0},
        "extra_sensor_key": "column2_pressure_drop",
    },
}

# ── Data logging ───────────────────────────────────────────────────────────────
LOG_COLUMNS = {
    "Water Temp (C)":              ("sensor", "water_temperature"),
    "Water Flowrate (L/min)":      ("loop",   "water_flow"),
    "Air Flowrate (SLPM)":         ("sensor", "air_flowrate"),
    "CO2 Concentration (ppm)":     ("sensor", "co2_concentration"),
    "Column 1 Pressure Drop (Pa)": ("sensor", "column1_pressure_drop"),
    "Column 2 Pressure Drop (Pa)": ("sensor", "column2_pressure_drop"),
    "Column 1 Level (mm)":         ("loop",   "column1_level"),
    "Column 2 Level (mm)":         ("loop",   "column2_level"),
}
