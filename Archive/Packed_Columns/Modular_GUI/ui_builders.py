# ui_builders.py
# Reusable widget-building functions.
#
# Every function here takes a parent frame, a data object (Sensor or
# ControlLoop), and grid position arguments, then returns a dict of the
# widgets it created so the caller (app.py) can store them for later
# enable/disable calls.
#
# Nothing in this file knows about specific channels, pin names, or
# calibration equations — all of that lives in config.py / the data objects.

import tkinter as tk
from tkinter import ttk

from sensor import Sensor
from control_loop import ControlLoop


# ══════════════════════════════════════════════════════════════════════════════
# Read-only sensor display  (no control, no PID)
# ══════════════════════════════════════════════════════════════════════════════

def build_sensor_display(parent, sensor: Sensor, row: int, col: int) -> dict:
    """
    Build a two-row label + read-only entry for a single sensor channel.

    Returns
    -------
    dict with key "entry" pointing to the ttk.Entry widget, so the caller
    can enable/disable it via the returned reference.
    """
    ttk.Label(parent, text=f"{sensor.label} ({sensor.unit})").grid(
        row=row, column=col, padx=5, pady=(10, 0), sticky="nsew"
    )
    entry = ttk.Entry(parent, textvariable=sensor.value_var, state="disabled", width=10)
    entry.grid(row=row + 1, column=col, padx=5, pady=(5, 10), sticky="ew")
    return {"entry": entry}


# ══════════════════════════════════════════════════════════════════════════════
# Full PID control loop panel
# ══════════════════════════════════════════════════════════════════════════════

