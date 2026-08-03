# main.py — Standalone Launcher for Catalytic Methanation Redesigned P&ID View
# =========================================================================

import sys
import os
import tkinter as tk
from tkinter import ttk

# Resolve workspace root directory and add it to sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from core.labjack_interface import LabJackInterface
from catalytic_methanation.Redesign.app import CatalyticMethanationRedesignFrame
import catalytic_methanation.Redesign.config as config

class StandaloneRedesignApp(tk.Tk):
    """
    Standalone Tkinter window class wrapping the redesigned P&ID Frame.
    """
    def __init__(self):
        super().__init__()
        self.title(config.SYSTEM_NAME)
        self.geometry("1450x800")
        self.minsize(1200, 700)
        self.configure(bg="#f5f5f5")

        # Initialize the hardware interface
        self._daq = LabJackInterface()

        # Load Forest theme from root assets directory
        self.style = ttk.Style()
        try:
            # Configure scaling based on screen size (required by forest tcl themes)
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            scalef = min(sw / 1600.0, sh / 900.0)
            self.tk.eval(f"set scalef {scalef:.3f}")

            assets_dir = os.path.join(root_dir, "assets")
            self.tk.call("source", os.path.join(assets_dir, "forest-dark.tcl"))
            self.tk.call("source", os.path.join(assets_dir, "forest-light.tcl"))
            self.style.theme_use("forest-light")
            
            # Setup custom Label styles matching the main application
            self.style.configure("Green.TLabel", foreground="green")
            self.style.configure("Red.TLabel", foreground="red")
        except Exception as e:
            print(f"[Redesign Launcher] Warning: Forest themes could not be loaded: {e}")

        # Instantiate and pack the redesigned GUI frame
        self.frame = CatalyticMethanationRedesignFrame(
            self,
            config=config,
            daq=self._daq,
            on_back=self.destroy
        )
        self.frame.pack(fill="both", expand=True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        # Shut down threads, close connections and destroy Tkinter loop
        if hasattr(self.frame, "_disconnect"):
            try:
                self.frame._disconnect()
            except Exception:
                pass
        self._daq.disconnect()
        self.destroy()


if __name__ == "__main__":
    app = StandaloneRedesignApp()
    app.mainloop()
