# main.py
# Entry point for the BYU TIPICE LabJack Control System.
# Displays the Equipment Selection Dashboard and loads apparatus controllers.

import tkinter as tk
from tkinter import ttk, messagebox
import os
import importlib
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[Warning] Pillow not found — images will be blank placeholders.")

from core.labjack_interface import LabJackInterface
from core.base_app import BaseAppFrame
from configs import AVAILABLE_CONFIGS


# ── Color Theme (GitHub Dark style for dashboard) ───────────────────────────
C = {
    "bg":          "#0d1117",   # window background (near-black)
    "panel":       "#161b22",   # card / panel surface
    "txt":         "#e6edf3",   # primary text
    "muted":       "#8b949e",   # secondary text
    "disabled":    "#484f58",   # disabled text
    "border":      "#30363d",   # borders
    "active_border": "#ffffff"  # active hover border
}


class EquipmentCard(tk.Frame):
    """
    Clickable card representing one piece of lab equipment.
    Active cards have hover effects and fire on_click().
    Inactive cards are visually dimmed.
    """

    def __init__(self, parent, title, subtitle, img_path, active=True, accent="#2f81f7", on_click=None, **kw):
        super().__init__(parent, bg=C["panel"], highlightbackground=accent if active else C["border"],
                         highlightthickness=2 if active else 1, cursor="hand2" if active else "arrow", **kw)

        self._active = active
        self._accent = accent
        self._on_click = on_click

        # ── Image Thumbnail ──
        self._photo = None
        if PIL_AVAILABLE and os.path.exists(img_path):
            try:
                img = Image.open(img_path)
                img = img.resize((260, 200), Image.Resampling.LANCZOS)
                self._photo = ImageTk.PhotoImage(img)
            except Exception as e:
                print(f"[Card] Image error for {img_path}: {e}")

        img_lbl = tk.Label(self, image=self._photo, bg=C["panel"], width=260, height=200)
        img_lbl.pack(pady=(12, 6), padx=12)

        # ── Text Labels ──
        title_fg = C["txt"] if active else C["disabled"]
        title_lbl = tk.Label(self, text=title, bg=C["panel"], fg=title_fg,
                             font=("Helvetica", 12, "bold"), wraplength=250, justify="center")
        title_lbl.pack(padx=12, pady=(4, 2))

        sub_fg = C["muted"] if active else C["disabled"]
        sub_lbl = tk.Label(self, text=subtitle, bg=C["panel"], fg=sub_fg,
                           font=("Helvetica", 9), wraplength=250, justify="center")
        sub_lbl.pack(pady=(2, 6), padx=12)

        badge_txt = "● ACTIVE" if active else "● COMING SOON"
        badge_fg = accent if active else C["disabled"]
        badge_lbl = tk.Label(self, text=badge_txt, bg=C["panel"], fg=badge_fg,
                             font=("Helvetica", 8, "bold"))
        badge_lbl.pack(pady=(0, 12))

        # ── Hover and Click Bindings ──
        if active:
            self.bind("<Button-1>", lambda _: self._click())
            self.bind("<Enter>", lambda _: self._hover(True))
            self.bind("<Leave>", lambda _: self._hover(False))
            for child in (img_lbl, title_lbl, sub_lbl, badge_lbl):
                child.bind("<Button-1>", lambda _: self._click())
                child.bind("<Enter>", lambda _: self._hover(True))
                child.bind("<Leave>", lambda _: self._hover(False))

    def _click(self):
        if self._on_click:
            self._on_click()

    def _hover(self, entering: bool):
        self.config(highlightbackground=C["active_border"] if entering else self._accent)


