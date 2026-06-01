# config.py — Shell and Tube Heat Exchanger System Configuration
# ==============================================================
# Fill in every value marked TODO before running the GUI.
# All other files (sensor.py, control_loop.py, pid_controller.py,
# labjack_interface.py, ui_builders.py, data_logger.py, main.py)
# are unchanged 

# ── System identity ────────────────────────────────────────────────────────────
SYSTEM_NAME = "Shell and Tube Heat Exchanger"
LOGO_FILE   = "assets/tipice_logo.png"
LOG_FOLDER  = "ShellTubeHX_LoggedData"

# ── LabJack connection ─────────────────────────────────────────────────────────
ETHERNET_ADDRESS = "TODO"          # e.g. "10.8.112.XX"

# ── Fixed digital outputs ──────────────────────────────────────────────────────
MAIN_POWER_PIN  = "TODO"           # e.g. "FIO6"
PUMP_SWITCH_PIN = "TODO"           # AMT369E-98 pump switch — e.g. "FIO5"

# ── Read-only sensor displays ──────────────────────────────────────────────────
# Calibration: lambda v: ...  where v is the raw voltage from the LabJack AIN pin.
#
# For 4-20 mA sensors (e.g. OMEGA PX5100-150GI, PX409-015DWUI):
#   Wire a 250 Ω shunt resistor across the AIN pin to convert mA → voltage:
#     4 mA  → 1.0 V  (min engineering value)
#     20 mA → 5.0 V  (max engineering value)
#   Then: slope = (eng_max - eng_min) / (5.0 - 1.0)
#         intercept = eng_min - slope * 1.0
#   calibration: lambda v: slope * v + intercept
#
# For OMEGA K-type thermocouples: use the appropriate signal conditioner
#   output range and derive slope/intercept from its datasheet.
#
# For FLOWSERVE 520MD flowmeter: derive from its 4-20 mA output range.

SENSOR_CONFIGS = {

    "water_inlet_temp": {
        "label":       "Water Inlet Temp",
        "unit":        "C",
        "pin":         "TODO",             # e.g. "AIN0"
        "calibration": lambda v: v,        # TODO: replace with OMEGA K conditioner equation
        # Example: lambda v: slope * v + intercept
    },

    "water_outlet_temp": {
        "label":       "Water Outlet Temp",
        "unit":        "C",
        "pin":         "TODO",             # e.g. "AIN1"
        "calibration": lambda v: v,        # TODO: replace with OMEGA K conditioner equation
    },

    "house_steam_pressure": {
        "label":       "House Steam Pressure",
        "unit":        "psig",
        "pin":         "TODO",             # e.g. "AIN2"  (4-20 mA via 250 Ω shunt → 1-5 V)
        # OMEGA PX5100-150GI: 0–150 psig, 4–20 mA output
        # With 250 Ω shunt: 1.0 V = 0 psig, 5.0 V = 150 psig
        # slope = 150 / (5.0 - 1.0) = 37.5,  intercept = 0 - 37.5 * 1.0 = -37.5
        "calibration": lambda v: v,        # TODO: lambda v: 37.5 * v - 37.5
    },

    "tube_side_pressure_drop": {
        "label":       "Tube-Side Pressure Drop",
        "unit":        "psig",
        "pin":         "TODO",             # e.g. "AIN3"  (4-20 mA via 250 Ω shunt → 1-5 V)
        # OMEGA PX409-015DWUI: 0–15 psid, 4–20 mA output
        # slope = 15 / (5.0 - 1.0) = 3.75,  intercept = 0 - 3.75 * 1.0 = -3.75
        "calibration": lambda v: v,        # TODO: lambda v: 3.75 * v - 3.75
    },

    "makeup_temperature": {
        "label":       "Makeup Temperature",
        "unit":        "C",
        "pin":         "TODO",             # e.g. "AIN4"
        "calibration": lambda v: v,        # TODO: replace with OMEGA K conditioner equation
    },

    "makeup_flowrate": {
        "label":       "Makeup Flowrate",
        "unit":        "L/min",
        "pin":         "TODO",             # e.g. "AIN5"  (4-20 mA via 250 Ω shunt → 1-5 V)
        # FLOWSERVE 520MD: derive slope/intercept from its rated flow range
        "calibration": lambda v: v,        # TODO: lambda v: slope * v + intercept
    },
}

