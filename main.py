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


# ── Color Theme ───────────────────────────
C = {
    "bg":          "#ffffff",   # window background (white)
    "panel":       "#ffffff",   # card / panel surface
    "txt":         "#313131",   # primary text
    "muted":       "#595959",   # secondary text
    "disabled":    "#a0a0a0",   # disabled text
    "border":      "#cccccc",   # borders
    "active_border": "#0072CE"  # active hover border
}


class EquipmentCard(tk.Frame):
    """
    Clickable card representing one piece of lab equipment or a group of equipment.
    If multiple units are available, shows a dropdown to select the unit and a Launch button.
    """

    def __init__(self, parent, title, subtitle, img_path, units, active=True, accent="#2f81f7", on_click=None, **kw):
        super().__init__(parent, bg=C["panel"], highlightbackground=C["border"],
                         highlightthickness=2 if active else 1, cursor="pointinghand" if active else "arrow", **kw)

        self._active = active
        self._accent = accent
        self._on_click = on_click
        self._units = units

        # Selected module variable
        self._selected_module = tk.StringVar()
        if active and self._units:
            self._selected_module.set(self._units[0]["module"])

        # ── Image Thumbnail (1:1 Aspect Ratio) ──
        self._photo = None
        if PIL_AVAILABLE and os.path.exists(img_path):
            try:
                img = Image.open(img_path)
                img = img.resize((150, 150), Image.Resampling.LANCZOS)
                self._photo = ImageTk.PhotoImage(img)
            except Exception as e:
                print(f"[Card] Image error for {img_path}: {e}")

        img_lbl = tk.Label(self, image=self._photo, bg=C["panel"], width=150, height=150)
        img_lbl.pack(side="left", pady=12, padx=(12, 8))

        # ── Right Side Frame (vertical stack for text and buttons) ──
        right_frame = tk.Frame(self, bg=C["panel"])
        right_frame.pack(side="left", fill="both", expand=True, pady=12, padx=(8, 12))

        # ── Text Labels ──
        title_fg = C["txt"] if active else C["disabled"]
        title_lbl = tk.Label(right_frame, text=title, bg=C["panel"], fg=title_fg,
                             font=("Helvetica", 16, "bold"), wraplength=200, justify="left")
        title_lbl.pack(anchor="w", pady=(0, 4))

        # ── Content Frame (Centering selectors and buttons vertically/horizontally) ──
        content_frame = tk.Frame(right_frame, bg=C["panel"])
        content_frame.pack(expand=True)

        # ── Dropdown or Text Label and Launch Button ──
        if active:
            if len(self._units) > 1:
                self._dropdown_values = [u["name"] for u in self._units]
                self._selected_name = tk.StringVar(value=self._dropdown_values[0])

                # Custom styled OptionMenu to fit the dashboard theme
                self._dropdown = tk.OptionMenu(
                    content_frame, self._selected_name, *self._dropdown_values,
                    command=self._on_dropdown_select
                )
                self._dropdown.config(
                    bg=C["panel"],
                    fg=C["txt"],
                    activebackground=C["border"],
                    activeforeground=C["txt"],
                    highlightbackground=C["panel"],
                    highlightcolor=C["panel"],
                    relief="flat",
                    font=("Helvetica", 12),
                    padx=10,
                    pady=4,
                    cursor="pointinghand"
                )
                self._dropdown["menu"].config(
                    bg=C["panel"],
                    fg=C["txt"],
                    activebackground=accent,
                    activeforeground="white",
                    relief="flat",
                    font=("Helvetica", 12)
                )
                self._dropdown.pack(pady=(2, 4))
            else:
                # Single unit: Add a static text label instead of a dropdown to keep visual symmetry
                unit_name = self._units[0]["name"] if self._units else "Unit #1"
                self._static_label = tk.Label(
                    content_frame,
                    text=unit_name,
                    bg=C["panel"],
                    fg=C["muted"],
                    font=("Helvetica", 12, "bold"),
                    pady=4
                )
                self._static_label.pack(pady=(2, 4))

            # Styled Launch Button (present on all active cards with black text color)
            self._launch_btn = tk.Button(
                content_frame,
                text="Launch Unit",
                bg=accent,
                fg="black",
                activebackground=self._darken_color(accent),
                activeforeground="black",
                relief="flat",
                bd=0,
                highlightthickness=0,
                font=("Helvetica", 10, "bold"),
                padx=15,
                pady=6,
                cursor="pointinghand",
                command=self._click
            )
            self._launch_btn.bind("<Enter>", lambda e: self._launch_btn.config(bg=self._lighten_color(accent)))
            self._launch_btn.bind("<Leave>", lambda e: self._launch_btn.config(bg=accent))
            self._launch_btn.bind("<ButtonPress-1>", lambda e: self._launch_btn.config(relief="sunken", bg=self._darken_color(accent)))
            self._launch_btn.bind("<ButtonRelease-1>", lambda e: self._launch_btn.config(relief="flat", bg=self._lighten_color(accent)))
            self._launch_btn.pack(pady=(2, 4))
        else:
            badge_txt = "● COMING SOON"
            badge_fg = C["disabled"]
            badge_lbl = tk.Label(content_frame, text=badge_txt, bg=C["panel"], fg=badge_fg,
                                 font=("Helvetica", 8, "bold"))
            badge_lbl.pack(pady=(0, 4))

        # ── Hover and Click Bindings ──
        if active:
            self.bind("<Enter>", lambda _: self._hover(True))
            self.bind("<Leave>", lambda _: self._hover(False))
            bindable_children = [img_lbl, right_frame, content_frame, title_lbl]
            if hasattr(self, "_static_label"):
                bindable_children.append(self._static_label)
            for child in bindable_children:
                child.bind("<Enter>", lambda _: self._hover(True))
                child.bind("<Leave>", lambda _: self._hover(False))

    def _on_dropdown_select(self, val):
        for u in self._units:
            if u["name"] == val:
                self._selected_module.set(u["module"])
                break

    def _lighten_color(self, hex_color):
        hover_map = {
            "#2f81f7": "#58a6ff",
            "#e05f2a": "#f78154",
            "#3fb950": "#56d364",
            "#ea4aaa": "#ff79c6",
        }
        return hover_map.get(hex_color, hex_color)

    def _darken_color(self, hex_color):
        dark_map = {
            "#2f81f7": "#1f59b6",
        }
        return dark_map.get(hex_color, hex_color)

    def _click(self):
        if self._on_click:
            self._on_click(self._selected_module.get())

    def _hover(self, entering: bool):
        self.config(highlightbackground=self._accent if entering else C["border"])