class Dashboard(tk.Frame):
    """
    Main Landing Screen displaying the grid of equipment cards.
    """

    def __init__(self, parent, on_select_equipment, **kw):
        super().__init__(parent, bg=C["bg"], **kw)
        self._on_select = on_select_equipment
        self._build_ui()

    def _build_ui(self):
        # ── Header ──
        hdr = tk.Frame(self, bg=C["panel"], highlightbackground=C["border"], highlightthickness=1)
        hdr.pack(fill="x", side="top")

        tk.Label(hdr, text="⚗  BYU Chemical Engineering Lab Control System",
                 bg=C["panel"], fg=C["txt"], font=("Helvetica", 16, "bold")).pack(side="left", padx=25, pady=20)

        tk.Label(hdr, text="Select apparatus to begin control",
                 bg=C["panel"], fg=C["muted"], font=("Helvetica", 10)).pack(side="right", padx=25, pady=20)

        # ── Section title ──
        tk.Label(self, text="AVAILABLE APPARATUSES", bg=C["bg"], fg=C["muted"],
                 font=("Helvetica", 10, "bold")).pack(pady=(35, 15))

        # ── Grid container ──
        grid_container = tk.Frame(self, bg=C["bg"])
        grid_container.pack(fill="both", expand=True, padx=25, pady=10)

        # Layout cards in a flexible grid
        cols = 3
        for idx, (slug, info) in enumerate(AVAILABLE_CONFIGS.items()):
            row_idx, col_idx = divmod(idx, cols)
            
            # Setup click handler
            click_cb = (lambda s=slug: self._on_select(s)) if info["active"] else None

            card = EquipmentCard(
                grid_container,
                title=info["title"],
                subtitle=info["subtitle"],
                img_path=info["image"],
                active=info["active"],
                accent=info["accent"],
                on_click=click_cb
            )
            card.grid(row=row_idx, column=col_idx, padx=20, pady=20, sticky="nsew")

            grid_container.columnconfigure(col_idx, weight=1)
            grid_container.rowconfigure(row_idx, weight=1)


class MainApplication(tk.Tk):
    """
    Root window of the application. Manages theme sourcing, sharing
    the LabJack DAQ interface, and swapping frames.
    """

    def __init__(self):
        super().__init__()
        self.title("BYU TIPICE Lab Control System")
        self.geometry("1400x900")  # Default size
        self.minsize(1000, 700)
        self.configure(bg=C["bg"])

        # Initialize shared LabJack interface
        self._daq = LabJackInterface()

        # Load styling and themes
        self._init_styles()

        # Setup frame container
        self._container = tk.Frame(self, bg=C["bg"])
        self._container.pack(fill="both", expand=True)

        self._active_frame = None
        self.show_dashboard()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _init_styles(self):
        # Configure scaling based on screen size
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        scalef = min(sw / 1600.0, sh / 900.0)
        self.tk.eval(f"set scalef {scalef:.3f}")

        # Sourced from shared assets directory
        assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        try:
            self.tk.call("source", os.path.join(assets_dir, "forest-dark.tcl"))
            self.tk.call("source", os.path.join(assets_dir, "forest-light.tcl"))
            
            self.style = ttk.Style()
            self.style.theme_use("forest-dark")  # Default to forest-dark theme
            
            # Setup custom Label styles
            self.style.configure("Green.TLabel", foreground="green")
            self.style.configure("Red.TLabel", foreground="red")
        except Exception as e:
            print(f"[MainApp] Warning: Forest themes could not be loaded: {e}")

    def show_dashboard(self):
        """Switch view to landing page dashboard."""
        self.title("BYU TIPICE Lab Control System")
        self.geometry("1000x700")  # Standard size for dashboard
        self._swap_frame(Dashboard(self._container, on_select_equipment=self.launch_apparatus))

    def launch_apparatus(self, slug):
        """Switch view to selected control panel frame."""
        if slug not in AVAILABLE_CONFIGS:
            return

        config_info = AVAILABLE_CONFIGS[slug]
        
        # Dynamically load the config module
        try:
            config_module = importlib.import_module(config_info["module"])
            # Reload module to pick up changes in configuration parameters
            importlib.reload(config_module)
        except Exception as e:
            messagebox.showerror(
                "Configuration Error",
                f"Failed to load configuration module '{config_info['module']}'.\n\nError: {e}"
            )
            return

        self.title(f"{config_module.SYSTEM_NAME} - Control Panel")
        self.geometry("1450x900")  # Larger size for control panels
        
        FrameClass = getattr(config_module, "FrameClass", BaseAppFrame)
        panel_frame = FrameClass(
            self._container,
            config=config_module,
            daq=self._daq,
            on_back=self.show_dashboard
        )
        self._swap_frame(panel_frame)

    def _swap_frame(self, new_frame):
        if self._active_frame is not None:
            self._active_frame.destroy()
        self._active_frame = new_frame
        self._active_frame.pack(fill="both", expand=True)

    def _on_close(self):
        # Clean up frames (this safely shuts down threads, disconnects daq)
        if self._active_frame and hasattr(self._active_frame, "_disconnect"):
            try:
                self._active_frame._disconnect()
            except Exception:
                pass
        self._daq.disconnect()
        self.destroy()


if __name__ == "__main__":
    app = MainApplication()
    app.mainloop()
