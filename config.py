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

# ── LJTick-InAmp constants ─────────────────────────────────────────────────────
INAMP_GAIN     = 51.0
INAMP_OFFSET_V = 1.25   # built-in 1.25 V offset of the LJTick-InAmp 3

# ── Cold junction temperature ──────────────────────────────────────────────────
# Stored in a mutable container so app.py can update it each cycle and the
# calibration lambdas below always read the latest value.
_cj_temp_c = [25.0]   # [0] is updated by app.py from TEMPERATURE_DEVICE_K

# ── Type K thermocouple conversion ─────────────────────────────────────────────
def _type_k_temp(amp_voltage_v):
    """
    Convert an amplified InAmp output voltage to °C.
    Extracts the true TC voltage using the inverse transfer function,
    then applies a linear Type K sensitivity with cold junction compensation.
    """
    tc_voltage_v = (amp_voltage_v - INAMP_OFFSET_V) / INAMP_GAIN
    return _cj_temp_c[0] + tc_voltage_v / 41.276e-6

# ── AIN channel configuration ──────────────────────────────────────────────────
# Applied once after the LabJack connects.
# Add an entry for every AIN channel that needs non-default settings.
AIN_CONFIGS = {
    # Thermocouples (LJTCS with LJTick-InAmp 3)
    "AIN0": {"NEGATIVE_CH": 199, "RANGE": 10.0, "RESOLUTION_INDEX": 8},
    "AIN1": {"NEGATIVE_CH": 199, "RANGE": 10.0, "RESOLUTION_INDEX": 8},
    # Makeup sensors (LJTCS current loop)
    "AIN2": {"NEGATIVE_CH": 199,"RANGE": 10.0},
    "AIN3": {"NEGATIVE_CH": 199,"RANGE": 10.0},
    "AIN4": {"NEGATIVE_CH": 199,"RANGE": 10.0}, # Flowrate sensor (LJTCS current loop)
    'AIN5': {"NEGATIVE_CH": 199,"RANGE": 10.0}, # Level sensor (LJTCS current loop)
    'AIN6': {"NEGATIVE_CH": 199,"RANGE": 10.0}, # Tube-side pressure drop sensor (LJTCS current loop)
    'AIN7': {"NEGATIVE_CH": 199,"RANGE": 10.0}, # Steam pressure sensor (LJTCS current loop)
}

# Register name for the T7's internal temperature sensor (cold junction)
COLD_JUNCTION_REGISTER = "TEMPERATURE_DEVICE_K"

# ── Flowrate sensor constants (LJTCS, AIN4) ───────────────────────────────────
_FLOW_Q_MIN = 0.79    # GPM at 4 mA (lower sensor limit)
_FLOW_Q_MAX = 79.00   # GPM at 20 mA (upper sensor limit)
_FLOW_V_MIN = 0.472   # Voltage at 4 mA
_FLOW_V_MAX = 2.360   # Voltage at 20 mA

def _flowrate_gpm(v):
    """
    Convert LJTCS output voltage to GPM.
    Returns 0.0 when voltage is below the sensor's lower limit,
    preventing noise near zero from showing a false low reading.
    """
    if v < _FLOW_V_MIN:
        return 0.0
    return _FLOW_Q_MIN + (v - _FLOW_V_MIN) * (_FLOW_Q_MAX - _FLOW_Q_MIN) / (_FLOW_V_MAX - _FLOW_V_MIN)

# ── Pressure sensor constants (LJTCS, 4-20 mA) ───────────────────────────────
_PRESSURE_V_MIN      = 0.472   # Voltage at 4 mA
_PRESSURE_V_MAX      = 2.360   # Voltage at 20 mA
_PRESSURE_ZERO_MA    = 4.05    # Zero-floor cutoff in mA

def _make_pressure_cal(p_min, p_max):
    """
    Returns a calibration lambda for a pressure sensor with the given PSI range.
    Applies zero-floor cutoff and safety clamp matching scale_pressure() logic.
    """
    return lambda v: (
        0.0 if 8.475 * v <= _PRESSURE_ZERO_MA
        else min(p_max, p_min + (v - _PRESSURE_V_MIN) * (p_max - p_min) / (_PRESSURE_V_MAX - _PRESSURE_V_MIN))
    )


