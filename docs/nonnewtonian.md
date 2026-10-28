# Non-Newtonian Fluids

Use **Development** at the top of the main selector and enter `dietcoke`.
The **Non-Newtonian Fluids** card uses `images/Non_Newtonian_Apparatus.png`
and has a dropdown for **Unit #1 (Small Pipe)** and **Unit #2 (Large Pipe)**.
Select a unit, then choose **Launch Unit**. These labels and the selector
image path are assigned in `configs/__init__.py`.

## Unit #1

Launch **Non-Newtonian Fluids → Unit #1 (Small Pipe)** from the dashboard. The screen uses
`PI diagrams/NonNewtonaion_1_V1.png`, exported from the supplied
`NonNewtonaion_1.drawio` canvas. Controls and logging are on the left, live
temperature, pressure-drop, flow and pump-speed readings are on the diagram,
and the flow PID/manual controls are below it.

## Hardware and calibration

The channel assignments, Ethernet address and calibration coefficients come from
`Development/NonNewtonian/nonnewtonian_gui_v1.py`.

| Channel | Assignment |
| --- | --- |
| AIN0 | Fluid temperature: `55.28745157 * V - 48.08422656` °C |
| AIN1 | Flow: `(53.2187707 * V - 25.35572892) * 0.264172` GPM |
| AIN2 | Pressure drop: `3.125 * 8.475 * V - 12.5` inches WC |
| TDAC2 | Pump-speed command: 0–10 V = 0–100% |
| FIO0 | Pump enable, active LOW: 0 = ON, 1 = OFF |

Ethernet uses **10.8.112.140**; USB connects to any available T7. TDAC2 uses
the existing LJTick-DAC accessory (DACA at the FIO2/FIO3 block). The built-in
DAC0 was only a half-voltage bookkeeping copy in the legacy GUI. The new GUI
holds the command in software and does not drive DAC0.

The three analog inputs are explicitly configured as single-ended, ±10 V.
The calibration results are not clipped or rounded until display formatting,
preserving small negative or overrange values and full precision for the PID.

## Operation

1. Connect by USB or Ethernet. The GUI first commands FIO0 HIGH and TDAC2 to
   0 V, then enables all control inputs and logging, including while the pump
   is OFF. The pump stays OFF. The canvas indicator above the pump is red for
   OFF and green for ON; it shows the commanded pump state.
2. Switch the pump ON. It starts in MANUAL with a zero speed command. Adjust
   the pump-speed slider or percentage entry; 50% writes 5 V and 100% writes
   10 V. Typed commands are bounded to 0–100% before writing.
3. To regulate flow, enter a flow setpoint in MANUAL, adjust the tuning, and
   select AUTO. As in the existing system panels, AUTO locks the setpoint and
   manual-speed entries; switch back to MANUAL to change the setpoint.
4. Start logging as needed. An Experiment ID is optional. The default interval
   is one second; control and display updates run every 500 ms.

The controller output is in volts, with a 0–10 V clamp. Kc is in V/GPM and
Ti/Td are in minutes. Positive Kc increases pump speed when measured flow is
below the setpoint. The configured startup tuning is
**Kc = 0.1 V/GPM, Ti = 0.05 min, Td = 0.04 min**.
The initial setpoint is zero and the editable setpoint range is **0–30 GPM**.
These gains and the entry range are provisional commissioning settings; the
legacy GUI provided neither PID tuning nor a rated flow range. They can be
changed in `configs/nonnewtonian_1.py` and the tuning can be edited on screen.

Pump OFF resets AUTO, the integrator and speed to zero. Disconnect, navigation
back to the dashboard, and window shutdown command FIO0 HIGH and TDAC2 to 0 V.
A failed/non-finite flow read in AUTO or a failed pump-output write requests
the same OFF states, disables controls and displays a fault; reconnect to reset.
Invalid/incomplete control inputs command zero speed until corrected.
These are software actions and require a working connection to reach the T7.
Control inputs remain available after Pump OFF while connected; output writes
remain gated by the pump switch. Detailed control/fault messages appear in the
Controls sidebar. The flow and temperature readout boxes are centered on their
diagram signal lines, and the lower panel shows output commands as percentages.

CSV files are saved under `NonNewtonian1_LoggedData/`. They include temperature,
pressure drop, measured flow, flow setpoint, pump-speed command, and PID tuning.
Pump speed is the commanded percentage, not a measured RPM or speed feedback.

## Unit #2: Pipe Viscometer (CB217A-Paul)

Unit #2 uses `PI diagrams/NonNewtonaion_2_V1.png`, exported from the supplied
`NonNewtonaion_2.drawio` canvas. It has the same controls/logging sidebar and
flow PID panel as #1, with a valve-command readout above the valve on the P&ID.
The loop adjusts the valve to regulate flow.

