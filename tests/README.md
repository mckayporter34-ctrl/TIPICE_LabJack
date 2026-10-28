# Regression checks

Run the controller-input and CSV-writer tests without a window server:

```sh
python3 -m unittest discover -s tests -v
```

Run the full suite, including actual Tkinter widgets with fake LabJack I/O, from a
desktop session with Tkinter and Pillow installed:

```sh
LABJACK_GUI_TESTS=1 python3 -m unittest discover -s tests -v
```

In PowerShell, set `$env:LABJACK_GUI_TESTS = '1'` before running the same Python
command. These tests never connect to a LabJack or require its drivers.
Temporary CSV files are created outside apparatus log folders and removed.

Coverage includes all nine registered apparatus configurations and the standalone Pump
Cart UI: manual setpoint editing, AUTO locking against typing and spinbox arrows,
power cycling, packed-column selection, numeric input messages and partial edits,
and orange He cylinders on both catalytic units. Logging checks cover invalid
tuning, failed sensor/source callbacks, NaN/infinity, UI-thread ownership,
recovery, row counts, rapid restart, file-open/write failures, and cleanup.

The suite includes headless checks and desktop checks that run only with
`LABJACK_GUI_TESTS=1`. The injected invalid values and disk-full exception
intentionally produce warning
and error log output; the final unittest result determines success.
Physical control performance and apparatus commissioning were not tested.

## Airflow checks

`test_airflow.py` adds six checks for the workbook's channel ranges, Type T
conversion arguments, complete input logging, ΔP and temperature overlays, entrance-pressure
placement, standard-window fit, manual/AUTO states, valve command bounds, shutdown,
and failed cold-junction compensation. Three use real Tk widgets with fake I/O:

```sh
LABJACK_GUI_TESTS=1 python3 -m unittest discover -s tests -p test_airflow.py -v
```

No test connects to lab hardware or a real historian. Hardware gain, valve transfer function, and
control tuning still require commissioning on the apparatus.

## Non-Newtonian checks

`test_nonnewtonian.py` checks the legacy channel/calibration mapping, dashboard
registration, 0–10 V manual/PID output limits, continued 0–5 V scaling for existing
systems, pump gating, invalid inputs, and AUTO sensor/output failures. Desktop
tests also cover P&ID overlay placement, themes, active-low pump start/stop,
reconnect, shutdown, configuration failure, and CSV logging:

```sh
LABJACK_GUI_TESTS=1 python3 -m unittest discover -s tests -p test_nonnewtonian.py -v
```

Unit #2 checks cover the workbook channel assignments, 0–45 GPM and 0–50 inches
WC scaling, direct AIN0–AIN1 differential Type K conversion and cold-junction compensation,
0–5 V manual/AUTO valve output, active-high pump behavior, shutdown/faults,
P&ID layout, Ethernet address prompting, CSV logging, and both dashboard dropdown
launch targets using the Small Pipe/Large Pipe labels and current apparatus image.
Unit #1 retains its separate active-low pump and 0–10 V speed output.
Both units also check immediate control/logging access with the pump OFF,
Unit #1 pump-speed gating, independent Unit #2 manual valve positioning,
paused AUTO flow control while stopped, red/green pump status above the pump,
centered temperature/flow boxes, and removal of the lower voltage-mapping text.

`test_sensor.py` checks optional exponential smoothing, the 5-second step
response with irregular sample intervals, retained calculation precision,
unfiltered defaults, and resets after errors. Unit #2's headless integration
checks verify that one thermocouple sample feeds the filtered display and both
temperature CSV columns, and that read failures and reconnects clear history.

## Development selector and historian integration

`test_dashboard.py` checks cancellation and incorrect passwords, unlocking with
`dietcoke`, locking again on return to the main selector, blocked direct launches,
and return navigation from the development control panels. The desktop test
checks the three main cards, two development cards, and top navigation buttons.

The logger tests also check UI-thread snapshots, timestamped run labels that
stay fixed during a logging session, skipped bad
historian channels, and continued CSV logging during a slow historian failure.
Historian clients are mocked and GUI tests disable external historian writes.

`test_device_manager.py` checks USB/Ethernet connections without a Student ID or
checkout/release/heartbeat requests for all development units. Main systems retain
required IDs and checkout, including declined/accepted session takeovers,
ownership heartbeats, shutdown, rejected requests, and network outages. These checks
run without a window server, lab hardware, or a real device-manager API.
