# TIPICE LabJack Control System

This repository contains the software for controlling and monitoring various laboratory apparatuses in the BYU Chemical Engineering Lab using LabJack T7 hardware.

## Architecture

The system is built with a modular architecture:
- `main.py`: The entry point for the application. It launches a unified dashboard where users can select which apparatus to control.
- `configs/`: Contains configuration files for each apparatus (e.g., Packed Column, Pump Cart, Shell & Tube Heat Exchanger, Catalytic Methanation). These dictate the UI layout, sensor mappings, and control loops for the specific setup.
- `core/`: Contains the core logic that is shared across all modules, including:
  - `base_app.py`: The foundation for the GUI control panels.
  - `labjack_interface.py`: Handles communication with the LabJack T7 devices.
  - `sensor.py`: Defines sensor types and scaling logic.
  - `control_loop.py`, `pid_controller.py`: Logic for automated control.
  - `data_logger.py`: Handles data logging to CSV.
  - `ui_builders.py`: Reusable UI components.

## Setup Instructions

1. Ensure Python 3.8+ is installed.
2. Install dependencies (e.g., `labjack-ljm`, `Pillow`, `matplotlib`).
3. Ensure the LabJack LJM driver is installed on the host machine.
4. Run the main application:
   ```bash
   python main.py
   ```

## Legacy Code

Older standalone versions of the code and legacy scripts have been moved to the `Archive/` directory to keep the main repository clean.