SENSOR_CONFIGS = {

    "water_inlet_temp": {
        "label":       "Water Inlet Temp",
        "unit":        "°C",
        "pin":         "AIN1",             # e.g. "AIN0"
        "calibration": lambda v: _type_k_temp(v),        
       
    },

    "water_outlet_temp": {
        "label":       "Water Outlet Temp",
        "unit":        "°C",
        "pin":         "AIN0",             # e.g. "AIN1"
        "calibration": lambda v: _type_k_temp(v),        
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
        "pin":         "AIN6",          
        "calibration": _make_pressure_cal(0.0, 15.0),        # TODO: lambda v: 3.75 * v - 3.75
    },

    "makeup_temperature": {
        "label":       "Makeup Temperature",
        "unit":        "°C",
        "pin":         "AIN2",
        "calibration": lambda v: (((4 + ((v * 8.475 - 4) / 16.0) * (176 - 4))) - 32) * 5 / 9,
        # Converts voltage → mA → °F → °C
        # Step 1: mA  = v * 8.475
        # Step 2: °F  = 4 + ((mA - 4) / 16.0) * (176 - 4)
        # Step 3: °C  = (°F - 32) * 5/9
    },

    "makeup_flowrate": {
        "label":       "Makeup Flowrate",
        "unit":        "GPM",
        "pin":         "AIN3",             
        "calibration": lambda v: max(0.0, ((v * 8.475 - 4) / 16.0) * 6.6),
            # Converts voltage → mA → GPM
            # Step 1: mA  = v * 8.475
            # Step 2: GPM = ((mA - 4) / 16.0) * 6.6,  floored at 0
    },
}

# ── Closed-loop PID control channels ──────────────────────────────────────────
CONTROL_LOOP_CONFIGS = {

    "level": {
        "label":            "Level",
        "unit":             "ft",
        "input_pin":        "AIN5",        # e.g. "AIN6"  — OMEGA LVU809 TYPE 4X
        "output_pin":       "DAC0",        # e.g. "DAC0"  — FLOWSERVE 520MD valve
        # OMEGA LVU809 TYPE 4X: derive voltage output range from datasheet
        "calibration":      lambda v: 0.0 if 8.475 * v <= 4.05 else min(1.96, 0.0 + (v - 0.472) * (1.96 - 0.0) / (2.360 - 0.472)),
        "setpoint_min":     0,             # TODO: set appropriate min level in ft
        "setpoint_max":     1.96,            # TODO: set appropriate max level in ft
        "default_setpoint": 0,
        "pid_defaults":     {"Kc": -75.0, "Ti": 0.005, "Td": 0.0},
        # Kc is negative → reverse acting (high level closes valve)
        "extra_sensor_key": None,
    },

    "flowrate": {
        "label":            "Flowrate",
        "unit":             "GPM",
        "input_pin":        "AIN4",        
        "output_pin":       "DAC1",        # e.g. "DAC1"  — FLOWSERVE 520MD valve
        # OMEGA IS2.140: derive voltage output range from datasheet
        "calibration":      _flowrate_gpm,   #: lambda v: slope * v + intercept
        "setpoint_min":     0,             # TODO: set appropriate min flowrate in GPM
        "setpoint_max":     79.00,            # TODO: set appropriate max flowrate in GPM
        "default_setpoint": 0,
        "pid_defaults":     {"Kc": 0.74, "Ti": 0.036, "Td": 0.0},
        "extra_sensor_key": None,
    },

    "steam_pressure": {
        "label":            "Steam Pressure",
        "unit":             "psig",
        "input_pin":        "AIN7",        # e.g. reuse AIN2 (same sensor as house_steam_pressure)
        "output_pin":       "TDAC0",        # e.g. DAC0 or DAC1 — FLOWSERVE 520MD valve
        # OMEGA PX5100-150GI: same as house_steam_pressure sensor
        # slope = 37.5, intercept = -37.5  (once shunt resistor is confirmed)
        "calibration":      _make_pressure_cal(0.0, 150.0),
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
