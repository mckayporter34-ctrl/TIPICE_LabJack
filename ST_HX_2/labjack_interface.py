# labjack_interface.py
# Hardware abstraction layer for the LabJack T7.
#
# All ljm calls are isolated here.  The rest of the codebase calls
# daq.read() and daq.write() and never imports ljm directly.
# This makes it easy to:
#   • Swap a T7 for a T4 by changing one line here.
#   • Write a mock/simulator subclass for offline UI testing.
#   • Handle connection errors in a single place.

from labjack import ljm


class LabJackInterface:
    """
    Thin wrapper around the LabJack LJM library.

    Usage
    -----
        daq = LabJackInterface()
        daq.connect("T7", "USB", "ANY")
        voltage = daq.read("AIN0")
        daq.write("DAC1", 2.5)
        daq.disconnect()
    """

    def __init__(self):
        self._handle = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self, model: str = "T7", connection: str = "USB", identifier: str = "ANY"):
        """
        Open a connection to the LabJack.

        Parameters
        ----------
        model       : Device model string, e.g. "T7" or "T4".
        connection  : Interface type — "USB", "ETHERNET", or "ANY".
        identifier  : Serial number, IP address, or "ANY".

        Raises
        ------
        Exception   : Propagates any ljm error so the caller can show a
                      descriptive message in the GUI status label.
        """
        self._handle = ljm.openS(model, connection, identifier)
        # Throttle I2C speed to avoid communication errors on longer cables.
        ljm.eWriteName(self._handle, "I2C_SPEED_THROTTLE", 65536)

    def disconnect(self):
        """Close the connection.  Safe to call even if not connected."""
        if self._handle is not None:
            ljm.close(self._handle)
            self._handle = None

    @property
    def is_connected(self) -> bool:
        return self._handle is not None

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def read(self, register: str) -> float:
        """
        Read a single register by name and return its float value.

        Raises
        ------
        RuntimeError : If not connected.
        ljm errors   : Propagated as-is so callers can log them.
        """
        if self._handle is None:
            raise RuntimeError("LabJack not connected")
        return ljm.eReadName(self._handle, register)

    def write(self, register: str, value: float):
        """
        Write a float value to a named register.
        Silently does nothing if not connected, to prevent crashes during
        startup before the device has been opened.
        """
        if self._handle is None:
            return
        ljm.eWriteName(self._handle, register, value)

    def write_digital(self, pin: str, state: bool):
        """Convenience wrapper — writes 1 or 0 to a digital output."""
        self.write(pin, 1 if state else 0)