class Dashboard(tk.Frame):
    """
    Main Landing Screen displaying the grid of equipment cards.
    """

    def __init__(self, parent, on_select_equipment, daq, **kw):
        super().__init__(parent, bg=C["bg"], **kw)
        self._on_select = on_select_equipment
        self.daq = daq
        self._build_ui()

    def _build_ui(self):
        # ── Header ──
        hdr = tk.Frame(self, bg=C["panel"], highlightbackground=C["border"], highlightthickness=1)
        hdr.pack(fill="x", side="top")

        tk.Label(hdr, text="BYU Chemical Engineering Lab Control System",
                 bg=C["panel"], fg=C["txt"], font=("Helvetica", 20, "bold")).pack(side="left", padx=25, pady=12)

        # Right header block
        right_hdr = tk.Frame(hdr, bg=C["panel"])
        right_hdr.pack(side="right", padx=25, pady=12)

        tk.Label(right_hdr, text="Select system to begin control",
                 bg=C["panel"], fg=C["muted"], font=("Helvetica", 14)).pack(side="top", anchor="e")



        # ── Section title ──
        tk.Label(self, text="AVAILABLE SYSTEMS", bg=C["bg"], fg=C["muted"],
                 font=("Helvetica", 16, "bold")).pack(pady=(15, 2))

        # ── Grid container ──
        grid_container = tk.Frame(self, bg=C["bg"])
        grid_container.pack(fill="both", expand=True, padx=25, pady=5)

        # Layout cards in a flexible 2x2 grid
        cols = 2
        for idx, (slug, info) in enumerate(AVAILABLE_CONFIGS.items()):
            row_idx, col_idx = divmod(idx, cols)
            
            # Setup click handler
            click_cb = (lambda mod_name: self._on_select(mod_name)) if info["active"] else None

            card = EquipmentCard(
                grid_container,
                title=info["title"],
                subtitle=info["subtitle"],
                img_path=info["image"],
                units=info.get("units", []),
                active=info["active"],
                accent=info["accent"],
                on_click=click_cb
            )
            card.grid(row=row_idx, column=col_idx, padx=15, pady=8, sticky="nsew")

            grid_container.columnconfigure(col_idx, weight=1, uniform="cols")
            grid_container.rowconfigure(row_idx, weight=1, uniform="rows")


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
            self.style.theme_use("forest-light")  # Default to forest-light theme
            
            # Setup custom Label styles
            self.style.configure("Green.TLabel", foreground="green")
            self.style.configure("Red.TLabel", foreground="red")
        except Exception as e:
            print(f"[MainApp] Warning: Forest themes could not be loaded: {e}")

    def show_dashboard(self):
        """Switch view to landing page dashboard."""
        self.title("BYU TIPICE Lab Control System")
        self.geometry("1000x580")  # Optimized height for horizontal tiles layout
        self._swap_frame(Dashboard(self._container, on_select_equipment=self.launch_apparatus, daq=self._daq))

    def launch_apparatus(self, module_name):
        """Switch view to selected control panel frame."""
        # Validate that the module_name is one of our registered system modules
        valid_modules = []
        for group in AVAILABLE_CONFIGS.values():
            for unit in group.get("units", []):
                valid_modules.append(unit["module"])

        if module_name not in valid_modules:
            return

        # Dynamically load the config module
        try:
            config_module = importlib.import_module(module_name)
            # Reload module to pick up changes in configuration parameters
            importlib.reload(config_module)
        except Exception as e:
            messagebox.showerror(
                "Configuration Error",
                f"Failed to load configuration module '{module_name}'.\n\nError: {e}"
            )
            return

        self.title(f"{config_module.SYSTEM_NAME} - Control Panel")
        self.geometry("1450x800")  # Larger size for control panels
        
        # Maximize the window for all apparatus interfaces
        try:
            self.state('zoomed')
        except tk.TclError:
            pass
        try:
            self.attributes('-zoomed', True)
        except tk.TclError:
            pass

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
