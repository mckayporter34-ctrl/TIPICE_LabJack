"""
hx_autotuner.py
================
Automatic PI tuning for the Shell and Tube Heat Exchanger control loops.

Method: Relay Feedback (Åström-Hägglund)
-----------------------------------------
For each loop the tuner applies a relay (bang-bang) signal that switches
the output between a high and low value. The process oscillates in response.
The tuner measures:
    Pu  — ultimate period (time between oscillation peaks, in minutes)
    a   — oscillation amplitude in engineering units

From these it computes:
    Ku  = (4 * relay_amplitude) / (π * a)   — ultimate gain
    Kc  = 0.45 * Ku                          — PI proportional gain (Z-N)
    Ti  = Pu / 1.2                           — PI integral time (Z-N, minutes)

Loops tested (in order):
    1. Flowrate   — fastest loop, tested first
    2. Level      — medium speed
    3. Steam Pressure — slowest, tested last

Safety:
    - Press Ctrl+C at any time to abort and move to the safe shutdown state.
    - On exit: level valve closed (0 V), steam valve closed (0 V),
      flow valve open (5 V) — system returns to a safe manual state.
    - Each loop is tested at a conservative relay amplitude (20% of output
      range) to avoid large process excursions.
    - A maximum test duration is enforced per loop — if the process does not
      oscillate within that time the test is aborted and the loop is skipped.

Usage:
    python3 hx_autotuner.py

Requirements:
    - LabJack LJM library installed
    - pip install labjack-ljm
    - config.py must be in the same directory (pin assignments are read from it)
"""

import sys
import os
import time
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from labjack import ljm
import config

# ══════════════════════════════════════════════════════════════════════════════
# Tuning parameters — adjust these before running
# ══════════════════════════════════════════════════════════════════════════════

LOOPS = {
    "flowrate": {
        "label":           "Flowrate",
        "unit":            "GPM",
        "input_pin":       "AIN4",
        "output_pin":      "DAC1",
        "output_max":      5.0,          # V — DAC range
        "relay_center":    2.5,          # V — midpoint of valve range for relay
        "relay_amplitude": 1.0,          # V — relay switches ±this around center
        "setpoint":        15.0,         # GPM — target operating point for test
        "max_test_time":   120,          # seconds — abort if no oscillation found
        "min_cycles":      3,            # complete oscillation cycles to average
        "action":          "direct",     # "direct" = more output → more PV
    },
    "level": {
        "label":           "Level",
        "unit":            "ft",
        "input_pin":       "AIN5",
        "output_pin":      "DAC0",
        "output_max":      5.0,
        "relay_center":    2.5,
        "relay_amplitude": 1.0,
        "setpoint":        0.5,          # ft — target operating point for test
        "max_test_time":   300,          # seconds — level loops are slower
        "min_cycles":      3,
        "action":          "reverse",    # "reverse" = more output → less PV
    },
    "steam_pressure": {
        "label":           "Steam Pressure",
        "unit":            "psig",
        "input_pin":       "AIN7",
        "output_pin":      "TDAC0",
        "output_max":      10.0,         # V — LJTick-DAC range
        "relay_center":    5.0,
        "relay_amplitude": 2.0,
        "setpoint":        25.0,         # psig — target operating point for test
        "max_test_time":   300,
        "min_cycles":      3,
        "action":          "direct",
    },
}

# Calibration functions pulled directly from config.py
CALIBRATIONS = {
    "flowrate":       config._flowrate_gpm,
    "level":          lambda v: (
                          0.0 if 8.475 * v <= 4.05
                          else min(1.96, (v - 0.472) * (1.96 / (2.360 - 0.472)))
                      ),
    "steam_pressure": config._make_pressure_cal(0.0, 150.0),
}

# Safe shutdown voltages (manual fallback)
SAFE_STATE = {
    "DAC0":  0.0,    # level valve — closed
    "DAC1":  5.0,    # flow valve  — open
    "TDAC0": 0.0,    # steam valve — closed
}

READ_INTERVAL   = 0.2    # seconds between measurements during test
SETTLE_TIME     = 10.0   # seconds to let process settle before relay starts


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def safe_shutdown(handle):
    """Write all outputs to the safe manual state and close the connection."""
    print("\n" + "=" * 60)
    print("SAFE SHUTDOWN — returning to manual state:")
    for pin, voltage in SAFE_STATE.items():
        ljm.eWriteName(handle, pin, voltage)
        print(f"  {pin} → {voltage:.1f} V")
    ljm.close(handle)
    print("LabJack disconnected.")
    print("=" * 60)


