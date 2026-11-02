# Pump Cart #1

Open **Development**, enter `dietcoke`, then launch **Pump Cart → Unit #1**.
Only unit #1 is registered. Connections do not require a Student ID or checkout.

The screen uses `PI diagrams/Pump_Cart_V1.png` from the supplied drawio canvas.
It has no scrollbars and is checked at 1366×768 and 1320×700, leaving room for
window borders and the taskbar. Controls and logging are stacked on the left,
with logging directly below main-flow control. The diagram scales proportionally
with white margins. Readout boxes, fonts and switches use the same ttk/Forest
styles as the other development systems. Added dashed leaders are 2 pixels wide.

## Diagram and operation

- The single PID reads **main flow** from AIN3 (upper meter) and commands the
  valve on DAC0. The bypass meter is read-only and never drives a PID.
- The lower meter shows bypass flow. Temperature is on the right dashed tap.
- All nine pressure drops use **psid**. Four approximate fitting locations are
  marked `*`, as authorized by the user on November 2, 2026. “El” means elbow.
  Elbow ΔP is at the bottom-left elbow, immediately below the tee.
- Edit `DIAGRAM_READOUTS` in `configs/pump_cart.py` to move labels. Each entry
  gives its key, title, card center and leader endpoint in source PNG pixels
  (470×310). Negative coordinates place cards in the white margins.
- Valve percentage and pump ON/OFF show the **commanded** state. The sheet
  supplies no valve position or relay feedback channels.
- Pump speed is an independent manual percentage on DAC1, not a PID. Its
  relay is FIO2. Pump OFF forces the speed command to zero.
- Blue particles follow tank → pump → upper meter → ball/globe/control valves
  → lower split, the pipe branch and shared tank return. Teal particles follow
  the lower bypass through its meter. Paths follow the drawing's arrows.
  Main minus bypass determines animation on the parallel pipe branch.
  Unknown/error/zero flow hides affected particles. Pump OFF/disconnect hides all.

The screen shares the development pump/valve lifecycle and numeric validation.
Connection zeros FIO2, DAC0 and DAC1 before exposing controls. Disconnect,
navigation, destruction and control faults zero all three. AUTO pauses with
the pump OFF. A failed main-flow read in running AUTO or failed output write
requests a fault. Manual valve positioning is independent of the pump relay.
AUTO locks setpoint/manual valve inputs, consistent with other system panels.

## Workbook channels and TODOs

Source: `Development/New_system_implementation.xlsx`, **PUMP CARTS**, rows 3–74.

| Channel | Measurement/command | Conversion/status |
| --- | --- | --- |
| AIN0 | Water temperature, Type K | User-confirmed channel; InAmp3 + CJC |
| AIN2 | Pump speed | TODO endpoints, 0–3450 RPM |
| AIN3 | Main flow | TODO endpoints, 0.79–79 GPM for unit #1 |
| AIN4 | Pump ΔP | TODO endpoints, 0–50 psid |
| AIN5 | Motor power | TODO endpoints, 0–630 W |
| AIN6 | Pipe ΔP | 0–50 psid |
| AIN7 | Control valve ΔP | 0–50 psid |
| AIN8 | Bypass ΔP | 0–50 psid |
| AIN9 | Tee ΔP | 0–50 psid |
| AIN10 | U ΔP | 0–50 psid |
| AIN11 | Elbow ΔP | 0–50 psid |
| AIN12 | Globe valve ΔP | 0–50 psid |
| AIN13 | Ball valve ΔP | 0–50 psid |
| FIO0 | Bypass flow, FMG94 pulse input | TODO pulses/gallon |
| DAC0 | Control valve | 0–100%, assumed 0–5 V into V2C |
| DAC1 | Manual pump speed | 0–100%, assumed 0–5 V into V2C |
| FIO2 | Pump relay | Assumed active HIGH |

Unspecified conversions remain TODO as requested. Connected readings display
**TODO**, never raw voltage or logic state as engineering units. Complete the
endpoint tuples and pulse factor in `configs/pump_cart.py` before using these
measurements or main-flow AUTO. Initial PID tuning and valve action also need
commissioning. Selecting Ethernet prompts for an IP or serial number.

AIN6–AIN13 follow the sheet's explicit **0–20 mA** range with a 118-ohm LJTick
shunt: 0–2.360 V → 0–50 psid. Verify the installed shunts/transmitter ranges.
Temperature uses the existing laboratory InAmp3 convention (gain 51, 1.25 V
offset), T7 cold-junction temperature and LJM Type K conversion. Verify the
fitted amplifier settings.

FIO0 uses rising-edge **Frequency In**, reading `DIO0_EF_READ_A_F` in seconds,
following [LabJack's documentation](https://support.labjack.com/docs/13-2-5-frequency-in-t-series-datasheet).
Conversion: `60 / (period × pulses_per_gallon)`. Input voltage conditioning,
pulse calibration and stop/no-pulse behavior need verification on the installed
FMG94. No physical hardware was operated during development.

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
