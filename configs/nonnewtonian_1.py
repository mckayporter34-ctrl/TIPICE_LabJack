"""Non-Newtonian #1: legacy channels/calibrations with pump-speed flow control."""

from pathlib import Path

from apps.nonnewtonian import NonNewtonianFrame

FrameClass = NonNewtonianFrame
SYSTEM_NAME = "Non-Newtonian Fluids #1"
DEVICE_MANAGER_ENABLED = False  # Development system: connect without student checkout.
_ROOT = Path(__file__).resolve().parents[1]
LOGO_FILE = str(_ROOT / "assets" / "tipice_logo.png")
PID_IMAGE = str(_ROOT / "PI diagrams" / "NonNewtonaion_1_V1.png")
LOG_FOLDER = "NonNewtonian1_LoggedData"
ETHERNET_ADDRESS = "10.8.112.140"
OUTPUT_LABEL = "Pump Speed"
# Overlay anchors are pixels in the 949 × 389 source diagram.
DIAGRAM_READOUTS = [
    ("pressure_drop", "Pressure Drop (in WC)", 666, 115, "s"),
    ("fluid_temperature", "Fluid Temperature (°C)", 353, 374, "n"),
    ("flowrate", "Flowrate (GPM)", 479, 374, "n"),
    ("output", "Pump Speed (%)", 350, 110, "s"),
]
PUMP_STATUS_POSITION = (350, 174)

# There is no separate main-power relay in the legacy GUI. FIO0 enables the pump.
MAIN_POWER_PIN = ""
CONNECT_ENABLES_CONTROLS = True
SYSTEM_SWITCHES = [
    {"key": "pump", "label": "Pump", "type": "toggle", "pin": "FIO0",
     "active_value": 0.0, "inactive_value": 1.0, "default": False},
]


def _temperature_c(voltage):
    return 55.28745157 * voltage - 48.08422656


def _flowrate_gpm(voltage):
    return (53.2187707 * voltage - 25.35572892) * 0.264172


def _pressure_drop_wc(voltage):
    return 3.125 * 8.475 * voltage - 12.5


SENSOR_CONFIGS = {
    "fluid_temperature": {
        "label": "Fluid Temperature", "unit": "°C", "pin": "AIN0",
        "calibration": _temperature_c,
    },
    "pressure_drop": {
        "label": "Pressure Drop", "unit": "in WC", "pin": "AIN2",
        "calibration": _pressure_drop_wc,
    },
}

CONTROL_LOOP_CONFIGS = {
    "flowrate": {
        "label": "Flowrate", "unit": "GPM", "input_pin": "AIN1",
        "output_pin": "TDAC2", "output_min": 0.0, "output_max": 10.0,
        "calibration": _flowrate_gpm,
        # Operator entry range and initial gains are starting values to commission;
        # the legacy GUI supplied neither a flow setpoint range nor PID tuning.
        "setpoint_min": 0.0, "setpoint_max": 30.0, "default_setpoint": 0.0,
        "pid_defaults": {"Kc": 0.1, "Ti": 0.05, "Td": 0.04},
    },
}

# Explicit single-ended settings match the default AIN use in the old GUI.
AIN_CONFIGS = {
    f"AIN{i}": {"NEGATIVE_CH": 199, "RANGE": 10.0}
    for i in range(3)
}

LOG_COLUMNS = {
    "Fluid Temperature (C)": ("sensor", "fluid_temperature"),
    "Pressure Drop (in WC)": ("sensor", "pressure_drop"),
    "Flowrate (GPM)": ("loop", "flowrate"),
    "Flow Setpoint (GPM)": ("loop_setpoint", "flowrate"),
    "Pump Speed Command (%)": ("loop_valve", "flowrate"),
    "Flow Kc (V/GPM)": ("loop_kc", "flowrate"),
    "Flow Ti (min)": ("loop_ti", "flowrate"),
    "Flow Td (min)": ("loop_td", "flowrate"),
}