def read_pv(handle, loop_cfg):
    """Read and calibrate the process variable for a loop."""
    v   = ljm.eReadName(handle, loop_cfg["input_pin"])
    key = loop_cfg["_key"]
    return CALIBRATIONS[key](v)


def configure_ain(handle):
    """Apply AIN channel settings from config.AIN_CONFIGS."""
    for ch, settings in config.AIN_CONFIGS.items():
        for reg, val in settings.items():
            ljm.eWriteName(handle, f"{ch}_{reg}", val)


# ══════════════════════════════════════════════════════════════════════════════
# Relay feedback tuning — one loop
# ══════════════════════════════════════════════════════════════════════════════

def tune_loop(handle, key, loop_cfg):
    """
    Run relay feedback test on one loop and return (Kc, Ti).
    Returns None if the test failed or was aborted.
    """
    label     = loop_cfg["label"]
    unit      = loop_cfg["unit"]
    out_pin   = loop_cfg["output_pin"]
    center    = loop_cfg["relay_center"]
    amp       = loop_cfg["relay_amplitude"]
    setpoint  = loop_cfg["setpoint"]
    max_time  = loop_cfg["max_test_time"]
    min_cyc   = loop_cfg["min_cycles"]
    action    = loop_cfg["action"]

    v_high = min(center + amp, loop_cfg["output_max"])
    v_low  = max(center - amp, 0.0)

    print(f"\n{'=' * 60}")
    print(f"TUNING: {label}")
    print(f"  Setpoint  : {setpoint} {unit}")
    print(f"  Relay     : {v_low:.2f} V ↔ {v_high:.2f} V")
    print(f"  Max time  : {max_time} s")
    print(f"  Press Ctrl+C to abort and shut down safely.")
    print(f"{'=' * 60}")

    # ── Step 1: Set output to centre and let process settle ───────────────────
    print(f"\nStep 1 — Setting output to {center:.2f} V and settling "
          f"for {SETTLE_TIME:.0f} s...")
    ljm.eWriteName(handle, out_pin, center)
    t_settle = time.time()
    while time.time() - t_settle < SETTLE_TIME:
        pv = read_pv(handle, loop_cfg)
        print(f"  {label}: {pv:.4f} {unit}   (settling...)", end="\r")
        time.sleep(READ_INTERVAL)
    print()

    # ── Step 2: Relay feedback ────────────────────────────────────────────────
    print(f"\nStep 2 — Starting relay feedback...")
    print(f"  {'Time(s)':<10} {'PV':<14} {'Output(V)':<12} {'State'}")
    print(f"  {'-'*50}")

    pv          = read_pv(handle, loop_cfg)
    # Initial relay state: if direct action, start high if PV < setpoint
    if action == "direct":
        relay_high = pv < setpoint
    else:
        relay_high = pv > setpoint

    crossings   = []      # timestamps of zero-crossings (PV crosses setpoint)
    peaks_high  = []      # PV values at high-relay peaks
    peaks_low   = []      # PV values at low-relay peaks
    pv_window   = []      # rolling window for peak detection
    prev_above  = pv > setpoint
    t_start     = time.time()
    last_cross  = t_start

    while True:
        elapsed = time.time() - t_start

        if elapsed > max_time:
            print(f"\n  TIMEOUT — no stable oscillation found in {max_time} s.")
            print(f"  Skipping {label}.")
            ljm.eWriteName(handle, out_pin, center)
            return None

        # Read PV
        pv = read_pv(handle, loop_cfg)
        pv_window.append(pv)
        if len(pv_window) > 10:
            pv_window.pop(0)

        # Detect setpoint crossing
        above = pv > setpoint
        if above != prev_above:
            t_cross = time.time()
            period_half = t_cross - last_cross

            # Record peak of the previous half-cycle
            if pv_window:
                if prev_above:
                    peaks_high.append(max(pv_window))
                else:
                    peaks_low.append(min(pv_window))

            crossings.append(t_cross)
            last_cross = t_cross
            pv_window  = []
            prev_above = above

            # Switch relay on crossing
            if action == "direct":
                relay_high = not above
            else:
                relay_high = above

        # Apply relay output
        v_out = v_high if relay_high else v_low
        ljm.eWriteName(handle, out_pin, v_out)

        state = "HIGH" if relay_high else "LOW "
        print(f"  {elapsed:<10.1f} {pv:<14.4f} {v_out:<12.2f} {state}", end="\r")

        # Check if we have enough complete cycles
        # A full cycle = 2 crossings
        complete_cycles = (len(crossings) - 1) // 2
        if complete_cycles >= min_cyc and len(crossings) >= 3:
            print(f"\n\n  Collected {complete_cycles} cycles — computing results...")
            break

        time.sleep(READ_INTERVAL)

    # ── Step 3: Compute Pu and oscillation amplitude ──────────────────────────
    # Each full period = time between every other crossing
    periods = []
    for i in range(0, len(crossings) - 2, 2):
        periods.append(crossings[i + 2] - crossings[i])

    Pu_seconds = sum(periods) / len(periods)
    Pu_minutes = Pu_seconds / 60.0

    # Oscillation amplitude = half the peak-to-peak swing
    if peaks_high and peaks_low:
        a = (sum(peaks_high) / len(peaks_high) - sum(peaks_low) / len(peaks_low)) / 2.0
    else:
        print("  Could not determine oscillation amplitude.")
        ljm.eWriteName(handle, out_pin, center)
        return None

    if a <= 0:
        print("  Oscillation amplitude is zero — check sensor and wiring.")
        ljm.eWriteName(handle, out_pin, center)
        return None

    # ── Step 4: Ziegler-Nichols PI formulas ───────────────────────────────────
    Ku = (4.0 * amp) / (math.pi * a)
    Kc = 0.45 * Ku
    Ti = Pu_minutes / 1.2

    # For reverse-acting loops Kc should be negative
    if action == "reverse":
        Kc = -abs(Kc)

    # ── Step 5: Return output to centre and report ────────────────────────────
    ljm.eWriteName(handle, out_pin, center)

    print(f"\n  Results for {label}:")
    print(f"    Ultimate period Pu : {Pu_seconds:.2f} s  ({Pu_minutes:.4f} min)")
    print(f"    Oscillation amp  a : {a:.4f} {unit}")
    print(f"    Ultimate gain   Ku : {Ku:.4f}")
    print(f"    ── Recommended PI ──────────────────")
    print(f"    Kc                 : {Kc:.4f}")
    print(f"    Ti                 : {Ti:.4f} min")

    return Kc, Ti


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    handle = None
    results = {}

    try:
        # ── Connect ───────────────────────────────────────────────────────────
        print("Connecting to LabJack T7...")
        handle = ljm.openS("T7", "ANY", "ANY")
        info   = ljm.getHandleInfo(handle)
        print(f"Connected [Serial: {info[2]}]")

        # ── Configure AIN channels ────────────────────────────────────────────
        print("Configuring AIN channels...")
        configure_ain(handle)

        # ── Initial safe state ────────────────────────────────────────────────
        print("Setting initial safe state...")
        for pin, voltage in SAFE_STATE.items():
            ljm.eWriteName(handle, pin, voltage)
        time.sleep(2.0)

        # ── Tune each loop ────────────────────────────────────────────────────
        for key, loop_cfg in LOOPS.items():
            loop_cfg["_key"] = key    # pass key through for calibration lookup

            print(f"\nReady to tune: {loop_cfg['label']}")
            print("Press Enter to start this loop, or type 'skip' to skip it.")
            user = input("> ").strip().lower()

            if user == "skip":
                print(f"Skipping {loop_cfg['label']}.")
                continue

            result = tune_loop(handle, key, loop_cfg)
            if result is not None:
                results[key] = result

            # Return all outputs to safe state between loops
            print("\nReturning to safe state between loops...")
            for pin, voltage in SAFE_STATE.items():
                ljm.eWriteName(handle, pin, voltage)
            time.sleep(3.0)

        # ── Final report ──────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("TUNING COMPLETE — Summary of recommended PI values")
        print("=" * 60)
        print(f"\nCopy these into config.py CONTROL_LOOP_CONFIGS:\n")

        for key, (Kc, Ti) in results.items():
            label = LOOPS[key]["label"]
            print(f'  "{key}":')
            print(f'      "pid_defaults": {{"Kc": {Kc:.4f}, '
                  f'"Ti": {Ti:.4f}, "Td": 0.0}},')
            print()

        if not results:
            print("  No loops were successfully tuned.")

        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\nAborted by user.")

    except ljm.LJMError as e:
        print(f"\nLabJack error: {e}")

    finally:
        if handle is not None:
            safe_shutdown(handle)


if __name__ == "__main__":
    main()
