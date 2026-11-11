"""Pump Cart #1
"""

from pathlib import Path
from apps.pump_cart import PumpCartFrame
from core.numeric_entry import finite_number

FrameClass = PumpCartFrame
SYSTEM_NAME = "Pump Cart #1"
WINDOW_SIZE = "1320x700"
DEVICE_MANAGER_ENABLED = False
_ROOT = Path(__file__).resolve().parents[1]
PID_IMAGE = str(_ROOT / "PI diagrams" / "Pump_Cart_V1.png")
LOGO_FILE = str(_ROOT / "assets" / "tipice_logo.png")
LOG_FOLDER = "PumpCart1_LoggedData"
ETHERNET_ADDRESS = ""
MAIN_POWER_PIN = ""  # Main 1–7 use the DIN rail supply.

# 4–20 mA, assuming the lab's 118 mV/mA current receiver on AIN3.
MAIN_FLOW_SIGNAL_V = (0.472, 2.360)
# Measured motor-power signal: 8.0 mV at 0 kW, 334 mV at 1.5 kW.
PUMP_POWER_SIGNAL_V = (0.008, 0.334)

# GS4 AO2 motor-speed feedback, 4.34–19.62 mA for 0–4390 RPM.
# The workbook specifies an LJTick-CurrentShunt on AIN2.
PUMP_SPEED_VOLTS_PER_MA = 0.118
# Type K thermocouple through the InAmp module, with its output on AIN1.
TEMPERATURE_PIN = "AIN1"
INAMP_GAIN = 51.0
INAMP_OFFSET_V = 1.25
# Omega M-5204/0615, p. 14: standard FMG94 K-factor. Use the nameplate
# value instead if the installed meter has a custom pulse rate.
BYPASS_PULSES_PER_GALLON = 750.0
BYPASS_DIO = "DIO0"  # T7 FIO0; use "DIO1" for FIO1 if rewired.
BYPASS_CLOCK_HZ = 80_000_000  # T7 Clock0, divisor 1.
BYPASS_NO_PULSE_TIMEOUT_S = 1.0  # Above two periods at the 0.52 GPM output threshold.
PRESSURE_SIGNAL_V = (0.472, 2.360)  # 4–20 mA at 118 mV/mA.
VALVE_OUTPUT_V = (0.0, 5.0)  # V2C input assumption; verify on the cart.
PUMP_SPEED_OUTPUT_V = (0.0, 5.0)  # T7 DAC1 voltage span.
MANUAL_OUTPUT_REQUIRES_PUMP = False
OUTPUT_LABEL = "Valve"
COLD_JUNCTION_REGISTER = "TEMPERATURE_DEVICE_K"
_cj_temp_c = [float("nan")]


def _linear(voltage, endpoints, low, high):
    if endpoints is None:
        raise ValueError("Signal scaling has not been confirmed")
    v0, v1 = map(finite_number, endpoints)
    if v1 <= v0:
        raise ValueError("Invalid signal endpoints")
    return low + (finite_number(voltage) - v0) * (high - low) / (v1 - v0)


def _main_flow(voltage):
    voltage = finite_number(voltage)
    flow = _linear(voltage, MAIN_FLOW_SIGNAL_V, 0.79, 79.0)
    # Allow some headroom below 4 mA, but treat a lost loop as a read fault.
    if voltage < 0.9 * MAIN_FLOW_SIGNAL_V[0]:
        raise ValueError("Main flow signal below 3.6 mA")
    return max(0.0, flow)


def _pressure(voltage):
    voltage = finite_number(voltage)
    if voltage < 0.9 * PRESSURE_SIGNAL_V[0]:
        raise ValueError("Pressure signal below 3.6 mA")
    return max(0.0, _linear(voltage, PRESSURE_SIGNAL_V, 0, 50))


def _pump_speed_rpm(voltage):
    current_ma = finite_number(voltage) / PUMP_SPEED_VOLTS_PER_MA
    if current_ma < 4.0:
        raise ValueError("Pump speed signal below the 4 mA loop minimum")
    rpm = (current_ma - 4.34) * 4390.0 / (19.62 - 4.34)
    return max(0.0, rpm)


