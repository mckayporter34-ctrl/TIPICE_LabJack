# Development GUI portability checks

Air Flow Meters and both Non-Newtonian units use Tkinter/ttk and Pillow. Their
P&ID, logo, and apparatus-image paths resolve relative to the configuration
files, independent of the launch directory. `setup.bat` and `run.bat` switch to
the project directory and invoke its virtual environment directly; setup stops
on installation errors and the launcher reports a missing environment. Both
accept Python 3.9.12 or newer. Setup prefers Python 3.9 when creating an
environment and reuses an existing compatible environment, including Python 3.14.
See [installation migration instructions](../README.md#updating-an-existing-lab-installation)
to rebuild an older `.venv`.

Canvas minimum sizes use the actual readout widths, including font sizing and
theme padding. Enlarged layouts scroll instead of squeezing readouts together.
Airflow keeps the entrance-pressure tile immediately below the diagram even
when the sidebar image and logo extend below the visible area. Both development
screens provide standard checkbutton styles if the Forest theme is unavailable.

## Automated checks

From the project directory, after running `setup.bat`, run in PowerShell:

```powershell
$env:LABJACK_GUI_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests use fake LabJack I/O and temporary logging destinations. They do not
require a connected LabJack or native LJM driver. The layout checks build all
three development screens with light, dark, and standard ttk themes at Tk font
scales of 1, 4/3, and 2 (72, 96, and 144 pixels per inch). Available Windows ttk
themes are also exercised when the tests run on Windows. Checks cover readout
alignment and separation, image loading, control sizing, and access to the far
edges of scrollable content at a 1200 × 720 window size. Existing tests also
exercise the standard 1450 × 800 layouts and control/logging behavior.

These scaling checks were run on macOS. They simulate larger font metrics;
they do not establish native Windows rendering, Windows display-scale behavior,
batch-file execution, or LJM driver operation.

The Python 3.9.12 compatibility update was checked in a fresh environment:
requirements installed successfully, all active application modules and the
historian imported, and all 64 non-desktop tests passed (31 desktop tests
skipped). The portable macOS Python 3.9.12 runtime embeds Tk in a form that
Pillow's Tk extension cannot load, so its desktop tests could not complete.
Run the desktop suite on the lab's standard Windows Python 3.9.12 installation.

## Native Windows verification before lab rollout

1. Confirm that setup and launch reject a `.venv` older than Python 3.9.12 with
   installation/rebuild instructions before installing packages or opening the
   GUI. With Python 3.9.12 installed and any incompatible `.venv` renamed, run
   setup and launch from a folder containing spaces, and launch again using a shortcut
   whose working directory is elsewhere. Verify
   `.\.venv\Scripts\python.exe --version` reports Python 3.9.12 or newer.
2. Open Air Flow Meters and both Non-Newtonian units in Development. Inspect
   them at the lab monitor's normal resolution and at 100%, 125%, and 150%
   Windows display scaling, restarting the application after each change.
3. Check the apparatus images, diagram readouts, mode/setpoint alignment, PID
   fields, theme switching, and both scrollbars. Airflow's rotameter indicator
   should show `Indicator Only` in a read-only box; its entrance-pressure sensor
   remains a separate numeric reading.
4. Run the automated suite above in a desktop session.
5. With the Windows LJM driver installed, perform the normal apparatus USB or
   Ethernet connection and commissioning checks. Fake-I/O tests do not validate
   physical pump/valve wiring or control performance.
