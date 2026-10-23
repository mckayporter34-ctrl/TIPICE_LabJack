"""One Aqua/Tk application per test process, shared by GUI test classes."""

import atexit
import tkinter as tk
from unittest.mock import patch


_root = None


def gui_root():
    global _root
    if _root is None:
        # GUI regressions never send fake measurements to a real historian.
        historian = patch("core.data_logger.INFLUX_TOKEN", "")
        historian.start()
        atexit.register(historian.stop)
        _root = tk.Tk()
        _root.withdraw()
        atexit.register(_root.destroy)
    return _root
