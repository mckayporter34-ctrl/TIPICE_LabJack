# config.py — Catalytic Methanation System Configuration
# ========================================================
# Fill in every value marked TODO before running the GUI.
# All shared files (sensor.py, control_loop.py, pid_controller.py,
# labjack_interface.py, ui_builders.py, data_logger.py, main.py)
# are unchanged from the framework.

# ── System identity ────────────────────────────────────────────────────────────
SYSTEM_NAME = "Catalytic Methanation"
LOGO_FILE   = "assets/tipice_logo.png"
LOG_FOLDER  = "CatalyticMethanation_LoggedData"

# ── LabJack connection ─────────────────────────────────────────────────────────
ETHERNET_ADDRESS = "TODO"          # e.g. "10.8.112.XX"

# ── Fixed digital outputs ──────────────────────────────────────────────────────
MAIN_POWER_PIN   = "TODO"          # main system relay e.g. "FIO0"
GC_SELECT_PIN    = "FIO2"          # 0.0 V = Reactor Feed, 5.0 V = Reactor Exhaust
HEATER_POWER_PIN = "FIO1"          # 5.0 V = ON, 0.0 V = OFF

# ── Manual analog outputs (gas flow setpoints via LJTick-DAC) ─────────────────
# These are setpoint-only outputs — no feedback loop.
# The GUI creates a spinbox and sends voltage = value / scale to the pin.
# TDAC pins output 0–10 V (via LJTick-DAC), so scale accordingly.
MANUAL_ANALOG_OUTPUTS = {
    "hydrogen_setpoint": {
        "label":   "Hydrogen Setpoint",
        "unit":    "SCCM",
        "pin":     "TDAC0",
        "scale":   10.0,         # value / scale = voltage  →  50 SCCM / 10 = 5.0 V
        "min_val": 0.0,
        "max_val": 50.0,
        "default": 0.0,
    },
    "co2_setpoint": {
        "label":   "CO2 Setpoint",
        "unit":    "SCCM",
        "pin":     "TDAC1",
        "scale":   2.0,          # 10 SCCM / 2 = 5.0 V
        "min_val": 0.0,
        "max_val": 10.0,
        "default": 0.0,
    },
    "helium_setpoint": {
        "label":   "Helium Setpoint",
        "unit":    "SCCM",
        "pin":     "TDAC2",
        "scale":   40.0,         # 200 SCCM / 40 = 5.0 V
        "min_val": 0.0,
        "max_val": 200.0,
        "default": 0.0,
    },
}

# ── LJTick-InAmp 3 constants ───────────────────────────────────────────────────
INAMP_GAIN     = 51.0
INAMP_OFFSET_V = 1.25    # built-in 1.25 V offset of the LJTick-InAmp 3

# ── Cold junction temperature ──────────────────────────────────────────────────
# Stored in a mutable list so app.py can update it every cycle and the
# calibration lambdas below always read the latest value without
# needing to be recreated.
_cj_temp_c = [25.0]      # updated each cycle from TEMPERATURE_DEVICE_K

COLD_JUNCTION_REGISTER = "TEMPERATURE_DEVICE_K"

# ── NIST Type K thermocouple conversion ───────────────────────────────────────
# Accurate from 0–1372°C, replacing the linear 41.276 µV/°C approximation
# which drifts significantly above ~200°C.
#
# The test code confirmed RESOLUTION_INDEX 8 gives correct readings —
# all thermocouple AIN channels must use index 8 for adequate accuracy.

