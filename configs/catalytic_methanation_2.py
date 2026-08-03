# config2.py — Catalytic Methanation System Configuration #2
# ==========================================================

from apps.catalytic_methanation import CatalyticMethanationRedesignFrame

SYSTEM_NAME = "Catalytic Methanation #2"
LOGO_FILE   = "assets/tipice_logo.png"
LOG_FOLDER  = "CatalyticMethanation2_LoggedData"

# Reference to the custom UI frame
FrameClass = CatalyticMethanationRedesignFrame

# LabJack connection
ETHERNET_ADDRESS = "10.8.112.13"

# Pins for custom panels
GC_SELECT_PINS = ["FIO5", "FIO6"]  # LOW (0.0V) = Reactor Exhaust, HIGH (5.0V) = Reactor Feed
HEATER_POWER_PIN = "FIO4"          # 5.0V = ON, 0.0V = OFF

# Layout Grid coordinates
CONTROLS_ROW = 0
CONTROLS_COL = 0

LOGO_ROW = 2
LOGO_COL = 0
LOGO_COLSPAN = 1

DATA_LOGGING_ROW = 0
DATA_LOGGING_COL = 1
DATA_LOGGING_COLSPAN = 1

# Apparatus diagram path & positioning
APPARATUS_IMAGE = "images/Catmeth2_apparatus.jpg"
APPARATUS_IMAGE_ROW = 1
APPARATUS_IMAGE_COL = 0
APPARATUS_IMAGE_COLSPAN = 1

