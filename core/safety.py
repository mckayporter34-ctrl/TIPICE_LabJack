from enum import Enum, auto
from typing import Callable, Dict

class SafetyState(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED_SAFE = auto()
    ENABLED = auto()
    FAULTED = auto()
    SHUTTING_DOWN = auto()

class SafetyManager:
    """
    Manages the safety state of the apparatus.
    Enforces rules on whether physical reads/writes are permitted.
    """
    def __init__(self, force_write_callback: Callable[[str, float], None] = None):
        self.state = SafetyState.DISCONNECTED
        self._force_write_callback = force_write_callback
        self.safe_outputs: Dict[str, float] = {}

    def register_safe_output(self, register: str, safe_value: float = 0.0):
        """Register a register/pin and its safe default value (usually 0.0)."""
        self.safe_outputs[register] = safe_value

    def transition_to(self, new_state: SafetyState):
        """Transition to a new state and execute side effects like safe_zero if needed."""
        print(f"[SafetyManager] State transition: {self.state.name} -> {new_state.name}")
        
        # Always execute safe zero on FAULTED or SHUTTING_DOWN
        if new_state in (SafetyState.FAULTED, SafetyState.SHUTTING_DOWN):
            self._execute_safe_zero()
            
        self.state = new_state

    def _execute_safe_zero(self):
        """Force all registered outputs to their safe default values."""
        if not self._force_write_callback:
            print("[SafetyManager] WARNING: No force_write_callback provided. Cannot safe_zero.")
            return
            
        print("[SafetyManager] Executing safe_zero()")
        for reg, val in self.safe_outputs.items():
            try:
                self._force_write_callback(reg, val)
            except Exception as e:
                print(f"[SafetyManager] Error zeroing {reg}: {e}")

    def can_read(self) -> bool:
        """Reads are permitted if we are connected and not completely disconnected/connecting."""
        return self.state.name in (
            "CONNECTED_SAFE",
            "ENABLED",
            "SHUTTING_DOWN",
            "FAULTED"
        )

    def can_write(self) -> bool:
        """Standard physical writes are only permitted in the ENABLED state."""
        return self.state.name == "ENABLED"
