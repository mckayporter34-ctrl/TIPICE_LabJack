# labjack_interface.py
# Hardware abstraction layer for the LabJack T7.
#
# All ljm calls are isolated here. The rest of the codebase calls
# daq.read() and daq.write() and never imports ljm directly.
# If LJM is missing or connection is not established, it falls back to simulated mode.

import random
from core.safety import SafetyManager, SafetyState

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
        self._sim_last_values = {}
        self.safety = SafetyManager(force_write_callback=self._force_write)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self, model: str = "T7", connection: str = "USB", identifier: str = "ANY"):
        """
        Open a connection to the LabJack.
        """
        self.safety.transition_to(SafetyState.CONNECTING)

        if not LJM_AVAILABLE:
            raise ImportError(
                "labjack-ljm library is not installed.\n"
                "Please run: python3 -m pip install labjack-ljm"
            )

        # Attempt real connection
        self._handle = ljm.openS(model, connection, identifier)
        self.simulated = False
        
        self.safety.transition_to(SafetyState.CONNECTED_SAFE)

        # Throttle I2C speed to avoid communication errors on longer cables.
        try:
            ljm.eWriteName(self._handle, "I2C_SPEED_THROTTLE", 65536)
        except Exception:
            pass

    def disconnect(self):
        """Close the connection. Safe to call even if not connected."""
        
        self.safety.transition_to(SafetyState.SHUTTING_DOWN)

        if self._handle is not None and not self.simulated:
            try:
                ljm.close(self._handle)
            except Exception:
                pass
        self._handle = None
        self.simulated = True
        
        self.safety.transition_to(SafetyState.DISCONNECTED)

    @property
    def is_connected(self) -> bool:
        return self._handle is not None and not self.simulated

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def read(self, register: str) -> float:
        """
        Read a single register by name and return its float value.
        If in simulated mode, returns a dummy float value.
        """
        if not self.safety.can_read():
            if not self.simulated and self._handle is not None and self.safety.state.name != "DISCONNECTED":
                print(f"[LabJack] Read blocked by safety system for {register}")
            return 0.0

        if self.simulated or self._handle is None:
            # Special registers simulation
            if register == "TEMPERATURE_DEVICE_K":
                return 273.15 + 23.5 + random.uniform(-0.1, 0.1)  # Room temp in Kelvin
            
            # Simulated analog input voltages typically range from 1V to 3.5V
            return random.uniform(1.2, 3.4)

        return ljm.eReadName(self._handle, register)

    def write(self, register: str, value: float):
        """
        Write a float value to a named register.
        """
        if not self.safety.can_write():
            # Only log blocked writes if we are physically connected and not in DISCONNECTED state
            if not self.simulated and self._handle is not None and self.safety.state.name != "DISCONNECTED":
                print(f"[LabJack] Write blocked by safety system for {register} <- {value}")
            return
            
        self._force_write(register, value)
        
    def _force_write(self, register: str, value: float):
        """Internal write method that bypasses safety checks, used by SafetyManager for safe_zero"""
        if self.simulated or self._handle is None:
            return

        ljm.eWriteName(self._handle, register, value)

    def write_digital(self, pin: str, state: bool):
        """Convenience wrapper — writes 1 or 0 to a digital output."""
        self.write(pin, 1.0 if state else 0.0)
