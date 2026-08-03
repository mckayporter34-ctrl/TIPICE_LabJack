# Modular LabJack GUI Framework

A modular, Python-based GUI framework for interfacing with laboratory apparatus via LabJack T7 data acquisition devices. Built for the BYU TIPICE laboratory, the framework is designed so that adapting it to a new system requires editing only one configuration file.

---

## Table of Contents

- [Overview](#overview)
- [Requirements](#requirements)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Adapting to a New System](#adapting-to-a-new-system)
  - [Step 1 — Copy the folder](#step-1--copy-the-folder)
  - [Step 2 — Edit config.py](#step-2--edit-configpy)
  - [Step 3 — Edit app.py (if needed)](#step-3--edit-apppy-if-needed)
- [Current Systems](#current-systems)
- [File Reference](#file-reference)
- [PID Tuning Guide](#pid-tuning-guide)
- [Calibration Equations](#calibration-equations)
- [Known Issues / Tips](#known-issues--tips)

---

## Overview

Each laboratory system has its own folder containing a `config.py` and an `app.py`. All other files — the PID controller, LabJack interface, data logger, sensor and control loop dataclasses, and UI panel builders — are shared and identical across systems.

```
┌─────────────────────────────────────────┐
│              config.py                  │  ← Edit this for a new system
│   Pin assignments, calibration,         │
│   PID defaults, log columns             │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│               app.py                    │  ← Edit layout here if needed
│   Builds panels from config, handles    │
│   connection, power, logging            │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│           Shared framework              │  ← Never edit these
│  sensor.py       control_loop.py        │
│  pid_controller.py  labjack_interface.py│
│  ui_builders.py     data_logger.py      │
└─────────────────────────────────────────┘
```

---

## Requirements

- Python 3.9 or later
- [LabJack LJM Library](https://labjack.com/pages/support?doc=/software-driver/installer-downloads/ljm-software-installers-t4-t7-t8-digit/) installed on your system
- Python packages:

```bash
pip install labjack-ljm
```

Tkinter is included with the standard Python installation on Windows and macOS. On Linux, install it with:

```bash
sudo apt-get install python3-tk
```

### Theme Files

The GUI uses the [Forest theme for tkinter](https://github.com/rdbende/Forest-ttk-theme). The two theme files must be placed in an `assets/` folder inside your system directory:

```
your_system/
└── assets/
    ├── forest-dark.tcl
    └── forest-light.tcl
```

---

## Project Structure

```
lab_gui/
│
├── packed_columns/               # Packed column absorption apparatus
│   ├── main.py
│   ├── app.py
│   ├── config.py
│   └── assets/
│
├── shell_tube_hx/                # Shell and tube heat exchanger
│   ├── main.py
│   ├── app.py
│   ├── config.py
│   └── assets/
│
├── pump_cart/                    # Pump cart fluid dynamics apparatus
│   ├── main.py
│   ├── app.py
│   ├── config.py
│   └── assets/
│
└── shared/                       # Copy these into each system folder
    ├── sensor.py
    ├── control_loop.py
    ├── pid_controller.py
    ├── labjack_interface.py
    ├── ui_builders.py
    └── data_logger.py
```

> **Note:** Each system folder must contain its own copy of the shared files alongside `main.py`, `app.py`, and `config.py`. Python requires them to be in the same directory.

---

## How It Works

### Sensors
Each entry in `SENSOR_CONFIGS` in `config.py` creates a read-only display panel in the GUI. The framework reads a raw voltage from the assigned LabJack analog input every 500 ms, passes it through the calibration function defined in config, and updates the display automatically.

### Control Loops
Each entry in `CONTROL_LOOP_CONFIGS` creates a full PID control panel with:
- A setpoint entry spinbox
- A live measurement readout
- A manual/auto mode toggle
- A 0–100 % manual valve slider with a vertical progress bar
- Kc, Ti, and Td tuning spinboxes

In **manual mode**, the slider value is written directly to the output pin as a 0–5 V signal. In **auto mode**, a discrete PID controller with integral anti-windup computes the output every 500 ms.

### Data Logging
When logging is started, a timestamped CSV file is created in the system's log folder. The columns logged are defined in `LOG_COLUMNS` in `config.py`. Any sensor or control loop measurement can be included. The logger runs in a background thread and does not affect GUI responsiveness.

---

## Adapting to a New System

### Step 1 — Copy the folder

Duplicate any existing system folder and rename it:

```
cp -r packed_columns/ my_new_system/
```

### Step 2 — Edit `config.py`

This is the only file that must be changed for most new systems.

#### System identity
```python
SYSTEM_NAME = "My New System"
LOGO_FILE   = "assets/my_logo.png"
LOG_FOLDER  = "MySystem_LoggedData"
```

#### LabJack connection
```python
ETHERNET_ADDRESS = "10.8.112.XX"   # your T7's IP address
```

#### Digital outputs
```python
MAIN_POWER_PIN = "FIO6"    # relay pin for main power
```

#### Read-only sensors
Add one entry per sensor. The `pin` field is the LabJack AIN register. The `calibration` field is a lambda that converts raw voltage to engineering units.

```python
SENSOR_CONFIGS = {
    "inlet_temperature": {
        "label":       "Inlet Temp",
        "unit":        "°C",
        "pin":         "AIN0",
        "calibration": lambda v: 52.1 * v - 10.4,
    },
}
```

#### PID control loops
Add one entry per controlled variable.

```python
CONTROL_LOOP_CONFIGS = {
    "flow": {
        "label":            "Flow",
        "unit":             "L/min",
        "input_pin":        "AIN1",
        "output_pin":       "DAC0",
        "calibration":      lambda v: 26.3 * v - 12.4,
        "setpoint_min":     0,
        "setpoint_max":     50,
        "default_setpoint": 0,
        "pid_defaults":     {"Kc": 0.1, "Ti": 0.5, "Td": 0.0},
        "extra_sensor_key": None,  # optional: embed a sensor reading in this panel
    },
}
```

#### Data logging columns
```python
LOG_COLUMNS = {
    "Inlet Temp (C)":  ("sensor", "inlet_temperature"),
    "Flow (L/min)":    ("loop",   "flow"),
}
```

### Step 3 — Edit `app.py` (if needed)

`app.py` only needs to be changed if:

- The **panel layout** differs from the template system — update the `loop_rows` dict in `_build_ui()` and the `row`/`col` arguments on each panel's `.grid()` call.
- The system has **unique hardware** not covered by the standard sensor/loop pattern, such as an additional relay, valve selector, or on/off switch — add a new frame-builder method following the pattern of `_build_controls_frame()`.
- System-specific hardware from the template (e.g. a column selector, air MFC) should be **removed** — delete the corresponding method and its call in `_build_ui()`.

---

## Current Systems

| System | Sensors | Control Loops | Special Hardware |
|---|---|---|---|
| Packed Columns | Air flow, CO₂, water temp, column pressure drops, liquid levels | Water flow, Column 1 level, Column 2 level | Air MFC setpoint output, column selector relay |
| Shell & Tube HX | Water inlet/outlet temps, steam pressure, tube-side ΔP, makeup temp & flow | Level, Flowrate, Steam Pressure | Pump switch |
| Pump Cart | 9 pressure/ΔP sensors, fluid temperature, bypass flowrate, pump RPM, motor power | Flowrate (via bypass valve), Pump Speed | Pump switch |

---

## File Reference

| File | Purpose | Edit? |
|---|---|---|
| `config.py` | Pin assignments, calibration equations, PID defaults, log columns | **Always** (per system) |
| `app.py` | GUI layout, panel arrangement, system-specific hardware | **Sometimes** (layout/hardware changes) |
| `main.py` | Entry point | Never |
| `sensor.py` | `Sensor` dataclass — holds pin, calibration, and live `StringVar` | Never |
| `control_loop.py` | `ControlLoop` dataclass — holds PID, setpoint, measurement, and valve vars | Never |
| `pid_controller.py` | Discrete PID with anti-windup | Never |
| `labjack_interface.py` | LabJack T7 hardware abstraction — wraps all `ljm` calls | Never |
| `ui_builders.py` | Reusable panel builder functions | Only to add a new panel type |
| `data_logger.py` | Background-thread CSV logger | Never |

---

## PID Tuning Guide

All three tuning parameters can be adjusted live in the GUI without restarting.

| Parameter | Effect | Starting Point |
|---|---|---|
| **Kc** | Proportional gain. Larger = faster response, more oscillation. Use a **negative** value for reverse-acting loops (e.g. a level loop where high level should close the valve). | ±0.1 – 1.0 |
| **Ti** | Integral time constant in minutes. Smaller = faster integral action, more wind-up risk. Set to `0` to disable integral entirely. | 0.1 – 5.0 |
| **Td** | Derivative time constant in minutes. Adds damping. Leave at `0.0` for most loops — derivative amplifies sensor noise. | 0.0 |

**Anti-windup** is implemented automatically. The integrator only accumulates when the output is not saturated, preventing the slow recovery that occurs when a control output is held at its limit for an extended period.

---

## Calibration Equations

All sensors use a linear calibration of the form `y = slope * v + intercept`, where `v` is the raw voltage measured by the LabJack.

### Deriving slope and intercept from two known points

```
slope     = (eng_max - eng_min) / (V_max - V_min)
intercept = eng_min - slope * V_min
```

### 4–20 mA sensors (most pressure and flow sensors)

Wire a **250 Ω shunt resistor** across the LabJack AIN pin to ground. This converts the current loop to a 1–5 V signal:

```
4 mA  →  1.0 V  (minimum engineering value)
20 mA →  5.0 V  (maximum engineering value)
```

Then derive slope and intercept using `V_min = 1.0` and `V_max = 5.0`.

**Example:** 0–150 psig pressure transmitter
```python
# slope = (150 - 0) / (5.0 - 1.0) = 37.5
# intercept = 0 - 37.5 * 1.0 = -37.5
"calibration": lambda v: 37.5 * v - 37.5
```

**Example:** 0–15 psid differential pressure transmitter
```python
# slope = (15 - 0) / (5.0 - 1.0) = 3.75
# intercept = 0 - 3.75 * 1.0 = -3.75
"calibration": lambda v: 3.75 * v - 3.75
```

---

## Known Issues / Tips

**GUI too wide:** Reduce the number of control loop panels shown side-by-side, or reduce `minsize` on column 0 in `ui_builders.py`. For sensor-heavy systems, use a grid layout inside the sensor panel rather than a single column.

**Blank space at bottom of window:** The canvas background shows through below the content area. Fix by matching the canvas background colour to the theme in `_load_themes()`:
```python
self._canvas.configure(bg=self.style.lookup("TFrame", "background"))
```

**Scrolling feels sluggish:** Increase the scroll multiplier in `_on_mousewheel()`. On macOS, `event.delta` is already normalised to ±1, so multiply by 3–5. On Windows it comes in multiples of 120.

**`can't read "scalef": no such variable`:** The Forest theme files require a `scalef` variable to be set before they are sourced. Add the following to `_configure_root()` before the `source` calls:
```python
sw = self.root.winfo_screenwidth()
sh = self.root.winfo_screenheight()
scalef = min(sw / self.BASE_WIDTH, sh / self.BASE_HEIGHT)
self.root.tk.eval(f"set scalef {scalef:.3f}")
```

**`ModuleNotFoundError: No module named 'app'`:** Python's working directory may not be the script folder. Add the following to the top of `main.py`:
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```

**`TclError` when sourcing theme files:** Use absolute paths rather than relative ones:
```python
base_dir = os.path.dirname(os.path.abspath(__file__))
self.root.tk.call("source", os.path.join(base_dir, "assets", "forest-dark.tcl"))
```

**Sensor reads `Error`:** Either the `pin` field in `config.py` is set to `""` (intentionally unassigned), the LabJack is not connected, or the register name is incorrect. LabJack analog inputs are named `AIN0` through `AIN13` on the T7.

**Two loops sharing one output pin:** If two control loops (e.g. two level controllers) share a single DAC output, add a selector flag in `app.py` to gate which loop writes to the pin on each update cycle. See `packed_columns/app.py` for an example using a column selector relay.