def build_control_loop_panel(
    parent,
    loop: ControlLoop,
    sensors: dict,
    row: int,
    col: int,
    columnspan: int = 3,
    root=None,          # needed for focus-get check in spinbox sync
) -> dict:
    """
    Build a complete control panel for one ControlLoop object.

    Layout (matches the original packed-columns design):
      Column 0 : Setpoint spinbox, measured entry, optional extra-sensor entry
      Column 1–3 : Manual override slider (0–100) + labels
      Column 4 : Spinbox mirroring the slider value
      Column 5 : Vertical progress bar + numeric entry
      Column 6–7 : Kc / Ti / Td PID tuning spinboxes

    Parameters
    ----------
    loop        : ControlLoop data object (holds all tkinter vars).
    sensors     : Full sensors dict from app — used to embed the optional
                  extra_sensor_key display inside this panel.
    row/col     : Grid position of the LabelFrame inside `parent`.
    columnspan  : How many parent columns the frame spans (default 3).
    root        : tk.Tk root — passed in so spinbox sync can call
                  root.focus_get().

    Returns
    -------
    dict mapping widget role → widget, for enable/disable in app.py.
    """
    frame = ttk.LabelFrame(parent, text=loop.label, padding=(20, 10))
    frame.grid(row=row, column=col, columnspan=columnspan,
               padx=(20, 20), pady=(10, 10), sticky="nsew")

    widgets = {"frame": frame}  # role → widget  ("frame" lets app.py add extra widgets)

    # ── Left column: setpoint, measurement, optional extra sensor ─────────────
    ttk.Label(frame, text=f"{loop.label} Setpoint ({loop.unit})").grid(
        row=0, column=0, padx=5, pady=0, sticky="ew"
    )
    sp_spinbox = ttk.Spinbox(
        frame,
        from_=loop.setpoint_min, to=loop.setpoint_max,
        textvariable=loop.setpoint_var,
        width=5, state="disabled",
    )
    sp_spinbox.grid(row=1, column=0, padx=5, pady=(5, 10), sticky="ew")
    widgets["setpoint_spinbox"] = sp_spinbox

    ttk.Label(frame, text=f"{loop.label} ({loop.unit})").grid(
        row=2, column=0, padx=5, pady=(10, 0), sticky="nsew"
    )
    measured_entry = ttk.Entry(
        frame, textvariable=loop.measured_var, state="disabled", width=10
    )
    measured_entry.grid(row=3, column=0, padx=5, pady=(5, 10), sticky="ew")
    widgets["measured_entry"] = measured_entry

    # Optional extra sensor reading embedded in this panel
    if loop.extra_sensor_key and loop.extra_sensor_key in sensors:
        extra = sensors[loop.extra_sensor_key]
        ttk.Label(frame, text=f"{extra.label} ({extra.unit})").grid(
            row=4, column=0, padx=5, pady=(10, 0), sticky="nsew"
        )
        extra_entry = ttk.Entry(
            frame, textvariable=extra.value_var, state="readonly", width=10
        )
        extra_entry.grid(row=5, column=0, padx=5, pady=(5, 10), sticky="ew")
        widgets["extra_entry"] = extra_entry

    # ── Centre: manual override switch + slider ───────────────────────────────
    ttk.Label(frame, width=20, text="Manual Override").grid(
        row=0, column=1, columnspan=3, padx=(40, 0), pady=0, sticky="nsew"
    )

    manual_ui_var = tk.BooleanVar(value=False)

    def _toggle_mode():
        loop.is_auto = not loop.is_auto
        loop.pid.reset()
        mode_switch.config(text="Mode: AUTO" if loop.is_auto else "Mode: MANUAL")

    mode_switch = ttk.Checkbutton(
        frame,
        text="Mode: MANUAL",
        style="Switch",
        variable=manual_ui_var,
        command=_toggle_mode,
    )
    mode_switch.grid(row=1, column=1, columnspan=3, padx=(40, 0), pady=(5, 10), sticky="ew")
    widgets["mode_switch"] = mode_switch

    ttk.Label(frame, text="Set Manual Valve Output").grid(
        row=2, column=1, columnspan=4, padx=(40, 0), pady=(10, 0), sticky="nsew"
    )

    scale = ttk.Scale(frame, from_=0, to=100, variable=loop.valve_position)
    scale.grid(row=3, column=1, columnspan=3, padx=(40, 5), pady=(5, 0), sticky="ew")
    widgets["scale"] = scale

    # Spinbox that mirrors the slider value
    spinbox = ttk.Spinbox(
        frame, from_=0, to=100, width=3,
        textvariable=loop.rounded_valve_position, state="normal",
    )
    spinbox.grid(row=3, column=4, padx=5, pady=(5, 10), sticky="ew")
    widgets["manual_spinbox"] = spinbox

    def _commit_manual(event=None):
        try:
            loop.valve_position.set(float(loop.rounded_valve_position.get()))
        except ValueError:
            pass

    spinbox.bind("<Return>", _commit_manual)
    spinbox.bind("<FocusOut>", _commit_manual)

    def _sync_spinbox_from_scale(*_args):
        if root and root.focus_get() != spinbox:
            loop.rounded_valve_position.set(round(loop.valve_position.get()))

    loop.valve_position.trace_add("write", _sync_spinbox_from_scale)
    spinbox.set(round(loop.valve_position.get()))

    # Scale tick labels
    for text, anchor, c in [("0", "w", 1), ("   50", "center", 2), ("100", "e", 3)]:
        ttk.Label(frame, text=text, anchor=anchor).grid(
            row=4, column=c, padx=(40 if c == 1 else 0, 0), pady=0, sticky="ew"
        )

    # ── Right side: vertical progress bar ────────────────────────────────────
    pb_frame = tk.LabelFrame(frame, borderwidth=0, relief="flat")
    pb_frame.grid(row=0, rowspan=7, column=5, padx=(40, 10), pady=0, sticky="nsew")
    widgets["pb_frame"] = pb_frame

    ttk.Label(pb_frame, text="Flow Valve Output (%)").grid(
        row=0, column=0, columnspan=3, padx=0, pady=0, sticky="nsew"
    )

    for text, anchor, r in [("100", "ne", 1), ("50", "e", 2), ("0", "se", 3)]:
        ttk.Label(pb_frame, text=text, anchor=anchor).grid(
            row=r, column=0, padx=0,
            pady=(0 if r != 2 else 10, 0),
            sticky="ew",
        )

    progressbar = ttk.Progressbar(
        pb_frame, orient="vertical",
        variable=loop.valve_position, mode="determinate",
    )
    progressbar.grid(row=1, rowspan=3, column=1, padx=0, pady=(10, 0), sticky="ns")

    valve_entry = ttk.Entry(
        pb_frame, state="readonly",
        textvariable=loop.rounded_valve_position, width=5,
    )
    valve_entry.grid(row=1, column=2, padx=(5, 0), pady=0, sticky="ew")
    widgets["valve_entry"] = valve_entry

    # ── PID tuning spinboxes ──────────────────────────────────────────────────
    pid_params = [
        ("Kc", loop.Kc_var, -100, 100, 6),
        ("Ti", loop.Ti_var, 0,    100, 6),
        ("Td", loop.Td_var, 0,    100, 6),
    ]
    for i, (name, var, lo, hi, col_idx) in enumerate(pid_params):
        ttk.Label(frame, text=name).grid(
            row=i * 2, column=col_idx, columnspan=2,
            padx=40, pady=(10 if i > 0 else 0, 0), sticky="nsew"
        )
        sb = ttk.Spinbox(
            frame, textvariable=var,
            from_=lo, to=hi, width=5, state="disabled",
        )
        sb.grid(row=i * 2 + 1, column=col_idx, padx=(40, 0), pady=(5, 10), sticky="ew")
        if name in ("Ti", "Td"):
            ttk.Label(frame, text="(min)").grid(
                row=i * 2 + 1, column=col_idx + 1,
                padx=(5, 0), pady=(5, 10), sticky="nsew"
            )
        widgets[f"{name}_spinbox"] = sb

    return widgets


# ══════════════════════════════════════════════════════════════════════════════
# Enable / disable helpers  (called by app.py on power toggle)
# ══════════════════════════════════════════════════════════════════════════════

def enable_loop_widgets(widgets: dict):
    """Enable all interactive widgets in a control loop panel."""
    states = {
        "setpoint_spinbox":  "normal",
        "measured_entry":    "readonly",
        "extra_entry":       "readonly",
        "extra_entry_2":     "readonly",
        "mode_switch":       "normal",
        "scale":             "normal",
        "manual_spinbox":    "normal",
        "valve_entry":       "readonly",
        "Kc_spinbox":        "normal",
        "Ti_spinbox":        "normal",
        "Td_spinbox":        "normal",
    }
    for role, state in states.items():
        if role in widgets:
            widgets[role].configure(state=state)


def disable_loop_widgets(widgets: dict):
    """Disable all interactive widgets in a control loop panel."""
    for role, widget in widgets.items():
        if role in ("pb_frame", "frame"):
            continue
        try:
            widget.configure(state="disabled")
        except tk.TclError:
            pass
