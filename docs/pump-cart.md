# Pump Cart #1

Open **Development**, enter `dietcoke`, then launch **Pump Cart → Unit #1**.
Only unit #1 is registered. Connections do not require a Student ID or checkout.

The screen uses `PI diagrams/Pump_Cart_V1.png` from the supplied drawio canvas.
The current source is 1791×1083 pixels and is downsampled directly from that
original on each resize. A 597×361 logical image area keeps the diagram,
sensor leaders and animation aligned independently of PNG export resolution.
It has no scrollbars and is checked at 1366×768 and 1320×700, leaving room for
window borders and the taskbar. Controls and logging are stacked on the left,
with logging directly below main-flow control. The diagram scales proportionally
with white margins. Readout boxes, fonts and switches use the same ttk/Forest
styles as the other development systems. Added dashed leaders are 2 pixels wide
and meet the center of the numeric field's edge. Top leaders are centered
under their fields; the four bottom fields share a baseline and use right-angle
leaders. The canvas has no small footer text.
The left tiles have padded input/readout fields, wider label-to-field spacing,
and larger gaps between rows and tiles, including the PID tuning fields.

## Diagram and operation

- The single PID reads **main flow** from AIN3 (upper meter) and commands the
  valve on DAC0. The bypass meter is read-only and never drives a PID.
- The lower meter shows bypass flow. The temperature leader meets the right
  vertical return pipe.
- All eight pressure drops use **psi**. Four approximate fitting locations are
  marked `*`, as authorized by the user on November 2, 2026. “El” means elbow.
  Elbow ΔP is at the bottom-left elbow, immediately below the tee.
- Edit `DIAGRAM_READOUTS` in `configs/pump_cart.py` to move labels. Each entry
  gives its key, title, numeric-field center, pipe tap and connecting card edge in the logical
  `DIAGRAM_SIZE` coordinate space (597×361). Negative coordinates place cards
  in the white margins. `DIAGRAM_BOUNDS` reserves room for those cards;
  `PUMP_STATUS_POSITION` and `FLOW_PATHS` use the same logical coordinates.
  Higher-resolution exports with the same crop and proportions need no
  coordinate changes. A changed crop or changed equipment positions require
  updating the logical layout and its aspect ratio.
- Valve percentage and pump ON/OFF show the **commanded** state. The sheet
  supplies no valve position or relay feedback channels.
- Pump speed is an independent manual 0–100% setpoint on DAC1. Press Enter
  or leave the box to apply a typed value. Its relay is FIO2. DAC1 is held
  at zero while the pump is off.
- Moving blue dashes follow tank → pump → upper meter → ball/globe/control valves
  → lower split, the pipe branch and shared tank return. Teal dashes follow
  the lower bypass through its meter. Paths follow the drawing's arrows.
  Main minus bypass determines animation on the parallel pipe branch.
  Dashes turn along pipe corners and clip at each open path's end before
  wrapping to its inlet. Unknown/error/zero flow hides affected dashes.
  Pump OFF/disconnect hides all.

The screen shares the development pump/valve lifecycle and numeric validation.
Connection zeros FIO2, DAC0 and DAC1 before exposing controls. Disconnect,
navigation, destruction and control faults zero all three. AUTO pauses with
the pump OFF. A failed main-flow read in running AUTO or failed output write
requests a fault. Manual valve positioning is independent of the pump relay.
AUTO locks setpoint/manual valve inputs, consistent with other system panels.
The MANUAL/AUTO switch sits beside the valve-command input on the same row.

## Workbook channels and TODOs

Source: `Development/New_system_implementation.xlsx`, **PUMP CARTS**, rows 3–74.
The current channel map includes the user's pump-pressure and motor-power
wiring updates; control-valve ΔP has been removed from the screen and logging.

| Channel | Measurement/command | Conversion/status |
| --- | --- | --- |
| AIN1 | Water temperature, Type K | InAmp gain 51, 1.25 V offset + T7 CJC |
| AIN2 | Pump speed, GS4 AO2 | 4.34–19.62 mA → 0–4390 RPM via LJTick-CurrentShunt |
| AIN3 | Main flow | 4–20 mA → 0.79–79 GPM, assuming 118 mV/mA receiver |
| AIN4 | Motor power | Measured 8.0–334 mV → 0–1500 W |
| AIN6 | Pipe ΔP | 0–50 psi |
| AIN7 | Pump ΔP | 4–20 mA → 0–50 psi |
| AIN8 | Bypass ΔP | 0–50 psi |
| AIN9 | Tee ΔP | 0–50 psi |
| AIN10 | U ΔP | 0–50 psi |
| AIN11 | Elbow ΔP | 0–50 psi |
| AIN12 | Globe valve ΔP | 0–50 psi |
| AIN13 | Ball valve ΔP | 0–50 psi |
| FIO0 | Bypass flow, FMG94 NPN pulse input | 750 pulses/US gallon; hardware period measurement |
| DAC0 | Control valve | 0–100%, assumed 0–5 V into V2C |
| DAC1 | Pump speed setpoint, GS4 AI1 | 0–100% → 0–5 V |
| FIO2 | Pump relay | Assumed active HIGH |