# ── Closed-loop PID control channels ──────────────────────────────────────────
CONTROL_LOOP_CONFIGS = {

    "level": {
        "label":            "Level",
        "unit":             "ft",
        "input_pin":        "TODO",        # e.g. "AIN6"  — OMEGA LVU809 TYPE 4X
        "output_pin":       "TODO",        # e.g. "DAC0"  — FLOWSERVE 520MD valve
        # OMEGA LVU809 TYPE 4X: derive voltage output range from datasheet
        "calibration":      lambda v: v,   # TODO: lambda v: slope * v + intercept
        "setpoint_min":     0,             # TODO: set appropriate min level in ft
        "setpoint_max":     10,            # TODO: set appropriate max level in ft
        "default_setpoint": 0,
        "pid_defaults":     {"Kc": -75.0, "Ti": 0.005, "Td": 0.0},
        # Kc is negative → reverse acting (high level closes valve)
        "extra_sensor_key": None,
    },

    "flowrate": {
        "label":            "Flowrate",
        "unit":             "GPM",
        "input_pin":        "TODO",        # e.g. "AIN7"  — OMEGA IS2.140
        "output_pin":       "TODO",        # e.g. "DAC1"  — FLOWSERVE 520MD valve
        # OMEGA IS2.140: derive voltage output range from datasheet
        "calibration":      lambda v: v,   # TODO: lambda v: slope * v + intercept
        "setpoint_min":     0,             # TODO: set appropriate min flowrate in GPM
        "setpoint_max":     50,            # TODO: set appropriate max flowrate in GPM
        "default_setpoint": 0,
        "pid_defaults":     {"Kc": 0.74, "Ti": 0.036, "Td": 0.0},
        "extra_sensor_key": None,
    },

    "steam_pressure": {
        "label":            "Steam Pressure",
        "unit":             "psig",
        "input_pin":        "TODO",        # e.g. reuse AIN2 (same sensor as house_steam_pressure)
        "output_pin":       "TODO",        # e.g. DAC0 or DAC1 — FLOWSERVE 520MD valve
        # OMEGA PX5100-150GI: same as house_steam_pressure sensor
        # slope = 37.5, intercept = -37.5  (once shunt resistor is confirmed)
        "calibration":      lambda v: v,   # TODO: lambda v: 37.5 * v - 37.5
        "setpoint_min":     0,             # TODO: set appropriate min pressure in psig
        "setpoint_max":     150,
        "default_setpoint": 0,
        "pid_defaults":     {"Kc": 0.5, "Ti": 0.05, "Td": 0.0},
        "extra_sensor_key": "house_steam_pressure",  # show live steam pressure in this panel
    },
}

# ── Data logging ───────────────────────────────────────────────────────────────
# Add or remove rows to control what appears in the CSV.
# ("sensor", key) → reads from SENSOR_CONFIGS[key]
# ("loop",   key) → reads the live measurement from CONTROL_LOOP_CONFIGS[key]
LOG_COLUMNS = {
    "Water Inlet Temp (C)":        ("sensor", "water_inlet_temp"),
    "Water Outlet Temp (C)":       ("sensor", "water_outlet_temp"),
    "House Steam Pressure (psig)": ("sensor", "house_steam_pressure"),
    "Tube-Side dP (psig)":         ("sensor", "tube_side_pressure_drop"),
    "Makeup Temp (C)":             ("sensor", "makeup_temperature"),
    "Makeup Flowrate (L/min)":     ("sensor", "makeup_flowrate"),
    "Level (ft)":                  ("loop",   "level"),
    "Flowrate (GPM)":              ("loop",   "flowrate"),
    "Steam Pressure (psig)":       ("loop",   "steam_pressure"),
}
