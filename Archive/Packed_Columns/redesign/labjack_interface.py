# labjack_interface.py
# Hardware abstraction layer for the LabJack T7 with dynamic simulation fallback.

import time
import random

try:
    from labjack import ljm
    LJM_AVAILABLE = True
except ImportError:
    LJM_AVAILABLE = False


class LabJackInterface:
    """
    Wrapper around the LabJack LJM library. Automatically supports
    simulated fallback mode if drivers are missing or device is offline.
    """

    def __init__(self):
        self._handle = None
        self.simulated = True  # Defaults to simulated mode until connect() succeeds
        self._sim_last_values = {
            "FIO6": 0.0,   # Main power (0 or 1)
            "FIO7": 0.0,   # Column selector (0 = Col 1, 1 = Col 2)
            "DAC0": 0.0,   # Water Exit Setpoint (Level valve, 0-5V)
            "DAC1": 0.0,   # Water Flow (Flow valve, 0-5V)
            "TDAC0": 0.0,  # Air Flow Setpoint (0-5V)
        }
        
        # Simulation states
        self._sim_air_flow = 0.0
        self._sim_water_flow = 0.0
        self._sim_col1_level = 10.0
        self._sim_col2_level = 15.0
        self._last_sim_time = time.time()

    def connect(self, model: str = "T7", connection: str = "USB", identifier: str = "ANY"):
        if not LJM_AVAILABLE:
            raise ImportError(
                "labjack-ljm library is not installed.\n"
                "Please run: python3 -m pip install labjack-ljm"
            )

        self._handle = ljm.openS(model, connection, identifier)
        self.simulated = False

        try:
            ljm.eWriteName(self._handle, "I2C_SPEED_THROTTLE", 65536)
        except Exception:
            pass

    def disconnect(self):
        if self._handle is not None and not self.simulated:
            try:
                ljm.close(self._handle)
            except Exception:
                pass
        self._handle = None
        self.simulated = True

    @property
    def is_connected(self) -> bool:
        return self._handle is not None and not self.simulated

    def _update_simulation(self):
        """Update simulated physical states based on elapsed time and outputs."""
        now = time.time()
        dt = min(1.0, now - self._last_sim_time)
        self._last_sim_time = now

        power = self._sim_last_values.get("FIO6", 0.0)
        col_select = self._sim_last_values.get("FIO7", 0.0) # 0 = Col 1, 1 = Col 2
        water_exit_valve = self._sim_last_values.get("DAC0", 0.0) # 0 to 5 V
        water_flow_valve = self._sim_last_values.get("DAC1", 0.0) # 0 to 5 V
        air_setpoint_v = self._sim_last_values.get("TDAC0", 0.0) # 0 to 5 V

        if power > 0.5:
            # 1. Air Flowrate tracking setpoint (TDAC0 * 200.0 = SLPM)
            target_air = air_setpoint_v * 200.0
            self._sim_air_flow += (target_air - self._sim_air_flow) * 0.15
            
            # 2. Water Flowrate tracking valve (DAC1 * 10.0 = L/min)
            target_water = water_flow_valve * 10.0
            self._sim_water_flow += (target_water - self._sim_water_flow) * 0.15
            
            # 3. Sump Levels (mm, max 700)
            # Level rises when water flow is high, and drains when exit valve is open
            inflow = self._sim_water_flow
            outflow = (water_exit_valve / 5.0) * 12.0 # max drain rate L/min
            
            # Column 1 level
            if col_select < 0.5: # Col 1 active
                col1_change = (inflow - outflow) * 4.0 # L/min to mm conversion factor
                col2_change = - (water_exit_valve / 5.0) * 2.0 # slow drain
            else: # Col 2 active
                col2_change = (inflow - outflow) * 4.0
                col1_change = - (water_exit_valve / 5.0) * 2.0

            self._sim_col1_level = max(0.0, min(700.0, self._sim_col1_level + col1_change * dt))
            self._sim_col2_level = max(0.0, min(700.0, self._sim_col2_level + col2_change * dt))
        else:
            # System powered off, flows go to zero, levels drain slowly if exit valve open
            self._sim_air_flow += (0.0 - self._sim_air_flow) * 0.2
            self._sim_water_flow += (0.0 - self._sim_water_flow) * 0.2
            outflow = (water_exit_valve / 5.0) * 3.0
            self._sim_col1_level = max(0.0, self._sim_col1_level - outflow * dt)
            self._sim_col2_level = max(0.0, self._sim_col2_level - outflow * dt)

    def read(self, register: str) -> float:
        if self.simulated or self._handle is None:
            self._update_simulation()
            
            # Temperature device cold junction
            if register == "TEMPERATURE_DEVICE_K":
                return 273.15 + 23.5 + random.uniform(-0.1, 0.1)

            # Air Flowrate (AIN0)
            if register == "AIN0":
                # calibration: 527.53746 * v - 250.26377
                # v = (SLPM + 250.26377) / 527.53746
                val = self._sim_air_flow + random.uniform(-1.0, 1.0)
                return (max(0.0, val) + 250.26377) / 527.53746

            # Water Flowrate (AIN1)
            if register == "AIN1":
                # calibration: 26.35046 * v - 12.35837
                val = self._sim_water_flow + random.uniform(-0.05, 0.05)
                return (max(0.0, val) + 12.35837) / 26.35046

            # Column 1 Pressure Drop (AIN2)
            if register == "AIN2":
                # dp = air_flow_slpm**2 * factor + water_flow_lpm * factor
                dp = (self._sim_air_flow * 0.05) ** 2 * 0.3 + self._sim_water_flow * 1.5
                dp = max(0.0, dp + random.uniform(-5.0, 5.0))
                # calibration: (100.0 * (v - 0.476) / (2.373 - 0.476)) * 248.84
                # v = (dp / 248.84) * (2.373 - 0.476) / 100.0 + 0.476
                return (dp / 248.84) * (2.373 - 0.476) / 100.0 + 0.476

            # Column 2 Pressure Drop (AIN3)
            if register == "AIN3":
                dp = (self._sim_air_flow * 0.05) ** 2 * 0.35 + self._sim_water_flow * 1.8
                dp = max(0.0, dp + random.uniform(-5.0, 5.0))
                return (dp / 248.84) * (2.373 - 0.476) / 100.0 + 0.476

            # Column 1 Level (AIN4)
            if register == "AIN4":
                # calibration: ((v - 0.478) / 1.896) * 703.0
                # v = (mm / 703.0) * 1.896 + 0.478
                return (self._sim_col1_level / 703.0) * 1.896 + 0.478

            # Column 2 Level (AIN5)
            if register == "AIN5":
                return (self._sim_col2_level / 703.0) * 1.896 + 0.478

            # Water Temperature (AIN6)
            if register == "AIN6":
                # room temp ~23.5 C
                temp = 23.5 + random.uniform(-0.1, 0.1)
                # calibration: (100.0 / (2.373 - 0.477)) * v + (-20.0 - 0.477 * (100.0 / (2.373 - 0.477)))
                # v = (temp - offset) / slope
                slope = 100.0 / (2.373 - 0.477)
                offset = -20.0 - 0.477 * slope
                return (temp - offset) / slope

            # Delta CO2 Concentration (Not connected)
            if register == "AIN7":
                # random fluctuations around 400-500 ppm
                return 420.0 + random.uniform(-2.0, 2.0)

            return random.uniform(1.2, 3.4)

        return ljm.eReadName(self._handle, register)

    def write(self, register: str, value: float):
        self._sim_last_values[register] = value
        if self.simulated or self._handle is None:
            return
        ljm.eWriteName(self._handle, register, value)

    def write_digital(self, pin: str, state: bool):
        self.write(pin, 1.0 if state else 0.0)