Unspecified conversions remain TODO as requested. Connected readings display
**TODO**, never raw voltage or logic state as engineering units. Complete the
endpoint tuples in `configs/pump_cart.py` before using those measurements.
Initial PID tuning and valve action need commissioning before main-flow AUTO.
Selecting Ethernet prompts for an IP or serial number.

AIN3 uses 0.472–2.360 V for the 4–20 mA main flow signal. Verify the installed
receiver before relying on this calibration. Signals below 3.6 mA follow the
flow measurement error path.

All pressure inputs scale 0.472–2.360 V (4–20 mA) to 0–50 psi using
118 mV/mA receivers.
Readings from 3.6 mA to 4 mA show 0 psi. Readings below 3.6 mA show **Error**.

The Type K thermocouple uses the **InAmp module**, with its amplified output
connected to **AIN1**. AIN1 is configured for single-ended measurement
(`NEGATIVE_CH=199`), a **±10 V** range and resolution index **8**. The conversion
subtracts the original **1.25 V offset** and divides by the **gain of 51** before
LJM Type K conversion. `TEMPERATURE_DEVICE_K` supplies cold-junction
compensation. A failed cold-junction read displays **Error** until a valid read
returns.

The AO2 speed feedback scales linearly from 0 RPM at 4.34 mA to 4390 RPM at
19.62 mA. The workbook specifies an LJTick-CurrentShunt on AIN2. Its 118 mV/mA
output maps the calibrated range to 0.51212–2.31516 V. Readings below 4 mA
show an error, and readings from 4 mA to 4.34 mA show 0 RPM. Readings above
19.62 mA are extrapolated.
[LabJack current-shunt datasheet](https://support.labjack.com/docs/ljtick-currentshunt-datasheet).

Motor power on **AIN4** uses the measured calibration points **8.0 mV at 0 kW**
and **334 mV at 1.5 kW**. With input `V` in volts, the conversion is
`power_W = max(0, 1500 * (V - 0.008) / (0.334 - 0.008))`.
The display and logs use watts: 8.0 mV → 0 W, 171 mV → 750 W,
334 mV → 1500 W. Below-zero results are clamped to zero; values above 334 mV
are extrapolated linearly. The independent RPM feedback remains on AIN2.

DAC1 maps the 0–100% speed setpoint to 0–5 V. The speed reached at 100%
depends on the installed AI1 settings and any converter. The log records
the command in percent and the AO2 feedback in RPM.

## FMG94 bypass flow meter: wiring and signal

Source: Omega **M-5204/0615 (M5204.pdf)**, electrical diagram on p. 11,
measuring operation on p. 12, and FMG94 specifications on p. 14. The existing
cart configuration identifies the bypass meter as FMG94. Its standard K-factor
is **750 pulses per US gallon**. Confirm the model and K-factor on the installed
nameplate: custom pulse rates are available, and the nameplate takes precedence.
Set `BYPASS_PULSES_PER_GALLON` to that value if different. Use the stated
pulses/gallon factor rather than deriving it from the rounded ml/pulse value.

### Connection to the T7 using NPN output

Make connections with power off. The meter needs an external **12 or 24 VDC**
supply (the manual specifies +/-15%); the T7's 5 V VS cannot power the meter.
The manual's NPN diagram uses **pin 2 as the output and pin 4 tied to ground**.
Identify the M12 pins by number, checking the connector's mating orientation;
the manual does not specify cable colors.

| Meter / component | Connection |
| --- | --- |
| M12 pin 1, +UB | External supply +12 or +24 VDC, as rated for the installed meter |
| M12 pin 3, GND | External supply 0 V and T7 GND (common reference) |
| M12 pin 4 | Tie to pin 3 / 0 V to use the NPN diagram |
| M12 pin 2, pulse output | T7 **FIO0**, also called DIO0 |
| 4.7 kOhm pull-up resistor | Between **T7 VS (+5 V)** and the pin-2/FIO0 signal node |

This adapts the manual's NPN circuit to a LabJack input. The NPN transistor
switches pin 2 to ground when on; when off, the pull-up raises it to approximately
5 V. Its pull-up current is about 1.1 mA, below the meter's 25 mA output limit.
The T7 accepts 5 V digital inputs, as described in its
[digital I/O specifications](https://support.labjack.com/docs/13-0-digital-i-o-t-series-datasheet).
LabJack documents this pull-up arrangement in its
[open-collector app note](https://support.labjack.com/docs/open-collector-signals-app-note).

**Do not pull the FIO0 signal up to the meter's 12/24 V supply.** The manual's
example resistors refer to a signal at that supply voltage; those circuits need
level conversion before connecting to a T7. The PNP diagram also produces a
supply-level signal and requires conditioning. The wiring above uses NPN and a
5 V pull-up instead. Verify the installed wiring has no existing 12/24 V pull-up
or other receiver driving this node before connecting FIO0.

### How flow becomes a reading

The meter uses magnetic induction: conductive liquid moving through a magnetic
field creates an electrode voltage proportional to velocity. Its electronics
convert the measurement to a **50% duty-cycle square wave** whose frequency
increases with flow. Flow is encoded by pulse frequency, not signal amplitude.

With K = 750 pulses/gallon:

```text
frequency_Hz = flow_GPM * 750 / 60 = flow_GPM * 12.5
flow_GPM = frequency_Hz * 60 / 750 = 0.08 * frequency_Hz
flow_GPM = 60 / (period_seconds * 750)
```

For example, **125 Hz = 8 ms per pulse = 10 GPM**. Count one full cycle per
pulse (rising edge to rising edge), rather than counting both edges.
The FMG94's normal range is 1.3-26.4 GPM; output starts at about 0.52 GPM
with reduced accuracy. The listed maximum flow is 31.7 GPM. Keep its tube full
of conductive liquid (at least 20 microSiemens/cm); empty or partially filled
tubes can produce random pulses that are not valid flow (manual p. 6).

### Software implementation

- `configs/pump_cart.py` sets K = 750 and `BYPASS_DIO = "DIO0"` for FIO0.
  To move to FIO1, rewire the signal and change that constant to `"DIO1"`;
  both the setup registers and read register follow it on the next app launch.
- Connection configures rising-edge **Frequency In** (`EF_INDEX = 3`),
  one-shot mode, and Clock0 at 80 MHz (divisor 1, maximum 32-bit roll).
  The clock source is explicitly selected; this setup reserves Clock0 for
  the bypass input on this cart.
- The app reads `DIO0_EF_READ_A_AND_RESET`, divides its clock ticks by
  80,000,000 to get seconds, then applies the GPM conversion above.
  Hardware captures the pulse timing independently of the 500 ms screen poll.
  [LabJack's Frequency In documentation](https://support.labjack.com/docs/13-2-5-frequency-in-t-series-datasheet)
  describes these registers and their reset behavior.
- A reset read consumes the result; zero means no new completed period
  (two rising edges). The app briefly retains the last valid reading between
  completed periods, then shows/logs **0.00 GPM after 1 second without a fresh
  period**, at 500 ms polling resolution. This prevents indefinite stale flow.
  At the standard meter's 0.52 GPM output threshold, two periods take about
  0.31 seconds. Reassess the timeout for any custom low-frequency version.
- Startup with no completed period shows zero. Read failures and invalid data
  display **Error** and clear the retained reading; reconnect and disconnect
  also clear it. A new valid measurement restores the reading automatically.
- No pulses cannot distinguish stopped flow, flow below the output threshold,
  an unpowered meter, or a disconnected signal wire. Zero is not proof that
  the sensor is healthy. Bypass flow remains a monitoring/logging channel.
- Simulated timer reads return integer clock ticks consistent with roughly
  10 GPM, rather than dummy analog voltages.

Bench checks: confirm the nameplate K-factor; check FIO0 relative to GND for
approximately 0-5 V pulses; verify 125 Hz reads 10 GPM; stop the pulses and
verify the readout falls to zero; restart and confirm recovery. No physical
hardware was connected or operated during this change.

CSV logging covers every measurement, main-flow setpoint/tuning, valve command
and manual pump-speed command, using a separate `PumpCart1` historian tag.
TODO/error measurements log as error markers rather than valid numbers.

## Verification

```sh
LABJACK_GUI_TESTS=1 .venv/bin/python -m unittest discover -s tests -p test_pump_cart.py -v
```

Checks use real Tk widgets and fake I/O: channel/range mapping, TODO handling,
single-unit/single-loop registration, complete fit and label separation in
Forest light/dark and standard ttk, separate pump/valve commands, main versus
bypass feedback, flow-path geometry, animation visibility and shutdown/faults.
Native Windows rendering and physical control performance remain untested.

Bypass lifecycle checks also run headlessly in `test_pump_cart.py`: FIO0 setup,
K-factor conversion, read/reset tick units, startup, identical successive
periods, timeout, restart, invalid reads, calibration TODO, and disconnect/reconnect.
