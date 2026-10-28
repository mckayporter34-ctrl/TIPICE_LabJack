# TIPICE LabJack Control System

This repository contains the software for controlling and monitoring various laboratory apparatuses in the BYU Chemical Engineering Lab using LabJack T7 hardware.

## Architecture

The system is built with a modular architecture:
- `main.py`: The entry point for the application. It launches a unified dashboard where users can select which apparatus to control.
- `configs/`: Contains configuration files for each apparatus (e.g., Packed Column, Pump Cart, Shell & Tube Heat Exchanger, Catalytic Methanation). These dictate the UI layout, sensor mappings, and control loops for the specific setup.
- `core/`: Contains the core logic that is shared across all modules, including:
  - `base_app.py`: The foundation for the GUI control panels.
  - `labjack_interface.py`: Handles communication with the LabJack T7 devices.
  - `sensor.py`: Defines sensor scaling, optional exponential filtering, and raw readings.
  - `control_loop.py`, `pid_controller.py`: Logic for automated control.
  - `data_logger.py`: Handles data logging to CSV.
  - `ui_builders.py`: Reusable UI components.

## Prerequisites: LabJack LJM Software

Before running this application, you **must** install the official LabJack LJM software (drivers) on your operating system. The Python library (`labjack-ljm`) is merely a wrapper and will fail if the underlying OS drivers are missing.

- **Windows**: Download and install the [LabJack LJM Installer for Windows](https://labjack.com/pages/support?doc=/software-driver/installer-downloads/ljm-software-installers-t4-t7-digit/#windows).
- **macOS**: Download and install the [LabJack LJM Installer for macOS](https://labjack.com/pages/support?doc=/software-driver/installer-downloads/ljm-software-installers-t4-t7-digit/#mac-os-x).
- **Linux**: Download and install the [LabJack LJM Installer for Linux](https://labjack.com/pages/support?doc=/software-driver/installer-downloads/ljm-software-installers-t4-t7-digit/#linux).

Ensure the device is powered and connected (via USB or Ethernet) before launching the software.

## Setup & Running Instructions

We have provided convenient scripts to automatically create a virtual environment and install the required dependencies (listed in `requirements.txt`).

### On Windows
1. Double-click `setup.bat` (or run it in the command prompt). This only needs to be done once.
2. To start the GUI, double-click `run.bat`.

### On macOS / Linux
1. Open a terminal in the project directory and run the setup script (only needed once):
   ```bash
   ./setup.sh
   ```
2. To start the GUI, run:
   ```bash
   ./run.sh
   ```

## Legacy Code

Older standalone versions of the code and legacy scripts have been moved to the `Archive/` directory to keep the main repository clean.

## Development systems

The main selector shows the Shell & Tube Heat Exchangers, Catalytic Methanation,
and Packed Column. Use the **Development** button at the top of the selector and
enter `dietcoke` to access Airflow and Non-Newtonian Fluids. An incorrect password
or Cancel leaves the selector locked. **Back to Main Selector** locks the
development section again; returning from a development control panel keeps you
in that section until you leave it or close the application.

This password is an operator access gate in the desktop interface. Anyone with
access to the source code can change it.

Airflow and both Non-Newtonian units have `DEVICE_MANAGER_ENABLED = False` in
their configurations. They connect without a Student ID or device-manager
checkout/release requests. Other systems keep device-manager checkout enabled
by default.

For managed systems, a busy-machine prompt allows the operator to take over
another session. While connected, the app checks session ownership every three
seconds and disconnects if the device manager reports a different owner.
Development systems skip checkout, release, and session heartbeat requests.

Selector titles, unit labels, image paths, and launch modules are assigned in
`configs/__init__.py`. The Non-Newtonian card uses
`images/Non_Newtonian_Apparatus.png`. Each control panel's P&ID is assigned
separately by `PID_IMAGE` in its apparatus configuration.

## Airflow System

In **Development**, choose **Launch Unit** on the **Air Flow Meters** card. It uses the
supplied airflow P&ID, with ΔP readings on the canvas and
entrance pressures in the panel below. See [airflow setup and channel mapping](docs/airflow.md)
for the workbook mapping and hardware settings to verify before commissioning.

## Non-Newtonian Fluids

Select **Unit #1 (Small Pipe)** or **Unit #2 (Large Pipe)** in the
**Non-Newtonian Fluids** dropdown on the Development selector.
Each supplied P&ID shows live temperature, pressure drop, flow and
output command. Unit #1 controls pump speed with 0–10 V; Unit #2 controls a
0–5 V valve to regulate 0–45 GPM flow. Unit #2 reads a Type K thermocouple
directly across AIN0–AIN1, applies a 5-second exponential filter to the display,
and logs both filtered and raw temperatures in °C. See the
[Non-Newtonian setup and operation guide](docs/nonnewtonian.md) for channel
assignments, operation and initial tuning settings.

## Historian logging

Local CSV logging also supports the InfluxDB historian and captures the Experiment
ID with an `HHMMSS` suffix as the run label when logging starts, for example
`Group1_Run1_143015`. A blank ID uses `Unnamed_Run_HHMMSS`. The label stays fixed
throughout that logging session. Network writes run separately so a
historian outage does not stop local CSV capture.

Set `INFLUX_TOKEN` in the environment or in a `.historian.local.json` file in the
repository root. This file is ignored by Git. `INFLUX_URL`, `INFLUX_ORG`, and
`INFLUX_BUCKET` can be set the same way; environment values take precedence.
Without a token or the optional InfluxDB library, local CSV logging still works.

The standalone service is in `Historian/Historian.py` and uses the same settings.
Install `requirements.txt` before running it. Credentials and local recording
files are excluded from commits.