def _pump_motor_power(voltage):
    """Convert the AIN4 power signal from volts to watts."""
    return max(0.0, _linear(voltage, PUMP_POWER_SIGNAL_V, 0, 1500))


def _temperature(voltage):
    if INAMP_GAIN is None or INAMP_OFFSET_V is None:
        raise ValueError("Thermocouple amplifier settings have not been confirmed")
    from labjack import ljm
    tc_v = (finite_number(voltage) - INAMP_OFFSET_V) / INAMP_GAIN
    return ljm.tcVoltsToTemp(6004, tc_v, finite_number(_cj_temp_c[0]) + 273.15) - 273.15


def _bypass_flow(period_seconds):
    if BYPASS_PULSES_PER_GALLON is None:
        raise ValueError("Bypass pulse calibration has not been confirmed")
    period = finite_number(period_seconds)
    pulses = finite_number(BYPASS_PULSES_PER_GALLON)
    if period < 0 or pulses <= 0:
        raise ValueError("No valid bypass pulse period")
    return 60.0 / (period * pulses) if period else 0.0


PRESSURE_CHANNELS = {
    "pump_dp": ("Pump ΔP", "AIN7"), "pipe_dp": ("Pipe ΔP", "AIN6"),
    "bypass_dp": ("Bypass ΔP", "AIN8"),
    "tee_dp": ("Tee ΔP", "AIN9"), "u_dp": ("U ΔP", "AIN10"),
    "el_dp": ("Elbow ΔP", "AIN11"), "globe_valve_dp": ("Globe valve ΔP", "AIN12"),
    "ball_valve_dp": ("Ball valve ΔP", "AIN13"),
}
SENSOR_CONFIGS = {
    **{key: {"label": label, "unit": "psi", "pin": pin,
             "calibration": _pressure}
       for key, (label, pin) in PRESSURE_CHANNELS.items()},
    "fluid_temperature": {"label": "Temperature", "unit": "°C", "pin": TEMPERATURE_PIN,
                          "calibration": _temperature},
    "bypass_flowrate": {"label": "Bypass flow", "unit": "GPM", "pin": f"{BYPASS_DIO}_EF_READ_A_AND_RESET",
                        "calibration": _bypass_flow},
    "pump_speed_rpm": {"label": "Pump speed", "unit": "RPM", "pin": "AIN2",
                       "calibration": _pump_speed_rpm},
    "pump_motor_power": {"label": "Motor power", "unit": "W", "pin": "AIN4",
                         "calibration": _pump_motor_power},
}


def pending_inputs():
    return {key for key, pending in {
        "flowrate": MAIN_FLOW_SIGNAL_V is None,
        "pump_motor_power": PUMP_POWER_SIGNAL_V is None,
        "fluid_temperature": not TEMPERATURE_PIN or INAMP_GAIN is None or INAMP_OFFSET_V is None,
        "bypass_flowrate": BYPASS_PULSES_PER_GALLON is None,
    }.items() if pending}


