"""Development GUI layout at desktop font/DPI sizes, using fake hardware."""

import os
from pathlib import Path
import subprocess
import sys
from tkinter import ttk
import unittest

from configs import airflow, nonnewtonian_1, nonnewtonian_2
from test_airflow import FakeAirflowDAQ
from test_nonnewtonian import FakeDAQ, assert_diagram_alignment
from ui_test_support import gui_root


@unittest.skipUnless(os.environ.get("LABJACK_GUI_TESTS") == "1", "requires a window server")
class DevelopmentLayoutTests(unittest.TestCase):
    def test_scaled_fonts_keep_readouts_separate_and_controls_reachable(self):
        requested_scale = os.environ.get("LABJACK_LAYOUT_SCALE")
        if requested_scale is None:
            # Tk caches font metrics; set scaling before loading any theme or
            # building widgets in a fresh process for each simulated DPI.
            for scale in (1.0, 4 / 3, 2.0):
                with self.subTest(scaling=scale):
                    result = subprocess.run(
                        [sys.executable, "-m", "unittest", "discover", "-s", "tests",
                         "-p", "test_development_layout.py", "-v"],
                        cwd=Path(__file__).resolve().parents[1],
                        env={**os.environ, "LABJACK_LAYOUT_SCALE": str(scale)},
                        capture_output=True, text=True, timeout=60,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return
        root = gui_root()
        original_scaling = root.tk.call("tk", "scaling")
        root.tk.call("tk", "scaling", float(requested_scale))
        style = ttk.Style(root)
        original_theme = style.theme_use()
        root.tk.call("set", "scalef", 1)
        assets = Path(__file__).resolve().parents[1] / "assets"
        for mode in ("light", "dark"):
            if f"forest-{mode}" not in style.theme_names():
                root.tk.call("source", str(assets / f"forest-{mode}.tcl"))
        errors = []
        original_handler = root.report_callback_exception
        root.report_callback_exception = lambda *exc: errors.append(exc)
        try:
            # Exercise real fonts at 72, 96 and 144 pixels per inch. These are
            # layout simulations; a native Windows run still verifies its fonts.
            themes = ["forest-light", "forest-dark", "clam"]
            themes += [name for name in ("vista", "xpnative", "winnative") if name in style.theme_names()]
            for theme in themes:
                style.theme_use(theme)
                for scaling in (float(requested_scale),):
                    for config in (airflow, nonnewtonian_1, nonnewtonian_2):
                        with self.subTest(theme=theme, scaling=scaling, system=config.SYSTEM_NAME):
                            daq = FakeAirflowDAQ() if config is airflow else FakeDAQ()
                            frame = config.FrameClass(root, config, daq)
                            try:
                                root.geometry("1200x720+0+40")
                                frame.pack(fill="both", expand=True)
                                root.deiconify()
                                root.update()
                                root.update_idletasks()
                                root.update()
                                self.assertEqual(daq.reads, [])
                                if config is airflow:
                                    items = [item for _, item in frame._delta_overlays]
                                    items += [item for _, item in frame._temperature_overlays]
                                    items += [frame._flow_overlay, frame._valve_overlay, frame._rotameter_overlay]
                                    entries = [frame._sensor_widgets[key]["entry"] for key in config.DELTA_P_KEYS]
                                    self.assertLessEqual(max(e.winfo_rooty() for e in entries) -
                                                         min(e.winfo_rooty() for e in entries), 1)
                                else:
                                    items = [item for _, _, item in frame._overlays]
                                    assert_diagram_alignment(self, frame)
                                bounds = [frame._pid.bbox(item) for item in items]
                                for left, top, right, bottom in bounds:
                                    self.assertGreaterEqual(left, 0)
                                    self.assertGreaterEqual(top, 0)
                                    self.assertLessEqual(right, frame._pid.winfo_width())
                                    self.assertLessEqual(bottom, frame._pid.winfo_height())
                                for index, a in enumerate(bounds):
                                    for b in bounds[index + 1:]:
                                        self.assertTrue(a[2] <= b[0] or b[2] <= a[0] or
                                                        a[3] <= b[1] or b[3] <= a[1], (a, b))
                                # Enlarged layouts may scroll, but neither axis
                                # may crop controls or make its far edge unreachable.
                                frame._canvas.xview_moveto(1)
                                frame._canvas.yview_moveto(1)
                                root.update()
                                self.assertAlmostEqual(frame._canvas.xview()[1], 1, delta=0.002)
                                self.assertAlmostEqual(frame._canvas.yview()[1], 1, delta=0.002)
                                for widgets in frame._loop_widgets.values():
                                    for role, widget in widgets.items():
                                        if role.endswith(("entry", "spinbox")):
                                            self.assertGreaterEqual(widget.winfo_width(), widget.winfo_reqwidth())
                                for tile in frame._sidebar.winfo_children():
                                    self.assertLessEqual(tile.winfo_x() + tile.winfo_width(), frame._sidebar.winfo_width())
                            finally:
                                frame.destroy()
                                root.withdraw()
                                root.update()
            self.assertEqual(errors, [])
        finally:
            root.report_callback_exception = original_handler
            root.tk.call("tk", "scaling", original_scaling)
            style.theme_use(original_theme)


if __name__ == "__main__":
    unittest.main()
