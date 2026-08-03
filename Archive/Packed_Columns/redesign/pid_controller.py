# pid_controller.py
# Self-contained discrete PID controller with integral anti-windup.

class PIDController:
    """
    Discrete PID controller with output clamping and integral anti-windup.

    Parameters
    ----------
    Kc         : Proportional gain. Negative Kc gives reverse action.
    Ti         : Integral time constant in the same time units as dt.
                 Set to 0 to disable integral action.
    Td         : Derivative time constant. Set to 0 to disable.
    output_min : Lower clamp on the controller output (default 0.0 V).
    output_max : Upper clamp on the controller output (default 5.0 V).
    """

    def __init__(
        self,
        Kc: float = 1.0,
        Ti: float = 1.0,
        Td: float = 0.0,
        output_min: float = 0.0,
        output_max: float = 5.0,
    ):
        self.Kc = Kc
        self.Ti = Ti
        self.Td = Td
        self.output_min = output_min
        self.output_max = output_max

        self._integral: float = 0.0
        self._e_prev:   float = 0.0

    def reset(self):
        """Zero the integrator and previous-error memory."""
        self._integral = 0.0
        self._e_prev   = 0.0

    def compute(self, setpoint: float, measurement: float, dt: float) -> float:
        """
        Run one PID iteration and return the clamped output voltage.
        """
        if dt <= 0:
            return self.output_min

        error = setpoint - measurement

        # Proportional
        P = self.Kc * error

        # Integral (with anti-windup via conditional integration)
        if self.Ti > 0:
            Ki = self.Kc / self.Ti
            potential_integral = self._integral + Ki * error * dt
        else:
            potential_integral = self._integral

        # Derivative
        D = (self.Kc * self.Td) * (error - self._e_prev) / dt

        # Raw output
        u_raw = P + potential_integral + D

        # Clamp + anti-windup
        if u_raw > self.output_max:
            u = self.output_max
            if error < 0 and self.Ti > 0:
                self._integral = potential_integral
        elif u_raw < self.output_min:
            u = self.output_min
            if error > 0 and self.Ti > 0:
                self._integral = potential_integral
        else:
            u = u_raw
            if self.Ti > 0:
                self._integral = potential_integral

        self._e_prev = error
        return u

    def update_tuning(self, Kc: float, Ti: float, Td: float):
        """Update gains without resetting integrator state."""
        self.Kc = Kc
        self.Ti = Ti
        self.Td = Td
