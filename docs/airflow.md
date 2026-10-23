# Air Flow Meters

Use **Development** at the top of the main selector, enter `dietcoke`, and launch
**Air Flow Meters → CB217A · Peter**. The screen uses
the same shared 1450 × 800 initial control-panel window and maximization behavior
as the other apparatuses. Its content scrolls on smaller displays. The dashboard
also scrolls to accommodate the fourth apparatus.

The supplied `PI diagrams/AirFlow_PID_V1.png` is displayed without stretching.
The four live ΔP readouts connect to the ends of the dashed taps. Each live temperature
entry (°C) is centered above its corresponding TI 1–4 symbol on the canvas;
T4 shifts slightly left as needed to clear the rotameter.
The live commanded valve percentage appears in a read-only box to the left of
the valve symbol, with the entry centered on the dashed command line.
The mass flow reading (SCFM) appears immediately to the right of Pitot ΔP, beneath
the flow sensor symbol. The five entrance pressures appear in their own panel
immediately below the canvas, with a “Rotameter - Indicator Only” note also shown
beside Orifice ΔP. The diagram expands to use the available window height;
sidebar panels stay compact, with the TIPICE logo below them.
Temperature symbols already present in the supplied
drawing remain part of the image.

## Channel mapping

Source: `Development/New_system_implementation.xlsx`, `AIRFLOW`, rows 3–44.

| Input | Measurement | Signal / engineering range |
| --- | --- | --- |
| AIN0–AIN3 | Temperatures 1–4 | Type T thermocouples through InAmp3; °C |
| AIN4 | Pitot ΔP | 4–20 mA / 0–2.5 in WC |
| AIN5 | Pitot entrance pressure | 4–20 mA / 0–2 psi |
| AIN6 | Nozzle ΔP | 4–20 mA / 0–10 in WC |
| AIN7 | Nozzle entrance pressure | 4–20 mA / 0–2 psi |
| AIN8 | Orifice ΔP | 4–20 mA / 0–1 psi |
| AIN9 | Orifice entrance pressure | 4–20 mA / 0–2 psi |
| AIN10 | Rotameter entrance pressure | 4–20 mA / 0–2 psi |
| AIN11 | Mass flow meter / flow PID feedback | 4–20 mA / 0–350 SCFM |
| AIN12 | Venturi ΔP | 4–20 mA / 0–2 psi |
| AIN13 | Venturi entrance pressure | 4–20 mA / 0–2 psi |
| DAC0 | Valve command through V2CMod | 4–20 mA / 0–100% |

The workbook's `WCO` nozzle unit is interpreted as inches of water column,
consistent with the old GUI. All pressure/current conversions are linear and
retain negative and overrange measurements. CSV logging includes all 14 inputs,
flow setpoint, commanded valve percentage, and PID settings.

## Hardware settings to verify during commissioning

- InAmp3 gain defaults to **51×** with **1.25 V** offset, matching the other lab
  controllers. The workbook does not specify the fitted gain. Set `INAMP_GAIN`
  and `INAMP_OFFSET_V` in `configs/airflow.py` to the installed values.
  Type T conversion uses LJM `tcVoltsToTemp(6008, ...)` and the device temperature
  for cold-junction compensation; failed compensation marks temperatures as errors.
  See the [InAmp3 datasheet](https://support.labjack.com/docs/ljtick-inamp-3-0-datasheet)
  and [LJM conversion reference](https://support.labjack.com/docs/tcvoltstotemp-ljm-user-s-guide).
- Current inputs assume standard LJTick-CurrentShunt conditioning:
  **0.472–2.360 V** for 4–20 mA. AIN5 is described only as “Current Shunt” in
  the workbook; verify it has the same transfer function. For different
  conditioning, update that sensor's calibration. See the
  [current-shunt datasheet](https://support.labjack.com/docs/ljtick-currentshunt-datasheet).
- The shared controller assumes **0–5 V at DAC0** corresponds to 0–100% valve
  command. The workbook specifies V2CMod and a 4–20 mA output but does not give
  its voltage-input transfer function or valve action. Verify the converter,
  valve direction, and the 0 V shutdown behavior before operating the apparatus.
- Default flow setpoint **80 SCFM**, Kc **1**, Ti **0.05 min**, and Td **0 min**
  reproduce the supplied old screen. They are starting values, not commissioned
  tuning for the new hardware. The controller starts in MANUAL at 0%.
- No digital blower/power relay is specified. A successful LabJack connection enables
  software valve control and logging directly. It does not operate the blower.
- No Ethernet address is specified. USB uses the usual device discovery;
  Ethernet asks for an IP address or serial number. An installation can set
  `ETHERNET_ADDRESS` in the configuration to skip the prompt.

Disconnect, navigating back, and closing the airflow screen
reset the valve command to zero and stop logging. Disconnected readings remain
`---`; they do not display simulated process data.
