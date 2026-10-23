"""Development access and equipment filtering without real hardware."""

import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from configs import AVAILABLE_CONFIGS
from main import Dashboard, EquipmentCard, MainApplication
from ui_test_support import gui_root


class DevelopmentAccessTests(unittest.TestCase):
    def application(self):
        return SimpleNamespace(
            _development_unlocked=False,
            _show_development_dashboard=Mock(),
            _container=object(), _daq=object(), _swap_frame=Mock(),
            title=Mock(), geometry=Mock(), launch_apparatus=Mock(), show_development=Mock(),
        )

    def test_cancel_and_wrong_password_keep_development_locked(self):
        for password in (None, "", "wrong", "DietCoke"):
            with self.subTest(password=password):
                app = self.application()
                with patch("main.simpledialog.askstring", return_value=password) as prompt, \
                        patch("main.messagebox.showerror") as error:
                    MainApplication.show_development(app)
                self.assertEqual(prompt.call_args.kwargs["show"], "*")
                self.assertFalse(app._development_unlocked)
                app._show_development_dashboard.assert_not_called()
                self.assertEqual(error.called, password is not None)

    def test_password_unlocks_and_returning_to_main_relocks(self):
        app = self.application()
        with patch("main.simpledialog.askstring", return_value="dietcoke"):
            MainApplication.show_development(app)
        self.assertTrue(app._development_unlocked)
        app._show_development_dashboard.assert_called_once()
        with patch("main.Dashboard") as dashboard:
            MainApplication.show_dashboard(app)
        self.assertFalse(app._development_unlocked)
        self.assertNotIn("development", dashboard.call_args.kwargs)

    def test_locked_development_modules_cannot_launch_directly(self):
        app = self.application()
        with patch("main.importlib.import_module") as load:
            for group in AVAILABLE_CONFIGS.values():
                if group.get("development"):
                    for unit in group["units"]:
                        MainApplication.launch_apparatus(app, unit["module"])
            MainApplication.launch_apparatus(app, "unregistered.module")
        load.assert_not_called()

    def test_development_launch_returns_to_development_selector(self):
        app = self.application()
        app._development_unlocked = True
        app.state = Mock()
        app.attributes = Mock()
        frame_class = Mock()
        config = SimpleNamespace(SYSTEM_NAME="Test System", FrameClass=frame_class)
        with patch("main.importlib") as loader:
            loader.import_module.return_value = config
            loader.reload.return_value = config
            for name in ("configs.airflow", "configs.nonnewtonian_1", "configs.nonnewtonian_2"):
                MainApplication.launch_apparatus(app, name)
                self.assertIs(frame_class.call_args.kwargs["on_back"], app._show_development_dashboard)


@unittest.skipUnless(os.environ.get("LABJACK_GUI_TESTS") == "1", "requires a window server")
class DashboardUITests(unittest.TestCase):
    def test_section_cards_and_top_navigation_buttons(self):
        root = gui_root()
        for development in (False, True):
            with self.subTest(development=development):
                navigate = Mock()
                frame = Dashboard(root, Mock(), object(), development=development,
                                  on_toggle_section=navigate)
                frame.pack(fill="both", expand=True)
                try:
                    def cards(widget):
                        for child in widget.winfo_children():
                            if isinstance(child, EquipmentCard):
                                yield child
                            else:
                                yield from cards(child)
                    modules = {unit["module"] for card in cards(frame) for unit in card._units}
                    expected = {unit["module"] for info in AVAILABLE_CONFIGS.values()
                                if bool(info.get("development")) == development for unit in info["units"]}
                    self.assertEqual(modules, expected)
                    self.assertEqual(len(list(cards(frame))), 2 if development else 3)
                    for width in (1000, 1150):
                        root.geometry(f"{width}x700")
                        root.deiconify()
                        root.update_idletasks()
                        button = frame._section_button
                        self.assertTrue(button.winfo_ismapped())
                        self.assertGreaterEqual(button.winfo_width(), button.winfo_reqwidth())
                        self.assertLessEqual(button.winfo_rootx() + button.winfo_width(),
                                             root.winfo_rootx() + root.winfo_width())
                    frame._section_button.invoke()
                    navigate.assert_called_once_with()
                finally:
                    frame.destroy()
                    root.withdraw()