# Manual Analog Outputs for the Gas setpoints
MANUAL_ANALOG_OUTPUTS = {
    "hydrogen_setpoint": {
        "label": "Hydrogen",
        "unit": "SCCM",
        "pin": "TDAC0",
        "scale": 10.0,       # 5V Max = 50 SLPM
        "min_val": 0.0,
        "max_val": 50.0,
        "default": 0.0
    },
    "co2_setpoint": {
        "label": "Carbon Dioxide",
        "unit": "SCCM",
        "pin": "TDAC1",
        "scale": 2.0,        # 5V Max = 10 SLPM
        "min_val": 0.0,
        "max_val": 10.0,
        "default": 0.0
    },
    "helium_setpoint": {
        "label": "Helium",
        "unit": "SCCM",
        "pin": "TDAC2",
        "scale": 40.0,        # 5V Max = 10 SLPM
        "min_val": 0.0,
        "max_val": 200.0,
        "default": 0.0
    }
}
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
    Convert LJTick-InAmp 3 output to °C using NIST Type K polynomial.
    Accurate over 0-1372°C, replacing the linear 41.276 µV/°C approximation.
    """
    # Extract true TC microvoltage from InAmp output
    tc_voltage_v  = (amp_voltage_v - INAMP_OFFSET_V) / INAMP_GAIN
    tc_voltage_uv = tc_voltage_v * 1e6   # convert to µV

    # Add cold junction compensation in µV (inverse NIST: CJ temp → µV)
    cj_uv = _temp_to_type_k_uv(_cj_temp_c[0])
    total_uv = tc_voltage_uv + cj_uv

    # NIST Type K polynomial: µV → °C  (valid 0 to 20644 µV = 0 to 500°C)
    coeffs = [
         0.0000000E+00,
         2.5083550E-02,
         7.8601060E-08,
        -2.5031310E-10,
         8.3152700E-14,
        -1.2280340E-17,
         9.8040360E-22,
        -4.4130300E-26,
         1.0577340E-30,
        -1.0527550E-35,
    ]
    temp_c = sum(c * (total_uv ** i) for i, c in enumerate(coeffs))
    return temp_c


def _temp_to_type_k_uv(temp_c):
    """
    Convert a temperature in °C to Type K thermocouple µV (for CJ compensation).
    Valid 0–500°C.
    """
    coeffs = [
        -1.7600413686E+01,
         3.8921204975E+01,
         1.8558770032E-02,
        -9.9457592874E-05,
         3.1840945719E-07,
        -5.6072844889E-10,
         5.6075059059E-13,
        -3.2020720003E-16,
         9.7151147152E-20,
        -1.2104721275E-23,
    ]
    return sum(c * (temp_c ** i) for i, c in enumerate(coeffs))

def _make_flow_cal(flow_min, flow_max):
    """
    Returns a calibration lambda for a 4-20 mA flow sensor
    wired through an LJTick-CurrentShunt (5.9 Ω resistor, x20 gain).
    V_min = 4mA * 5.9 * 20 = 0.472V
    V_max = 20mA * 5.9 * 20 = 2.360V
    """
    v_min = 0.545
    v_max = 2.3589
    
    slope     = (flow_max - flow_min) / (v_max - v_min)
    intercept = flow_min - slope * v_min
    
    # Returns a function mapping LabJack voltage directly to flowrate (sccm)
    return lambda v: max(flow_min, slope * v + intercept)

# ── AIN channel configuration ──────────────────────────────────────────────────
# Applied once after the LabJack connects.
# Add an entry for every AIN channel that needs non-default settings.
AIN_CONFIGS = {
    # Thermocouples (LJTCS with LJTick-InAmp 3)
    "AIN0": {"NEGATIVE_CH": 199, "RANGE": 10.0, "RESOLUTION_INDEX": 8}, #reactor temperature
    "AIN1": {"NEGATIVE_CH": 199, "RANGE": 10.0, "RESOLUTION_INDEX": 8}, #heater temperature
    # Sensors (LJTCS current loop)
    "AIN2": {"NEGATIVE_CH": 199,"RANGE": 10.0}, #reactor pressure
    "AIN3": {"NEGATIVE_CH": 199,"RANGE": 10.0}, #H2 actual flow
    "AIN4": {"NEGATIVE_CH": 199,"RANGE": 10.0}, #CO2 actual flow
    'AIN5': {"NEGATIVE_CH": 199,"RANGE": 10.0}, #He actual flow
}

# Register name for the T7's internal temperature sensor (cold junction)
COLD_JUNCTION_REGISTER = "TEMPERATURE_DEVICE_K"

# Read-only sensor definitions
SENSOR_CONFIGS = {
    "reactor_temp_sensor": {
        "label":       "Reactor Temperature",
        "unit":        "°C",
        "pin":         "AIN0",
        "calibration": lambda v: _type_k_temp(v),
    },
    "reactor_pressure_sensor": {
        "label":       "Reactor Pressure",
        "unit":        "psia",
        "pin":         "AIN2",
        "calibration": lambda v: max(0.0, 15.8898 * v + 4.84),
    },
    "heater_temp_sensor": {
        "label":       "Heater Temperature",
        "unit":        "°C",
        "pin":         "AIN1",
        "calibration": lambda v: _type_k_temp(v),
    },

    "hydrogen_actual": {
        "label":       "H2 Actual Flow",
        "unit":        "SCCM",
        "pin":         "AIN3",
        "calibration": _make_flow_cal(0.0, 50.0),  
    },
    "co2_actual": {
        "label":       "CO2 Actual Flow",
        "unit":        "SCCM",
        "pin":         "AIN4",
        "calibration": _make_flow_cal(0.0, 10.0), 
    },
    "helium_actual": {
        "label":       "He Actual Flow",
        "unit":        "SCCM",
        "pin":         "AIN5",
        "calibration": _make_flow_cal(0.0, 200.0),   
    },
}

# PID Control Loops
CONTROL_LOOP_CONFIGS = {
    "pressure": {
        "label":            "Reactor Pressure",
        "unit":             "psia",
        "input_pin":        "AIN2",
        "output_pin":       "DAC0",
        "calibration":      lambda v: max(0.0, 15.8898 * v +4.84 ), #0-30psig, adjusted for absolute pressure + 4.84
        "setpoint_min":     0.0,
        "setpoint_max":     30.0,
        "default_setpoint": 18.4,
        "pid_defaults":     {"Kc": -0.5, "Ti": 0.1, "Td": 0.0},
    },
    "temperature": {
        "label":            "Reactor Temperature",
        "unit":             "°C",
        "input_pin":        "AIN0",
        "output_pin":       "DAC1",
        "calibration":      _type_k_temp,
        "setpoint_min":     0.0,
        "setpoint_max":     500.0,
        "default_setpoint": 0.0,
        "pid_defaults":     {"Kc": 0.2, "Ti": 5.0, "Td": 0.0},
        "extra_sensor_key": "heater_temp_sensor",
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
    "H2 Actual Flow (SCCM)":         ("sensor", "hydrogen_actual"),
    "CO2 Actual Flow (SCCM)":        ("sensor", "co2_actual"),
    "He Actual Flow (SCCM)":         ("sensor", "helium_actual"),
}
