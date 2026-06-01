# config.py — Packed Columns System Configuration
# =================================================
# This is the ONLY file that needs to be edited when adapting this GUI
# to a different lab system. All pin assignments, calibration equations,
# PID defaults, and logging layout are defined here.
#
# To create a GUI for a new system:
#   1. Copy the entire project folder.
#   2. Update SYSTEM_NAME, LOGO_FILE, LOG_FOLDER below.
#   3. Edit SENSOR_CONFIGS  — add, remove, or modify read-only sensors.
#   4. Edit CONTROL_LOOP_CONFIGS — add, remove, or modify PID control loops.
#      Each loop automatically gets a full panel with slider, progress bar,
#      and PID tuning spinboxes. Add "extra_sensor_key" to show a second
#      sensor reading inside the same panel.
#   5. Edit LOG_COLUMNS — choose which values appear in the CSV output.
#   6. If the panel LAYOUT changes (e.g. different number of columns),
#      also update the grid() calls in app.py _build_ui().

# ── System identity ────────────────────────────────────────────────────────────
SYSTEM_NAME = "Packed Columns"
LOGO_FILE   = "assets/tipice_logo.png"
LOG_FOLDER  = "PackedColumns_LoggedData"

# ── LabJack connection ─────────────────────────────────────────────────────────
ETHERNET_ADDRESS = "10.8.112.59"

# ── Fixed digital / special analog outputs ────────────────────────────────────
MAIN_POWER_PIN      = "FIO6"   # Write 1 to turn system on, 0 to turn off
COLUMN_SELECTOR_PIN = "FIO7"   # 0 V = Column 1 active,  5 V = Column 2 active
AIR_SETPOINT_PIN    = "TDAC0"  # Analog output driving the air mass-flow controller
AIR_SETPOINT_SCALE  = 200.0    # SLPM ÷ AIR_SETPOINT_SCALE = voltage sent to MFC

# ── Read-only sensor displays ──────────────────────────────────────────────────
# Each entry becomes a Sensor object and a display widget in the GUI.
# Removing an entry removes that sensor entirely.
# Setting "pin" to "" marks the channel as unassigned (displays "Error" until
# a real pin is assigned).
#
# Calibration: callable that maps raw voltage (float) → engineering value (float).
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
        "pin":         "",          # Not yet connected on this system
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
        "label":       "Column 1 Pressure Drop",
        "unit":        "Pa",
        "pin":         "AIN2",
        "calibration": lambda v: max(0.0, (100.0 * (v - 0.476) / (2.373 - 0.476)) * 248.84),
    },
    "column2_pressure_drop": {
        "label":       "Column 2 Pressure Drop",
        "unit":        "Pa",
        "pin":         "AIN3",
        "calibration": lambda v: max(0.0, (100.0 * (v - 0.476) / (2.373 - 0.476)) * 248.84),
    },
}

# ── Closed-loop PID control channels ──────────────────────────────────────────
# Each entry creates a ControlLoop object: one sensor input, one PID controller,
# and one analog valve output.
#
# "extra_sensor_key" (optional): a key from SENSOR_CONFIGS whose live reading
# is displayed inside this control panel (e.g. water temperature shown alongside
# the water-flow control panel; pressure drop shown alongside a level panel).
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
        "calibration":      lambda v: max(0.0, ((v - 0.478) / 1.896) * 703.0),
        "setpoint_min":     0,
        "setpoint_max":     100,
        "default_setpoint": 0,
        "pid_defaults":     {"Kc": -0.05, "Ti": 2.0, "Td": 0.0},
        "extra_sensor_key": "column1_pressure_drop",
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
    },
}

# ── Data logging ───────────────────────────────────────────────────────────────
# Maps CSV column headers to their data source.
#   ("sensor", key) → reads from SENSOR_CONFIGS[key]   (value_var)
#   ("loop",   key) → reads from CONTROL_LOOP_CONFIGS[key] (measured_var)
# Column order in the CSV matches the dict insertion order.
LOG_COLUMNS = {
    "Water Temp (C)":              ("sensor", "water_temperature"),
    "Water Flowrate (L/min)":      ("loop",   "water_flow"),
    "Air Flowrate (SLPM)":         ("sensor", "air_flowrate"),
    "Column 1 Pressure Drop (Pa)": ("sensor", "column1_pressure_drop"),
    "Column 2 Pressure Drop (Pa)": ("sensor", "column2_pressure_drop"),
}
