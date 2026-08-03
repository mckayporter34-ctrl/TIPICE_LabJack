# pump_cart.py — Pump Cart System Configuration
# ============================================

SYSTEM_NAME = "Pump Cart"
LOGO_FILE   = "assets/tipice_logo.png"
LOG_FOLDER  = "PumpCart_LoggedData"

# LabJack connection
ETHERNET_ADDRESS = "TODO"

# Main physical power relay
MAIN_POWER_PIN = "TODO"

# Layout Grid coordinates
CONTROLS_ROW = 0
CONTROLS_COL = 0

LOGO_ROW = 1
LOGO_COL = 0
LOGO_COLSPAN = 1

DATA_LOGGING_ROW = 0
DATA_LOGGING_COL = 1
DATA_LOGGING_COLSPAN = 1

# Apparatus diagram path & positioning
APPARATUS_IMAGE = "images/Pumpcart_apparatus.jpg"
APPARATUS_IMAGE_ROW = 2
APPARATUS_IMAGE_COL = 1
APPARATUS_IMAGE_COLSPAN = 1

# Digital System Switches (Controls panel)
SYSTEM_SWITCHES = [
    {
        "key": "pump",
        "label": "Pump",
        "type": "toggle",
        "pin": "TODO",
        "active_value": 1.0,
        "inactive_value": 0.0,
        "default": False
    }
]

# Read-only sensor definitions
SENSOR_CONFIGS = {
    # ── Pressure sensors (shown in grid) ───────────────────────────
    "pump_valve_dp": {
        "label":       "Pump Valve ΔP",
        "unit":        "psig",
        "pin":         "TODO",
        "calibration": lambda v: v,
    },
    "globe_valve_dp": {
        "label":       "Globe Valve ΔP",
        "unit":        "psig",
        "pin":         "TODO",
        "calibration": lambda v: v,
    },
    "ball_valve_dp": {
        "label":       "Ball Valve ΔP",
        "unit":        "psig",
        "pin":         "TODO",
        "calibration": lambda v: v,
    },
    "el_dp": {
        "label":       "EL ΔP",
        "unit":        "psig",
        "pin":         "TODO",
        "calibration": lambda v: v,
    },
    "tee_dp": {
        "label":       "TEE ΔP",
        "unit":        "psig",
        "pin":         "TODO",
        "calibration": lambda v: v,
    },
    "pipe_dp": {
        "label":       "Pipe ΔP",
        "unit":        "psig",
        "pin":         "TODO",
        "calibration": lambda v: v,
    },
    "u_dp": {
        "label":       "U ΔP",
        "unit":        "psig",
        "pin":         "TODO",
        "calibration": lambda v: v,
    },
    "bypass_dp": {
        "label":       "Bypass ΔP",
        "unit":        "psig",
        "pin":         "TODO",
        "calibration": lambda v: v,
    },
    "control_valve_dp": {
        "label":       "Control Valve ΔP",
        "unit":        "psig",
        "pin":         "TODO",
        "calibration": lambda v: v,
    },

    # ── Temperature (shown in grid alongside pressures) ────────────
    "fluid_temperature": {
        "label":       "Fluid Temperature",
        "unit":        "°C",
        "pin":         "TODO",
        "calibration": lambda v: v,
    },

    # ── Sensors embedded inside control loop panels ────────────────────────────
    "bypass_flowrate": {
        "label":       "Bypass Flowrate",
        "unit":        "GPM",
        "pin":         "TODO",
        "calibration": lambda v: v,
    },
    "pump_speed_rpm": {
        "label":       "Actual Pump Speed",
        "unit":        "RPM",
        "pin":         "TODO",
        "calibration": lambda v: v,
    },
    "pump_motor_power": {
        "label":       "Motor Power",
        "unit":        "W",
        "pin":         "TODO",
        "calibration": lambda v: v,
    },
}

# Left side sensor panel layout: displays pressures & temperature in a grid
SENSOR_PANELS = [
    {
        "title": "Pressures & Temperature",
        "row": 1,
        "col": 1,
        "columnspan": 1,
        "columns": 3,
        "sensors": [
            "pump_valve_dp",
            "globe_valve_dp",
            "ball_valve_dp",
            "el_dp",
            "tee_dp",
            "pipe_dp",
            "u_dp",
            "bypass_dp",
            "control_valve_dp",
            "fluid_temperature",
        ]
    }
]

# PID Control Loops
CONTROL_LOOP_CONFIGS = {
    "flowrate": {
        "label":            "Flowrate",
        "unit":             "GPM",
        "input_pin":        "TODO",
        "output_pin":       "TODO",
        "calibration":      lambda v: v,
        "setpoint_min":     0.0,
        "setpoint_max":     100.0,
        "default_setpoint": 0.0,
        "pid_defaults":     {"Kc": 2.0, "Ti": 0.05, "Td": 0.0},
        # Displays bypass flowrate inside the panel
        "extra_sensor_keys": ["bypass_flowrate"],
    },
    "pump_speed": {
        "label":            "Pump Speed",
        "unit":             "% nominal",
        "input_pin":        "TODO",
        "output_pin":       "TODO",
        "calibration":      lambda v: v,
        "setpoint_min":     0.0,
        "setpoint_max":     100.0,
        "default_setpoint": 0.0,
        "pid_defaults":     {"Kc": 1.0, "Ti": 1.0, "Td": 0.0},
        # Displays actual RPM and motor power (W) inside the panel
        "extra_sensor_keys": ["pump_speed_rpm", "pump_motor_power"],
    },
}

# Row positioning of control loops inside the grid (Col 2-5)
LOOP_ROWS = {
    "flowrate":   0,
    "pump_speed": 1,
}

# CSV Data logging columns
LOG_COLUMNS = {
    "Fluid Temp (C)":             ("sensor", "fluid_temperature"),
    "Main Flowrate (GPM)":        ("loop",   "flowrate"),
    "Bypass Flowrate (GPM)":      ("sensor", "bypass_flowrate"),
    "Pump Speed (% nominal)":     ("loop",   "pump_speed"),
    "Pump Speed (RPM)":           ("sensor", "pump_speed_rpm"),
    "Motor Power (W)":            ("sensor", "pump_motor_power"),
    "Pump Valve ΔP (psig)":       ("sensor", "pump_valve_dp"),
    "Globe Valve ΔP (psig)":      ("sensor", "globe_valve_dp"),
    "Ball Valve ΔP (psig)":       ("sensor", "ball_valve_dp"),
    "EL ΔP (psig)":               ("sensor", "el_dp"),
    "TEE ΔP (psig)":              ("sensor", "tee_dp"),
    "Pipe ΔP (psig)":             ("sensor", "pipe_dp"),
    "U ΔP (psig)":                ("sensor", "u_dp"),
    "Bypass ΔP (psig)":           ("sensor", "bypass_dp"),
    "Control Valve ΔP (psig)":    ("sensor", "control_valve_dp"),
}
