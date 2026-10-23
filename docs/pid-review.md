# PID implementation review — October 8, 2026

## Recommendation

Keep the positional PI implementation as the starting point for these systems.
Prioritize correcting reverse-action anti-windup, improving manual/AUTO transfer,
and measuring actual elapsed time before considering an incremental (velocity)
rewrite. No PID equations, initialization/reset behavior, configured gains, or
control sampling constants were changed during this update. Input parsing now
rejects malformed or non-finite values before they reach the controller.

The code alone cannot establish optimal tuning. That requires apparatus response
data, actuator direction/limits, sensor noise, operating ranges, and an agreed
performance objective (such as overshoot, settling time, or disturbance rejection).
The verification in this update used simulated I/O, not physical apparatus.

## Current implementation

All active configurations use `core/pid_controller.py`. It calculates an absolute
output voltage with the ideal/dependent-gain positional equation:

```text
e[k] = SP[k] - PV[k]
I_candidate = I[k-1] + (Kc/Ti) * e[k] * dt    (when Ti > 0)
D[k] = Kc * Td * (e[k] - e[k-1]) / dt
u[k] = clamp(Kc * e[k] + I_candidate + D[k], 0 V, 5 V)
```

Integration is rectangular; differentiation is a backward difference on error.
Conditional integration provides anti-windup. Time constants and `dt` use minutes.
The shared update callback assumes 500 ms (`dt = 1/120 minute`). Every configured
`Td` is zero, so the default controllers are PI controllers.

| System | Loop | Kc | Ti (minutes) |
| --- | --- | ---: | ---: |
| Shell & Tube #1 and #2 | Level | -75 | 0.005 |
| Shell & Tube #1 and #2 | Flow | 0.74 | 0.036 |
| Shell & Tube #1 and #2 | Steam pressure | 0.5 | 0.05 |
| Shell & Tube #3 | Level | -75 | 5 |
| Shell & Tube #3 | Flow | 0.2254 | 0.1321 |
| Shell & Tube #3 | Steam pressure | 0.1501 | 0.1116 |
| Catalytic Methanation #1 and #2 | Pressure | -0.5 | 0.1 |
| Catalytic Methanation #1 and #2 | Temperature | 0.2 | 5 |
| Packed Columns | Water flow | 0.14 | 0.06 |
| Packed Columns | Column 1 and 2 level | -0.05 | 2 |
| Pump Cart (shared UI, outside current dashboard registry) | Flow | 2 | 0.05 |
| Pump Cart | Pump speed | 1 | 1 |

## Recommended follow-up changes, in priority order

1. **Correct conditional integration for negative Kc.** At the upper limit the
   controller allows integration when `error < 0`; at the lower limit it allows
   integration when `error > 0`. Those directions assume positive gain. For
   reverse-action loops, use the direction of the integral increment
   `(Kc/Ti) * error * dt`, or implement back-calculation against the applied output.
   This affects exchanger level, catalytic pressure, and packed-column level.
   In a diagnostic with `Kc=-1, Ti=1, e=10, dt=1`, output clamps to 0 V while the
   integrator becomes -10 V, accumulating further into saturation. Conversely,
   starting at `I=8 V` with `e=1` produces a corrective -1 V increment, but the
   upper-limit branch rejects it and leaves `I=8 V`. These examples demonstrate
   the sign issue; their values are diagnostic inputs, not proposed tuning.
   [MathWorks documents clamping and back-calculation](https://www.mathworks.com/help/simulink/slref/discretepidcontroller.html).

2. **Implement true output tracking for manual/AUTO transfer.** `initialize()`
   sets `I` to the manual output and previous error to zero. The next computation
   still adds proportional action, one integral increment, and (if enabled)
   derivative action. With `Kc=1, Ti=1, Td=0`, manual output 2.5 V, error 1, and
   the current sampling constant, the first AUTO output is 3.50833 V. Track the
   applied manual output while in manual, or initialize the state accounting
   for proportional/derivative contributions and the first integration step.
   Packed-column mode callbacks currently do not initialize the controller at
   transfer. Exchanger state refreshes reinitialize all AUTO loops, even when
   another loop's mode changes. Initialize only at actual transitions and define
   tracking behavior while power or loop gates inhibit the actuator.
   [MathWorks illustrates manual-output tracking](https://www.mathworks.com/help/simulink/slref/bumpless-control-transfer-between-manual-and-pid-control.html).

3. **Measure elapsed time and audit fast-loop tuning.** Tk schedules the next
   cycle after the current callback completes, so I/O time and UI delays make
   actual sampling longer than the fixed assumption. Use monotonic elapsed time
   in a later control change. Exchanger #1/#2 level `Ti=0.005 minute` is 0.3 s,
   shorter than the nominal 0.5 s sample interval; #3's level `Ti=5 minutes` is
   1,000 times larger. Verify the intended units and commissioning records before
   adopting either tuning. Faster sampling and retuning should follow measured
   process dynamics, rather than changing these constants by inspection.

4. **Keep PI for initial flow, level, and pressure tuning; evaluate filtered D
   for thermal loops only if measurements justify it.** If derivative action is
   enabled later, use derivative on measurement with a low-pass filter, and
   initialize its history appropriately. The present unfiltered error derivative
   can amplify measurement noise and react to a setpoint change or AUTO transfer.
   [NI discusses measurement-based D and process-loop suitability](https://download.ni.com/support/manuals/370010c.pdf#page=198),
   and [MathWorks explains derivative filtering](https://www.mathworks.com/videos/understanding-pid-control-part-3-expanding-beyond-a-simple-derivative-1531120808026.html).

## Positional versus incremental form

The actuators receive absolute analog commands (0–5 V), making positional PI a
natural implementation. An incremental controller can also drive them by
accumulating output changes, but it must reconcile that accumulated state with
the clamped/applied output, manual commands, gating, and changing gains. Switching
forms alone does not establish better control performance.

Consider incremental PI if frequent manual transfers, actuator tracking, or
online gain changes make explicit output-state tracking easier to implement.
For the current system, improving positional PI's tracking and anti-windup is a
smaller, more directly supported change. NI's
[positional and velocity equations](https://download.ni.com/support/manuals/370010c.pdf#page=198)
describe the distinction; the choice above is an engineering recommendation based
on this repository's absolute voltage outputs and observed state handling.

Before a future algorithm change, collect step responses at representative
operating points, confirm actuator action, and compare saturation recovery,
manual/AUTO output jumps, disturbance rejection, settling time, and noise response.