SYSTEM_SWITCHES = [
    {"key": "pump", "label": "Pump", "type": "toggle", "pin": "FIO2",
     "active_value": 1.0, "inactive_value": 0.0, "default": False},
]
CONTROL_LOOP_CONFIGS = {
    "flowrate": {
        "label": "Main Flow Control", "unit": "GPM", "input_pin": "AIN3",
        "output_pin": "DAC0", "calibration": _main_flow,
        "setpoint_min": 0.0, "setpoint_max": 79.0, "default_setpoint": 0.0,
        "output_min": VALVE_OUTPUT_V[0], "output_max": VALVE_OUTPUT_V[1],
        "pid_defaults": {"Kc": 0.05, "Ti": 0.025, "Td": 0.0},  # Commission before AUTO.
    },
}
MANUAL_ANALOG_OUTPUTS = {
    "pump_speed": {"label": "Speed setpoint", "pin": "DAC1", "unit": "%",
                   "max_val": 100.0, "scale": 100.0 / PUMP_SPEED_OUTPUT_V[1], "default": 0},
}
MANUAL_ANALOG_OUTPUTS_PANEL = {"outputs": ["pump_speed"]}
AIN_CONFIGS = {
    "AIN1": {"NEGATIVE_CH": 199, "RANGE": 10.0, "RESOLUTION_INDEX": 8},
    **{f"AIN{i}": {"NEGATIVE_CH": 199, "RANGE": 10.0, "RESOLUTION_INDEX": 1}
       for i in range(2, 14)},
}
# Rising-edge Frequency In on FIO0 (DIO0), explicitly using Clock0.
# READ_A_AND_RESET returns clock ticks and clears the old result, so a stopped
# pulse train can be detected. The app converts ticks to seconds before calibration.
# https://support.labjack.com/docs/13-2-5-frequency-in-t-series-datasheet
BYPASS_INPUT_SETUP = (
    (f"{BYPASS_DIO}_EF_ENABLE", 0), ("DIO_EF_CLOCK0_ENABLE", 0),
    ("DIO_EF_CLOCK0_DIVISOR", 1), ("DIO_EF_CLOCK0_ROLL_VALUE", 0),
    ("DIO_EF_CLOCK0_OPTIONS", 0), ("DIO_EF_CLOCK0_ENABLE", 1),
    (f"{BYPASS_DIO}_EF_INDEX", 3), (f"{BYPASS_DIO}_EF_OPTIONS", 0),
    (f"{BYPASS_DIO}_EF_CONFIG_A", 0), (f"{BYPASS_DIO}_EF_ENABLE", 1),
)
# Resolution-independent layout: the 1791×1083 export is 3× this logical size.
# Re-exporting the same crop at a higher resolution does not move the overlays.
DIAGRAM_SIZE = (597, 361)
# The virtual bounds include space for the fixed-size readouts outside the PNG.
DIAGRAM_BOUNDS = (-160, -95, 760, 455)
PUMP_STATUS_POSITION = (185, 310)
# key, label, numeric-field center, pipe tap, leader's card edge.
# Positions use logical image coordinates. Bottom fields share one baseline.
# Four fittings retain approximate tap positions, marked *. The user located
# elbow ΔP at the bottom-left elbow, just below the tee.
DIAGRAM_READOUTS = (
    ("ball_valve_dp", "Ball valve ΔP", (133, -40), (133, 25), "bottom"),
    ("globe_valve_dp", "Globe valve ΔP", (272, -40), (272, 25), "bottom"),
    ("valve", "Valve command", (425, -40), (425, 6), "bottom"),
    ("flowrate", "Main flow", (660, 69), (539, 69), "left"),
    ("fluid_temperature", "Temperature", (660, 190), (441, 190), "left"),
    ("bypass_flowrate", "Bypass flow", (470, 405), (395, 319), "top"),
    ("pump_dp", "Pump ΔP", (185, 165), (185, 234), "bottom"),
    ("el_dp", "Elbow ΔP", (-70, 405), (10, 349), "top"),
    ("tee_dp", "Tee ΔP *", (-70, 323), (10, 323), "right"),
    ("bypass_dp", "Bypass ΔP *", (100, 405), (195, 334), "top"),
    ("pipe_dp", "Pipe ΔP *", (285, 405), (266, 323), "top"),
    ("u_dp", "U ΔP *", (660, 317), (492, 317), "left"),
)
# Directed, OPEN paths following the drawing's arrows. No diagonal closure.
FLOW_PATHS = {
    "supply": ((333, 221), (333, 262), (211, 262), (185, 260), (149, 243),
               (86, 243), (86, 69), (594, 69), (594, 31), (10, 31), (10, 323)),
    "pipe": ((10, 323), (492, 323), (492, 310), (441, 310)),
    "bypass": ((10, 323), (10, 349), (137, 349), (289, 310), (441, 310)),
    "return": ((441, 310), (441, 87.5), (378, 87.5), (378, 118)),
}
LOG_COLUMNS = {
    **{f"{s['label']} ({s['unit']})": ("sensor", key) for key, s in SENSOR_CONFIGS.items()},
    "Main flow (GPM)": ("loop", "flowrate"),
    "Main flow setpoint (GPM)": ("loop_setpoint", "flowrate"),
    "Valve command (%)": ("loop_valve", "flowrate"),
    "Flow Kc": ("loop_kc", "flowrate"), "Flow Ti (min)": ("loop_ti", "flowrate"),
    "Flow Td (min)": ("loop_td", "flowrate"),
}