The input assignments, thermocouple type, current signals, and pressure range
come from `Development/New_system_implementation.xlsx`, sheet `NONNEWTONIAN_2`,
rows 3, 5, 7, 11 and 19. The flow range, pump pin and polarity, valve voltage
range, and original amplifier gain/offset were confirmed by the user on October 21,
2026. On October 28, 2026, temperature acquisition changed to a direct
differential thermocouple input.

| Channel | Assignment |
| --- | --- |
| AIN0–AIN1 | Direct Type K fluid-temperature thermocouple: positive to AIN0, negative to AIN1 |
| AIN2 | Flow transmitter: 4–20 mA = 0–45 GPM |
| AIN3 | Differential-pressure transmitter: 4–20 mA = 0–50 inches WC |
| DAC0 | Valve command: 0–5 V = 0–100% |
| FIO0 | Pump enable, active HIGH: 1 = ON, 0 = OFF |

The LJTick-CurrentShunt converts 4–20 mA to 0.472–2.360 V. Flow scaling is
`(V - 0.472) * 45 / 1.888`; pressure scaling is
`(V - 0.472) * 50 / 1.888`. Readings remain unclipped, so sensor overrange
and small negative readings are visible.

For temperature, each connection configures `AIN0_NEGATIVE_CH = 1`,
`AIN0_RANGE = 0.1` (±0.1 V), and `AIN0_RESOLUTION_INDEX = 8`. Reading `AIN0`
then returns AIN0 minus AIN1, matching Kipling's differential input setting.
LJM's nonlinear Type K function converts this thermocouple voltage directly to
°C with the T7's `TEMPERATURE_DEVICE_K` as cold-junction compensation. Failed
compensation marks the temperature as Error rather than reusing a stale value.
The InAmp3 is bypassed; its gain/offset correction is no longer applied.
Wire the thermocouple directly to AIN0 (+) and AIN1 (−), with an approximately
100 kΩ resistor from AIN1 to GND as specified in
[LabJack's T7 thermocouple wiring instructions](https://support.labjack.com/docs/using-a-thermocouple-with-the-t7).
AIN1 is reserved for the thermocouple's negative lead. AIN2 and AIN3 retain
their single-ended transmitter settings.

The temperature readout uses an exponential low-pass filter with a 5-second
time constant, configured by `TEMPERATURE_FILTER_TIME_CONSTANT_S`. Each sensor
update uses its actual elapsed time: `alpha = 1 - exp(-dt / 5)` and
`filtered = previous + alpha * (raw - previous)`. Filtering runs independently
of the CSV logging interval. The first valid reading initializes the filter.
Reconnects and failed readings clear its history; after a failure, the next
valid reading initializes it again. A failed reading marks both log values as
Error. The filter reaches about 95% of a temperature step after 15 seconds and
does not correct a calibration or cold-junction offset.

Ethernet is deliberately blank in `configs/nonnewtonian_2.py`. Selecting
Ethernet prompts for an address or serial number for that connection. USB
connects to any available T7.

On connection, all control inputs and logging become available. The pump stays
OFF (FIO0 LOW) and the valve command is 0 V. The canvas pump indicator, readout
alignment, and percentage command panel match Unit #1.
Manual valve positioning works whenever connected, including with the pump OFF
or a failed flow reading. Starting/stopping the pump preserves the valve command.
AUTO flow control runs with the pump ON and pauses at the current valve command
while the pump is OFF. Switch to MANUAL to reposition the valve while stopped.
The setpoint range is 0–45 GPM. Valve commands map 0%, 50%,
and 100% to 0 V, 2.5 V, and 5 V. The controller output is limited to 0–5 V.
Configured startup PID tuning is **Kc = 0.05 V/GPM, Ti = 0.02 min, Td = 0**; commission the
gains and valve action on the apparatus. Positive Kc assumes increasing command
increases flow.

Pump OFF commands FIO0 LOW while preserving the valve command. Disconnect,
navigation, shutdown, and control/output faults request FIO0 LOW and DAC0 at 0 V.
The shared UI applies each unit's own output mapping
and pump polarity. CSV files go to `NonNewtonian2_LoggedData/` and include
`Fluid Temperature Filtered (C)` and `Fluid Temperature Raw (C)` from the same
sample (both are temperatures in °C, with raw meaning unfiltered), differential
pressure, measured flow, setpoint, valve-command
percentage, and PID tuning. The valve percentage is a command, not measured
valve-position feedback.

## Verification

Run the control and calibration checks without hardware:

```sh
python3 -m unittest discover -s tests -p test_nonnewtonian.py -v
```

For the real Tk widget/layout, logging, connection and shutdown tests, run from
a desktop session:

```sh
LABJACK_GUI_TESTS=1 python3 -m unittest discover -s tests -p test_nonnewtonian.py -v
```

All tests use fake LabJack I/O. They do not connect to or commission the apparatus.