def _temp_to_type_k_uv(temp_c):
    """
    Convert a temperature in °C to Type K thermocouple equivalent µV.
    Used for cold junction compensation.
    NIST ITS-90 coefficients, valid 0–500°C.
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


def _type_k_temp(amp_voltage_v):
    """
    Convert a LJTick-InAmp 3 output voltage to °C.

    Steps:
      1. Extract true TC voltage: Vin = (Vout - 1.25) / 51
      2. Convert to µV
      3. Add cold junction compensation in µV (NIST inverse)
      4. Apply NIST Type K polynomial (µV → °C), valid 0–20644 µV (0–500°C)
    """
    # Step 1 & 2 — extract TC voltage in µV
    tc_voltage_v  = (amp_voltage_v - INAMP_OFFSET_V) / INAMP_GAIN
    tc_voltage_uv = tc_voltage_v * 1e6

    # Step 3 — cold junction compensation
    cj_uv    = _temp_to_type_k_uv(_cj_temp_c[0])
    total_uv = tc_voltage_uv + cj_uv

    # Step 4 — NIST Type K polynomial µV → °C (ITS-90, 0–20644 µV)
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
    return sum(c * (total_uv ** i) for i, c in enumerate(coeffs))


# ── AIN channel configuration ──────────────────────────────────────────────────
# Applied once after the LabJack connects via _configure_ain_channels in app.py.
# RESOLUTION_INDEX 8 confirmed accurate for thermocouples on this system.
AIN_CONFIGS = {
    "AIN0": {"NEGATIVE_CH": 199, "RANGE": 10.0, "RESOLUTION_INDEX": 8},  # Reactor TC
    "AIN1": {"NEGATIVE_CH": 199, "RANGE": 10.0, "RESOLUTION_INDEX": 8},  # Heater TC
    "AIN2": {"NEGATIVE_CH": 199, "RANGE": 10.0},                          # Reactor pressure
    "AIN3": {"NEGATIVE_CH": 199, "RANGE": 10.0},                          # H2 actual flow
    "AIN4": {"NEGATIVE_CH": 199, "RANGE": 10.0},                          # CO2 actual flow
    "AIN5": {"NEGATIVE_CH": 199, "RANGE": 10.0},                          # He actual flow
}

# ── Read-only sensor displays ──────────────────────────────────────────────────
SENSOR_CONFIGS = {

    "reactor_temp_sensor": {
        "label":       "Reactor Temperature",
        "unit":        "°C",
        "pin":         "AIN0",
        "calibration": _type_k_temp,
    },

    "heater_temp_sensor": {
        "label":       "Heater Temperature",
        "unit":        "°C",
        "pin":         "AIN1",
        "calibration": _type_k_temp,
    },

    "reactor_pressure_sensor": {
        "label":       "Reactor Pressure",
        "unit":        "psi",
        "pin":         "AIN2",
        "calibration": lambda v: v * 20.0,   # 0–5 V → 0–100 psi
        # TODO: confirm calibration against pressure gauge
    },

    "hydrogen_actual": {
        "label":       "H2 Actual Flow",
        "unit":        "SCCM",
        "pin":         "AIN3",
        "calibration": lambda v: v * 10.0,   # 0–5 V → 0–50 SCCM
        # TODO: confirm against MFC readout
    },

    "co2_actual": {
        "label":       "CO2 Actual Flow",
        "unit":        "SCCM",
        "pin":         "AIN4",
        "calibration": lambda v: v * 4.0,    # 0–5 V → 0–20 SCCM
        # TODO: confirm against MFC readout
    },

    "helium_actual": {
        "label":       "He Actual Flow",
        "unit":        "SCCM",
        "pin":         "AIN5",
        "calibration": lambda v: v * 2.0,    # 0–5 V → 0–10 SCCM
        # TODO: confirm against MFC readout
    },
}

# ── Closed-loop PID control channels ──────────────────────────────────────────
CONTROL_LOOP_CONFIGS = {

    "pressure": {
        "label":            "Reactor Pressure",
        "unit":             "psi",
        "input_pin":        "AIN2",
        "output_pin":       "DAC0",
        "calibration":      lambda v: v * 20.0,    # 0–5 V → 0–100 psi
        "setpoint_min":     0.0,
        "setpoint_max":     100.0,
        "default_setpoint": 14.7,                  # atmospheric
        "pid_defaults":     {"Kc": -5.0, "Ti": 0.01, "Td": 0.0},
        # Negative Kc: reverse acting — high pressure closes the vent valve
        "extra_sensor_key": None,
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
        "pid_defaults":     {"Kc": 3.0, "Ti": 5.0, "Td": 0.0},
        # Heater temperature shown inside this panel as a second readout
        "extra_sensor_key": "heater_temp_sensor",
        # gate_switch and gate_value are read by app.py to block PID output
        # unless the heater power switch is on.
        "gate_switch":      "heater_power",
        "gate_value":       True,
    },
}

# ── Control loop panel positions (col 3, stacked vertically) ──────────────────
# Change the integer values to rearrange panel order.
LOOP_ROWS = {
    "pressure":    0,
    "temperature": 1,
}

# ── Data logging ───────────────────────────────────────────────────────────────
LOG_COLUMNS = {
    "Reactor Pressure (psi)":    ("loop",   "pressure"),
    "Reactor Temperature (C)":   ("loop",   "temperature"),
    "Heater Temperature (C)":    ("sensor", "heater_temp_sensor"),
    "H2 Actual Flow (SCCM)":     ("sensor", "hydrogen_actual"),
    "CO2 Actual Flow (SCCM)":    ("sensor", "co2_actual"),
    "He Actual Flow (SCCM)":     ("sensor", "helium_actual"),
    "H2 Setpoint (SCCM)":        ("manual", "hydrogen_setpoint"),
    "CO2 Setpoint (SCCM)":       ("manual", "co2_setpoint"),
    "He Setpoint (SCCM)":        ("manual", "helium_setpoint"),
}