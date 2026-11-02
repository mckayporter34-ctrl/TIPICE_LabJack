"""Pump Cart #1, development configuration.

Source: Development/New_system_implementation.xlsx, PUMP CARTS, rows 3–74.
Unspecified signal endpoints remain None. See docs/pump-cart.md.
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

# LabJack voltages at the engineering-range endpoints: absent from the sheet.
MAIN_FLOW_SIGNAL_V = None  # TODO: 0.79–79 GPM signal endpoints
PUMP_SPEED_SIGNAL_V = None  # TODO: 0–3450 RPM signal endpoints
PUMP_PRESSURE_SIGNAL_V = None  # TODO: 0–50 psid signal endpoints
PUMP_POWER_SIGNAL_V = None  # TODO: 0–630 W signal endpoints
TEMPERATURE_PIN = "AIN0"  # Confirmed by the user on November 2, 2026.
INAMP_GAIN = 51.0  # Existing laboratory InAmp3 convention; verify fitted gain.
INAMP_OFFSET_V = 1.25
BYPASS_PULSES_PER_GALLON = None  # TODO: confirm the installed FMG94 pulse setting.
PRESSURE_SIGNAL_V = (0.0, 2.360)  # Sheet: 0–20 mA, 118-ohm current shunt.
VALVE_OUTPUT_V = (0.0, 5.0)  # V2C input assumption; verify on the cart.
PUMP_SPEED_OUTPUT_V = (0.0, 5.0)  # V2C input assumption; verify on the cart.
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
    return _linear(voltage, MAIN_FLOW_SIGNAL_V, 0.79, 79.0)


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
    if period <= 0 or pulses <= 0:
        raise ValueError("No valid bypass pulse period")
    return 60.0 / (period * pulses)


PRESSURE_CHANNELS = {
    "pump_dp": ("Pump ΔP", "AIN4"), "pipe_dp": ("Pipe ΔP", "AIN6"),
    "control_valve_dp": ("Control valve ΔP", "AIN7"), "bypass_dp": ("Bypass ΔP", "AIN8"),
    "tee_dp": ("Tee ΔP", "AIN9"), "u_dp": ("U ΔP", "AIN10"),
    "el_dp": ("Elbow ΔP", "AIN11"), "globe_valve_dp": ("Globe valve ΔP", "AIN12"),
    "ball_valve_dp": ("Ball valve ΔP", "AIN13"),
}
SENSOR_CONFIGS = {
    **{key: {"label": label, "unit": "psid", "pin": pin,
             "calibration": (lambda v: _linear(v, PUMP_PRESSURE_SIGNAL_V, 0, 50))
             if key == "pump_dp" else (lambda v: _linear(v, PRESSURE_SIGNAL_V, 0, 50))}
       for key, (label, pin) in PRESSURE_CHANNELS.items()},
    "fluid_temperature": {"label": "Temperature", "unit": "°C", "pin": TEMPERATURE_PIN,
                          "calibration": _temperature},
    "bypass_flowrate": {"label": "Bypass flow", "unit": "GPM", "pin": "DIO0_EF_READ_A_F",
                        "calibration": _bypass_flow},
    "pump_speed_rpm": {"label": "Pump speed", "unit": "RPM", "pin": "AIN2",
                       "calibration": lambda v: _linear(v, PUMP_SPEED_SIGNAL_V, 0, 3450)},
    "pump_motor_power": {"label": "Motor power", "unit": "W", "pin": "AIN5",
                         "calibration": lambda v: _linear(v, PUMP_POWER_SIGNAL_V, 0, 630)},
}


def pending_inputs():
    return {key for key, pending in {
        "flowrate": MAIN_FLOW_SIGNAL_V is None,
        "pump_dp": PUMP_PRESSURE_SIGNAL_V is None,
        "pump_speed_rpm": PUMP_SPEED_SIGNAL_V is None,
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
        "pid_defaults": {"Kc": 0.05, "Ti": 0.05, "Td": 0.0},  # Commission before AUTO.
    },
}
MANUAL_ANALOG_OUTPUTS = {
    "pump_speed": {"label": "Pump speed", "pin": "DAC1", "scale": 20.0, "default": 0},
}
MANUAL_ANALOG_OUTPUTS_PANEL = {"outputs": ["pump_speed"]}
AIN_CONFIGS = {
    "AIN0": {"NEGATIVE_CH": 199, "RANGE": 10.0, "RESOLUTION_INDEX": 8},
    **{f"AIN{i}": {"NEGATIVE_CH": 199, "RANGE": 10.0, "RESOLUTION_INDEX": 1}
       for i in range(2, 14)},
}
# Frequency In on FIO0 (DIO0). READ_A_F returns period in seconds, not logic state.
# https://support.labjack.com/docs/13-2-5-frequency-in-t-series-datasheet
BYPASS_INPUT_SETUP = (
    ("DIO0_EF_ENABLE", 0), ("DIO_EF_CLOCK0_ENABLE", 0),
    ("DIO_EF_CLOCK0_DIVISOR", 1), ("DIO_EF_CLOCK0_ROLL_VALUE", 0),
    ("DIO_EF_CLOCK0_ENABLE", 1), ("DIO0_EF_INDEX", 3),
    ("DIO0_EF_CONFIG_A", 0), ("DIO0_EF_ENABLE", 1),
)
# key, label, card position, leader position (source PNG pixels, including margins).
# Four fittings retain approximate tap positions, marked *. The user located
# elbow ΔP at the bottom-left elbow, just below the tee.
DIAGRAM_READOUTS = (
    ("ball_valve_dp", "Ball valve ΔP", (70, -31), (105, 39)),
    ("globe_valve_dp", "Globe valve ΔP", (230, -31), (214, 39)),
    ("control_valve_dp", "Control valve ΔP", (390, -31), (347, 46)),
    ("valve", "Valve command", (550, 0), (334, 5)),
    ("flowrate", "Main flow", (550, 103), (417, 104)),
    ("fluid_temperature", "Temperature", (550, 190), (378, 170)),
    ("bypass_flowrate", "Bypass flow", (385, 345), (311, 273)),
    ("pump_dp", "Pump ΔP", (144, 157), (144, 206)),
    ("el_dp", "Elbow ΔP", (-55, 335), (8, 296)),
    ("tee_dp", "Tee ΔP *", (-55, 266), (8, 276)),
    ("bypass_dp", "Bypass ΔP *", (90, 345), (155, 284)),
    ("pipe_dp", "Pipe ΔP *", (230, 345), (210, 276)),
    ("u_dp", "U ΔP *", (490, 280), (388, 271)),
)
# Directed, OPEN paths following the drawing's arrows. No diagonal closure.
FLOW_PATHS = {
    "supply": ((263, 196), (263, 228), (167, 228), (144, 224), (118, 213),
               (68, 213), (68, 76), (467, 76), (467, 46), (8, 46), (8, 276)),
    "pipe": ((8, 276), (388, 276), (388, 266), (348, 266)),
    "bypass": ((8, 276), (8, 296), (108, 296), (228, 266), (348, 266)),
    "return": ((348, 266), (348, 90), (298, 90), (298, 110)),
}
LOG_COLUMNS = {
    **{f"{s['label']} ({s['unit']})": ("sensor", key) for key, s in SENSOR_CONFIGS.items()},
    "Main flow (GPM)": ("loop", "flowrate"),
    "Main flow setpoint (GPM)": ("loop_setpoint", "flowrate"),
    "Valve command (%)": ("loop_valve", "flowrate"),
    "Flow Kc": ("loop_kc", "flowrate"), "Flow Ti (min)": ("loop_ti", "flowrate"),
    "Flow Td (min)": ("loop_td", "flowrate"),
}
