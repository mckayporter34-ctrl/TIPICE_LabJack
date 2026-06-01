# config.py — Pump Cart System Configuration
# ============================================
# Fill in every value marked TODO before running the GUI.
# Copy the following unchanged files from the packed_columns folder:
#   sensor.py, control_loop.py, pid_controller.py, labjack_interface.py,
#   data_logger.py
# Copy the updated ui_builders.py provided alongside this file.

# ── System identity ────────────────────────────────────────────────────────────
SYSTEM_NAME = "Pump Cart"
LOGO_FILE   = "assets/tipice_logo.png"
LOG_FOLDER  = "PumpCart_LoggedData"

# ── LabJack connection ─────────────────────────────────────────────────────────
ETHERNET_ADDRESS = "TODO"          # e.g. "10.8.112.XX"

# ── Fixed digital outputs ──────────────────────────────────────────────────────
MAIN_POWER_PIN  = "TODO"           # e.g. "FIO6"
PUMP_SWITCH_PIN = "TODO"           # Pump switch digital output pin e.g. "FIO5"

# ── Read-only sensor displays ──────────────────────────────────────────────────
# Sensors are split into two groups in the GUI:
#   1. Pressure sensors → displayed in the wide horizontal panel at the bottom
#   2. Extra loop sensors (bypass_flowrate, pump_speed_rpm, pump_motor_power)
#      → displayed inside their respective control loop panels
#
# Calibration notes:
#   All pressure sensors are likely 4-20 mA with a 250 Ω shunt (1-5 V at LabJack).
#   Use: slope = (eng_max - eng_min) / (5.0 - 1.0)
#        intercept = eng_min - slope * 1.0
#   e.g. 0-15 psig sensor: slope = 3.75, intercept = -3.75
#        lambda v: 3.75 * v - 3.75

SENSOR_CONFIGS = {

    # ── Pressure sensors (shown in horizontal panel) ───────────────────────────
    "pump_valve_dp": {
        "label":       "Pump Valve ΔP",
        "unit":        "psig",
        "pin":         "TODO",
        "calibration": lambda v: v,    # TODO: lambda v: slope * v + intercept
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

    # ── Temperature (shown in horizontal panel alongside pressures) ────────────
    "fluid_temperature": {
        "label":       "Fluid Temperature",
        "unit":        "°C",
        "pin":         "TODO",
        "calibration": lambda v: v,    # TODO: derive from thermocouple conditioner
    },

    # ── Sensors embedded inside control loop panels ────────────────────────────
    "bypass_flowrate": {
        "label":       "Bypass Flowrate",
        "unit":        "GPM",
        "pin":         "TODO",
        "calibration": lambda v: v,    # TODO: FLOWSERVE 520MD calibration
    },
    "pump_speed_rpm": {
        "label":       "Actual Pump Speed",
        "unit":        "RPM",
        "pin":         "TODO",
        "calibration": lambda v: v,    # TODO: derive from tachometer signal range
    },
    "pump_motor_power": {
        "label":       "Motor Power",
        "unit":        "W",
        "pin":         "TODO",
        "calibration": lambda v: v,    # TODO: derive from power meter signal range
    },
}

# ── Closed-loop PID control channels ──────────────────────────────────────────
CONTROL_LOOP_CONFIGS = {

    "flowrate": {
        "label":            "Flowrate",
        "unit":             "GPM",
        "input_pin":        "TODO",        # Main line flow sensor — OMEGA IS2.140
        "output_pin":       "TODO",        # Control valve — FLOWSERVE 520MD
        "calibration":      lambda v: v,   # TODO: OMEGA IS2.140 calibration
        "setpoint_min":     0,
        "setpoint_max":     100,           # TODO: set to max rated flow in GPM
        "default_setpoint": 0,
        "pid_defaults":     {"Kc": 2.0, "Ti": 0.05, "Td": 0.0},
        # Bypass flowrate is displayed in this panel as a second readout
        "extra_sensor_key": "bypass_flowrate",
    },

    "pump_speed": {
        "label":            "Pump Speed",
        "unit":             "% nominal",
        "input_pin":        "TODO",        # Speed feedback signal from VFD/tachometer
        "output_pin":       "TODO",        # Speed command output to VFD
        # Input is speed as % of nominal 3450 RPM
        "calibration":      lambda v: v,   # TODO: derive from VFD feedback signal range
        "setpoint_min":     0,
        "setpoint_max":     100,           # 100 = 3450 RPM nominal
        "default_setpoint": 0,
        "pid_defaults":     {"Kc": 1.0, "Ti": 1.0, "Td": 0.0},
        # Actual pump speed in RPM is shown as first extra sensor.
        # Motor power in W is added as a second extra sensor in app.py.
        "extra_sensor_key": "pump_speed_rpm",
    },
}

# ── Data logging ───────────────────────────────────────────────────────────────
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

# ── Pressure panel layout ──────────────────────────────────────────────────────
# Controls the order sensors appear left-to-right in the horizontal panel.
# Must be keys from SENSOR_CONFIGS.
PRESSURE_PANEL_SENSORS = [
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
