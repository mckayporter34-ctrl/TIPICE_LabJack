"""
=============================================================================
  Chemical Engineering Lab Control System
  LabJack T7 — Packed Columns Interface
=============================================================================
  Hardware: LabJack T7
  Inputs  : AIN0 (airFlowRate), AIN1 (waterFlowRate), AIN2 (pressureDrop1),
             AIN3 (pressureDrop2), AIN6 (waterTemperature)
  Outputs : TDAC0 (airFlowSet), DAC0 (waterValveOutSetpoint),
             DAC1 (waterFlow), FIO6 (mainPower), FIO7 (columnSelector)

  Screens:
    1. Dashboard    -- card-based equipment selector
    2. PackedColumn -- live sensor readouts + manual output controls
=============================================================================
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import os

# ---------------------------------------------------------------------------
# Optional dependency imports (app runs in simulation if unavailable)
# ---------------------------------------------------------------------------

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[Warning] Pillow not found — images will be blank placeholders.")
    print("         Install: python3 -m pip install pillow")

try:
    from labjack import ljm
    LJM_AVAILABLE = True
except ImportError:
    LJM_AVAILABLE = False
    print("[Warning] labjack-ljm not installed — simulated mode.")

# ---------------------------------------------------------------------------
# GLOBAL CONFIGURATION
# ---------------------------------------------------------------------------

# ---- Input channel map  (friendly label -> LabJack channel name) -----------
INPUTS = {
    "Air Flow Rate":      "AIN0",
    "Water Flow Rate":    "AIN1",
    "Pressure Drop 1":    "AIN2",
    "Pressure Drop 2":    "AIN3",
    "Water Temperature":  "AIN6",
}

# ---- Analog output definitions  (label -> (channel, min V, max V, units)) --
ANALOG_OUTPUTS = [
    ("Air Flow Setpoint",  "TDAC0", 0.0, 5.0, "V"),
    ("Water Exit Setpoint (Closed-0V, Open-5V)", "DAC0",  0.0, 5.0, "V"),
    ("Water Flow", "DAC1",  0.0, 5.0, "V"),
]

# ---- Digital output definitions  (label -> channel) -----------------------
DIGITAL_OUTPUTS = [
    ("Main Power",       "FIO6"),
    ("Column Selector",  "FIO7"),
]

# ---- GUI refresh period (ms) -----------------------------------------------
POLL_INTERVAL_MS = 500

# ---- Color theme -----------------------------------------------------------
C = {
    "bg":          "#0d1117",   # window background (near-black)
    "panel":       "#161b22",   # card / panel surface
    "panel2":      "#1c2128",   # secondary surface (sliders, switches)
    "blue":        "#2f81f7",   # active accent – packed column
    "orange":      "#e05f2a",   # heat exchanger accent (inactive)
    "green":       "#3fb950",   # methanation accent (inactive)
    "txt":         "#e6edf3",   # primary text
    "muted":       "#8b949e",   # secondary text
    "disabled":    "#484f58",   # disabled text
    "border":      "#30363d",   # borders
    "trough":      "#21262d",   # slider trough
    "on":          "#238636",   # switch ON
    "off":         "#b91c1c",   # switch OFF
    "warn":        "#d29922",   # warning / simulated badge
}

# ---------------------------------------------------------------------------
# LABJACK INTERFACE
# ---------------------------------------------------------------------------

class LabJackInterface:
    """
    Thin wrapper around the LabJack LJM library.
    If the native driver or Python package is missing, all operations
    fall back to simulation (prints to console, returns dummy values).
    """

    def __init__(self):
        self.handle = None
        self.connected = False
        self._open()

    # ---- Connection --------------------------------------------------------

    def _open(self):
        """Attempt to open the first T7 via USB or Ethernet."""
        if not LJM_AVAILABLE:
            print("[LJ] labjack-ljm package missing — simulated mode.")
            return
        try:
            self.handle = ljm.openS("T7", "ETHERNET", "10.8.112.59")
            info = ljm.getHandleInfo(self.handle)
            print(f"[LJ] Connected — serial {info[2]}")
            self.connected = True
        except AttributeError:
            # Native libLabJackM.dylib not installed
            print("[LJ] Native LJM driver not found — simulated mode.")
            print("     Download: https://support.labjack.com/docs/"
                  "ljm-software-installer-downloads-t4-t7-t8-digit")
        except Exception as e:
            print(f"[LJ] Connection error: {e} — simulated mode.")

    def close(self):
        """Close the device handle if open."""
        if self.handle and LJM_AVAILABLE:
            try:
                ljm.close(self.handle)
                print("[LJ] Connection closed.")
            except Exception:
                pass

    # ---- Reads -------------------------------------------------------------

    def read_analog(self, channel: str) -> float:
        """Return voltage on an analog input channel, or a fake value."""
        if not self.connected:
            import random
            return round(random.uniform(0.5, 4.5), 4)
        try:
            return ljm.eReadName(self.handle, channel)
        except Exception as e:
            print(f"[LJ] Read {channel}: {e}")
            return 0.0

    def read_all_inputs(self) -> dict:
        """Read every configured input. Returns {label: voltage}."""
        return {lbl: self.read_analog(ch) for lbl, ch in INPUTS.items()}

    # ---- Writes ------------------------------------------------------------

    def write_analog(self, channel: str, value: float):
        """Write a voltage to an analog output channel."""
        if not self.connected:
            print(f"[SIM] {channel} <- {value:.4f} V")
            return
        try:
            ljm.eWriteName(self.handle, channel, value)
        except Exception as e:
            print(f"[LJ] Write {channel}: {e}")

    def write_digital(self, channel: str, state: int):
        """Write a digital state (0 or 1) to a flexible-IO channel."""
        if not self.connected:
            print(f"[SIM] {channel} <- {'ON (1)' if state else 'OFF (0)'}")
            return
        try:
            ljm.eWriteName(self.handle, channel, state)
        except Exception as e:
            print(f"[LJ] Write {channel}: {e}")


# ---------------------------------------------------------------------------
# REUSABLE WIDGETS
# ---------------------------------------------------------------------------

class ToggleSwitch(tk.Frame):
    """
    Pill-shaped ON/OFF toggle switch.
    Fires on_change(state: int) when clicked.
    """

    W, H = 60, 28   # pill dimensions

    def __init__(self, parent, label="", on_change=None, **kw):
        super().__init__(parent, bg=C["panel2"], **kw)
        self._state = 0
        self._cb = on_change

        tk.Label(self, text=label, bg=C["panel2"], fg=C["muted"],
                 font=("Helvetica", 9), justify="center").pack(pady=(0, 4))

        self.cv = tk.Canvas(self, width=self.W, height=self.H,
                            bd=0, highlightthickness=0,
                            bg=C["panel2"], cursor="hand2")
        self.cv.pack()

        self._lbl = tk.Label(self, text="OFF", bg=C["panel2"],
                             fg=C["off"], font=("Helvetica", 9, "bold"))
        self._lbl.pack(pady=(4, 0))

        self._draw()
        self.cv.bind("<Button-1>", self._toggle)

    def _draw(self):
        self.cv.delete("all")
        w, h = self.W, self.H
        r = h // 2
        col = C["on"] if self._state else C["off"]
        self.cv.create_oval(0, 0, h, h, fill=col, outline="")
        self.cv.create_oval(w - h, 0, w, h, fill=col, outline="")
        self.cv.create_rectangle(r, 0, w - r, h, fill=col, outline="")
        p = 3
        kx = w - h + p if self._state else p
        self.cv.create_oval(kx, p, kx + h - 2*p, h - p, fill="white", outline="")

    def _toggle(self, _=None):
        self._state ^= 1
        self._draw()
        self._lbl.config(
            text="ON" if self._state else "OFF",
            fg=C["on"] if self._state else C["off"],
        )
        if self._cb:
            self._cb(self._state)

    def get(self) -> int:
        return self._state


# ---------------------------------------------------------------------------

class LabeledSlider(tk.Frame):
    """
    Labeled horizontal slider for an analog output channel.
    Fires on_change(float) on every movement.
    """

    def __init__(self, parent, label, channel, lo, hi, units,
                 on_change=None, **kw):
        super().__init__(parent, bg=C["panel2"], **kw)
        self._cb = on_change
        self._units = units

        # Header row
        hdr = tk.Frame(self, bg=C["panel2"])
        hdr.pack(fill="x", padx=10, pady=(8, 0))
        tk.Label(hdr, text=label, bg=C["panel2"], fg=C["txt"],
                 font=("Helvetica", 10, "bold")).pack(side="left")
        self._readout = tk.StringVar(value=f"0.00 {units}")
        tk.Label(hdr, textvariable=self._readout, bg=C["panel2"],
                 fg=C["blue"], font=("Helvetica", 10, "bold")).pack(side="right")

        # Channel info
        tk.Label(self, text=f"{channel}   {lo} – {hi} {units}",
                 bg=C["panel2"], fg=C["muted"],
                 font=("Helvetica", 8)).pack(anchor="w", padx=10)

        # Slider row
        row = tk.Frame(self, bg=C["panel2"])
        row.pack(fill="x", padx=10, pady=(2, 8))
        tk.Label(row, text=str(lo), bg=C["panel2"], fg=C["muted"],
                 font=("Helvetica", 8)).pack(side="left")

        self._var = tk.DoubleVar(value=0.0)
        tk.Scale(row, from_=lo, to=hi, orient="horizontal",
                 variable=self._var, resolution=0.01, showvalue=False,
                 bg=C["panel2"], fg=C["txt"], troughcolor=C["trough"],
                 activebackground=C["blue"], highlightthickness=0, bd=0,
                 command=self._moved).pack(side="left", fill="x", expand=True, padx=4)

        tk.Label(row, text=str(hi), bg=C["panel2"], fg=C["muted"],
                 font=("Helvetica", 8)).pack(side="left")

    def _moved(self, raw):
        v = float(raw)
        self._readout.set(f"{v:.2f} {self._units}")
        if self._cb:
            self._cb(v)

    def get(self) -> float:
        return self._var.get()


# ---------------------------------------------------------------------------

class SensorCard(tk.Frame):
    """
    Displays a single live sensor reading.
    Call update_value(float) from the GUI thread to refresh.
    """

    def __init__(self, parent, label, channel, units="V", **kw):
        super().__init__(parent, bg=C["panel"],
                         highlightbackground=C["border"],
                         highlightthickness=1, **kw)
        self._units = units

        tk.Label(self, text=channel, bg=C["panel"], fg=C["blue"],
                 font=("Helvetica", 8, "bold")).pack(anchor="w", padx=8, pady=(8, 0))

        self._var = tk.StringVar(value="—")
        tk.Label(self, textvariable=self._var, bg=C["panel"], fg=C["txt"],
                 font=("Helvetica", 22, "bold")).pack(padx=8)

        tk.Label(self, text=units, bg=C["panel"], fg=C["muted"],
                 font=("Helvetica", 9)).pack()

        tk.Label(self, text=label, bg=C["panel"], fg=C["muted"],
                 font=("Helvetica", 9)).pack(padx=8, pady=(2, 8))

    def update_value(self, value: float):
        """Refresh the displayed reading to 2 decimal places."""
        self._var.set(f"{value:.2f}")


# ---------------------------------------------------------------------------
# PACKED COLUMN PANEL
# ---------------------------------------------------------------------------

class PackedColumnPanel(tk.Frame):
    """
    Control panel for the Packed Column experiment.

    Left  — live sensor readouts (AIN0, AIN1, AIN2, AIN3, AIN6)
    Right — analog sliders (TDAC0, DAC0, DAC1) and toggle switches
             (FIO6 main power, FIO7 column selector), plus a write log.

    A daemon thread polls all inputs every POLL_INTERVAL_MS ms.
    The GUI is updated via tkinter's after() scheduler (never from the thread).
    """

    def __init__(self, parent, lj: LabJackInterface, on_back, **kw):
        super().__init__(parent, bg=C["bg"], **kw)
        self._lj = lj
        self._on_back = on_back
        self._polling = False
        self._readings = {k: 0.0 for k in INPUTS}
        self._build_ui()
        self._start_polling()

    # =========================================================================
    # UI construction
    # =========================================================================

    def _build_ui(self):
        self._build_header()

        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=14, pady=10)

        # Left column — sensor inputs
        left = tk.Frame(body, bg=C["bg"])
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self._build_inputs(left)

        # Right column — manual outputs
        right = tk.Frame(body, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))
        self._build_outputs(right)

    def _build_header(self):
        bar = tk.Frame(self, bg=C["panel"],
                       highlightbackground=C["border"], highlightthickness=1)
        bar.pack(fill="x")

        tk.Button(bar, text="← Dashboard", bg=C["panel"], fg=C["muted"],
                  font=("Helvetica", 10), relief="flat", cursor="hand2",
                  activebackground=C["panel2"], activeforeground=C["txt"],
                  padx=12, pady=8,
                  command=self._go_back).pack(side="left")

        tk.Label(bar, text="Packed Column — Control & Monitoring",
                 bg=C["panel"], fg=C["txt"],
                 font=("Helvetica", 14, "bold")).pack(side="left", padx=18, pady=10)

        status  = "● CONNECTED"  if self._lj.connected else "● SIMULATED"
        s_color = C["on"]        if self._lj.connected else C["warn"]
        tk.Label(bar, text=status, bg=C["panel"], fg=s_color,
                 font=("Helvetica", 9, "bold")).pack(side="right", padx=14)

    def _build_inputs(self, parent):
        tk.Label(parent, text="SENSOR INPUTS", bg=C["bg"], fg=C["muted"],
                 font=("Helvetica", 9, "bold")).pack(anchor="w", pady=(0, 6))

        # 2-column grid of sensor cards
        grid = tk.Frame(parent, bg=C["bg"])
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        sensors = [
            ("Air Flow Rate",     "AIN0", "V"),
            ("Water Flow Rate",   "AIN1", "V"),
            ("Pressure Drop 1",   "AIN2", "V"),
            ("Pressure Drop 2",   "AIN3", "V"),
            ("Water Temperature", "AIN6", "V"),
        ]

        self._cards = {}
        for i, (lbl, ch, u) in enumerate(sensors):
            row, col = divmod(i, 2)
            card = SensorCard(grid, label=lbl, channel=ch, units=u)
            card.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
            grid.rowconfigure(row, weight=1)
            self._cards[lbl] = card

    def _build_outputs(self, parent):
        tk.Label(parent, text="MANUAL OUTPUTS", bg=C["bg"], fg=C["muted"],
                 font=("Helvetica", 9, "bold")).pack(anchor="w", pady=(0, 6))

        # ── Analog sliders ───────────────────────────────────────────────────
        sf = tk.LabelFrame(parent, text=" Analog Outputs ",
                           bg=C["panel2"], fg=C["muted"],
                           font=("Helvetica", 9), bd=1,
                           highlightbackground=C["border"], highlightthickness=1)
        sf.pack(fill="x", pady=(0, 8))

        for lbl, ch, lo, hi, units in ANALOG_OUTPUTS:
            LabeledSlider(sf, label=lbl, channel=ch, lo=lo, hi=hi, units=units,
                          on_change=lambda v, c=ch: self._write_analog(c, v),
                          ).pack(fill="x", padx=6, pady=2)
            ttk.Separator(sf, orient="horizontal").pack(fill="x", padx=6)

        # ── Digital switches ─────────────────────────────────────────────────
        df = tk.LabelFrame(parent, text=" Digital Outputs ",
                           bg=C["panel2"], fg=C["muted"],
                           font=("Helvetica", 9), bd=1,
                           highlightbackground=C["border"], highlightthickness=1)
        df.pack(fill="x", pady=(0, 8))

        sw_row = tk.Frame(df, bg=C["panel2"])
        sw_row.pack(pady=14)

        for lbl, ch in DIGITAL_OUTPUTS:
            ToggleSwitch(sw_row,
                         label=f"{lbl}\n({ch})",
                         on_change=lambda s, c=ch: self._write_digital(c, s),
                         ).pack(side="left", padx=24)

        # ── Write log ────────────────────────────────────────────────────────
        lf = tk.LabelFrame(parent, text=" Output Log ",
                           bg=C["panel2"], fg=C["muted"],
                           font=("Helvetica", 9), bd=1)
        lf.pack(fill="both", expand=True)

        self._log = tk.Text(lf, height=7, bg=C["bg"], fg=C["muted"],
                            font=("Courier", 9), state="disabled",
                            relief="flat", padx=4, pady=4)
        self._log.pack(fill="both", expand=True, padx=4, pady=4)

    # =========================================================================
    # Write helpers
    # =========================================================================

    def _write_analog(self, channel: str, value: float):
        self._lj.write_analog(channel, value)
        self._log_entry(f"[ANALOG]  {channel:<6} <- {value:.3f} V")

    def _write_digital(self, channel: str, state: int):
        self._lj.write_digital(channel, state)
        self._log_entry(f"[DIGITAL] {channel:<6} <- {'ON (1)' if state else 'OFF (0)'}")

    def _log_entry(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self._log.config(state="normal")
        self._log.insert("end", f"[{ts}] {msg}\n")
        self._log.see("end")
        self._log.config(state="disabled")

    # =========================================================================
    # Background polling (daemon thread + after() scheduler)
    # =========================================================================

    def _start_polling(self):
        self._polling = True
        threading.Thread(target=self._poll_loop,
                         daemon=True, name="SensorPoller").start()
        self.after(POLL_INTERVAL_MS, self._refresh_gui)

    def _poll_loop(self):
        """Runs in background thread. Reads all inputs and stores them."""
        while self._polling:
            self._readings = self._lj.read_all_inputs()
            time.sleep(POLL_INTERVAL_MS / 1000.0)

    def _refresh_gui(self):
        """Runs in GUI thread via after(). Pushes latest readings to cards."""
        if not self._polling:
            return
        for lbl, card in self._cards.items():
            card.update_value(self._readings.get(lbl, 0.0))
        self.after(POLL_INTERVAL_MS, self._refresh_gui)

    # =========================================================================
    # Navigation
    # =========================================================================

    def _go_back(self):
        self._polling = False
        if self._on_back:
            self._on_back()


# ---------------------------------------------------------------------------
# EQUIPMENT DASHBOARD
# ---------------------------------------------------------------------------

class EquipmentCard(tk.Frame):
    """
    Clickable card for one piece of lab equipment.
    Active cards have hover effects and fire on_click().
    Inactive cards are visually dimmed with a 'Coming Soon' badge.
    """

    def __init__(self, parent, title, subtitle, img_path,
                 active=False, accent=C["blue"], on_click=None, **kw):
        super().__init__(parent, bg=C["panel"],
                         highlightbackground=accent if active else C["border"],
                         highlightthickness=2 if active else 1,
                         cursor="hand2" if active else "arrow",
                         **kw)

        self._active = active
        self._accent = accent
        self._on_click = on_click

        # ---- Image thumbnail -----------------------------------------------
        self._photo = None
        if PIL_AVAILABLE and os.path.exists(img_path):
            try:
                img = Image.open(img_path)
                img.thumbnail((200, 190))
                self._photo = ImageTk.PhotoImage(img)
            except Exception as e:
                print(f"[Card] Image error: {e}")

        img_lbl = tk.Label(self, image=self._photo, bg=C["panel"],
                           width=200, height=190)
        img_lbl.pack(pady=(10, 6))

        # ---- Text ----------------------------------------------------------
        title_fg = C["txt"] if active else C["disabled"]
        tk.Label(self, text=title, bg=C["panel"], fg=title_fg,
                 font=("Helvetica", 11, "bold"),
                 wraplength=190, justify="center").pack(padx=8)

        tk.Label(self, text=subtitle, bg=C["panel"],
                 fg=C["muted"] if active else C["disabled"],
                 font=("Helvetica", 9)).pack(pady=(2, 4))

        badge_txt = "● ACTIVE"      if active else "● COMING SOON"
        badge_fg  = accent           if active else C["disabled"]
        tk.Label(self, text=badge_txt, bg=C["panel"], fg=badge_fg,
                 font=("Helvetica", 8, "bold")).pack(pady=(0, 10))

        # ---- Interactions --------------------------------------------------
        if active:
            self.bind("<Button-1>", lambda _: self._click())
            self.bind("<Enter>",    lambda _: self._hover(True))
            self.bind("<Leave>",    lambda _: self._hover(False))
            for child in self.winfo_children():
                child.bind("<Button-1>", lambda _: self._click())
                child.bind("<Enter>",    lambda _: self._hover(True))
                child.bind("<Leave>",    lambda _: self._hover(False))

    def _click(self):
        if self._on_click:
            self._on_click()

    def _hover(self, entering: bool):
        self.config(highlightbackground="white" if entering else self._accent)


# ---------------------------------------------------------------------------

class Dashboard(tk.Frame):
    """
    Main landing screen with equipment selection cards.
    Only the Packed Column card is active/selectable.
    """

    def __init__(self, parent, on_packed_column, image_dir, **kw):
        super().__init__(parent, bg=C["bg"], **kw)
        self._on_pc = on_packed_column
        self._img_dir = image_dir
        self._build_ui()

    def _img(self, name):
        return os.path.join(self._img_dir, name)

    def _build_ui(self):
        # ── Header ───────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=C["panel"],
                       highlightbackground=C["border"], highlightthickness=1)
        hdr.pack(fill="x")

        tk.Label(hdr, text="⚗  Chemical Engineering Lab Control System",
                 bg=C["panel"], fg=C["txt"],
                 font=("Helvetica", 16, "bold")).pack(side="left", padx=20, pady=16)

        tk.Label(hdr, text="Select equipment to open",
                 bg=C["panel"], fg=C["muted"],
                 font=("Helvetica", 10)).pack(side="right", padx=20)

        # ── Section label ────────────────────────────────────────────────────
        tk.Label(self, text="AVAILABLE EQUIPMENT", bg=C["bg"], fg=C["muted"],
                 font=("Helvetica", 10, "bold")).pack(pady=(28, 12))

        # ── Cards (packed side-by-side) ──────────────────────────────────────
        row = tk.Frame(self, bg=C["bg"])
        row.pack()   # natural size, centered

        EquipmentCard(
            row,
            title="Packed Column",
            subtitle="1 Unit  ·  LabJack T7",
            img_path=self._img("packed_column.jpg"),
            active=True,
            accent=C["blue"],
            on_click=self._on_pc,
        ).pack(side="left", padx=16, pady=4)

        EquipmentCard(
            row,
            title="Shell & Tube\nHeat Exchanger",
            subtitle="3 Units",
            img_path=self._img("shell_tube_hx.jpg"),
            active=False,
            accent=C["orange"],
        ).pack(side="left", padx=16, pady=4)

        EquipmentCard(
            row,
            title="Catalytic\nMethanation",
            subtitle="2 Units",
            img_path=self._img("catalytic_methanation.jpg"),
            active=False,
            accent=C["green"],
        ).pack(side="left", padx=16, pady=4)

        # ── Footer note ──────────────────────────────────────────────────────
        tk.Label(self,
                 text="Inactive cards will be enabled in a future release.",
                 bg=C["bg"], fg=C["disabled"],
                 font=("Helvetica", 9, "italic")).pack(pady=(14, 0))


# ---------------------------------------------------------------------------
# ROOT APPLICATION
# ---------------------------------------------------------------------------

class App(tk.Tk):
    """
    Root window. Owns the LabJack connection and manages navigation between
    the Dashboard and equipment panels via frame swapping.
    """

    def __init__(self):
        super().__init__()
        self.title("Chemical Engineering Lab Control System")
        self.configure(bg=C["bg"])
        self.geometry("1200x740")
        self.minsize(960, 640)

        self._img_dir = os.path.dirname(os.path.abspath(__file__))
        self._frame = None

        # Open LabJack connection
        self._lj = LabJackInterface()

        # Build UI first, THEN show any dialogs (avoids blank-window issue)
        self._container = tk.Frame(self, bg=C["bg"])
        self._container.pack(fill="both", expand=True)

        self.show_dashboard()

        # Defer the simulation warning so the window renders first
        if not self._lj.connected:
            self.after(200, self._show_sim_warning)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _show_sim_warning(self):
        messagebox.showwarning(
            "LabJack Not Found",
            "No LabJack T7 detected.\n\n"
            "Running in SIMULATED mode.\n"
            "Sensor values are randomized; writes are printed to the console.\n\n"
            "Install the LJM driver to connect to real hardware:\n"
            "support.labjack.com → Downloads → LJM Software",
        )

    # ---- Navigation --------------------------------------------------------

    def show_dashboard(self):
        """Switch to the equipment-selection dashboard."""
        self._swap(Dashboard(self._container,
                             on_packed_column=self.show_packed_column,
                             image_dir=self._img_dir))

    def show_packed_column(self):
        """Switch to the Packed Column control panel."""
        self._swap(PackedColumnPanel(self._container,
                                     lj=self._lj,
                                     on_back=self.show_dashboard))

    def _swap(self, new_frame: tk.Frame):
        """Replace the current frame with a new one."""
        if self._frame is not None:
            self._frame.destroy()
        self._frame = new_frame
        self._frame.pack(fill="both", expand=True)

    # ---- Cleanup -----------------------------------------------------------

    def _on_close(self):
        self._lj.close()
        self.destroy()


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = App()
    app.mainloop()
