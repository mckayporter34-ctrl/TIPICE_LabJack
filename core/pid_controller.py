# pid_controller.py
# Self-contained discrete PID controller with integral anti-windup.
# All state (integral accumulator, previous error) lives on the object,
# so the app no longer needs getattr(self, 'integral_w', 0.0) gymnastics.


class PIDController:
    """
    Discrete PID controller with output clamping and integral anti-windup.

    Parameters
    ----------
    Kc         : Proportional gain.  Negative Kc gives reverse action
                 (e.g. increase valve output when measurement is too high).
    Ti         : Integral time constant in the same time units as dt.
                 Set to 0 to disable integral action entirely.
    Td         : Derivative time constant.  Set to 0 to disable.
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self):
        """Zero the integrator and previous-error memory.
        Call this whenever switching from manual to auto mode to avoid
        an integrator wind-up spike on the first PID cycle."""
        self._integral = 0.0
        self._e_prev   = 0.0

    def compute(self, setpoint: float, measurement: float, dt: float) -> float:
        """
        Run one PID iteration and return the clamped output voltage.

        Parameters
        ----------
        setpoint    : Desired process value in engineering units.
        measurement : Current process value in engineering units.
        dt          : Time step in minutes (matching Ti / Td units).

        Returns
        -------
        float : Controller output, clamped to [output_min, output_max].
        """
        if dt <= 0:
            return self.output_min

        error = setpoint - measurement

        # ── Proportional ──────────────────────────────────────────────
        P = self.Kc * error

        # ── Integral (with anti-windup via conditional integration) ───
        if self.Ti > 0:
            Ki = self.Kc / self.Ti
            potential_integral = self._integral + Ki * error * dt
        else:
            potential_integral = self._integral

        # ── Derivative ────────────────────────────────────────────────
        D = (self.Kc * self.Td) * (error - self._e_prev) / dt

        # ── Raw output ────────────────────────────────────────────────
        u_raw = P + potential_integral + D

        # ── Clamp + anti-windup ───────────────────────────────────────
        # The integral is only updated when the output is NOT saturated,
        # or when it is saturated but the error is driving it back.
        if u_raw > self.output_max:
            u = self.output_max
            if error < 0 and self.Ti > 0:      # error pulling output down → allow
                self._integral = potential_integral
        elif u_raw < self.output_min:
            u = self.output_min
            if error > 0 and self.Ti > 0:      # error pulling output up → allow
                self._integral = potential_integral
        else:
            u = u_raw
            if self.Ti > 0:
                self._integral = potential_integral

        self._e_prev = error
        return u

    # ------------------------------------------------------------------
    # Allow the GUI spinboxes to write tuning parameters at runtime
    # ------------------------------------------------------------------

    def update_tuning(self, Kc: float, Ti: float, Td: float):
        """Update gains without resetting integrator state."""
        self.Kc = Kc
        self.Ti = Ti
        self.Td = Td

    def initialize(self, current_output: float):
        """
        Seed the integrator to the current output value before switching to AUTO.
        Prevents the output from jumping to 0 on the first PID cycle.
        Call this instead of reset() when transferring from manual to auto.
        """
        self._integral = current_output
        self._e_prev   = 0.0
