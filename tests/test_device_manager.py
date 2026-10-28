"""Device-manager requirements for development and commissioned systems."""

import importlib
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import requests

from configs import AVAILABLE_CONFIGS
from core.base_app import BaseAppFrame


class DeviceManagerTests(unittest.TestCase):
    def frame(self, config):
        # Exercise the actual connection callbacks without Tk or LabJack hardware.
        frame = object.__new__(getattr(config, "FrameClass", BaseAppFrame))
        frame.config = config
        frame.student_id_var = Mock()
        frame.student_id_var.get.return_value = ""
        frame._unit_op = "TestUnit"
        frame._connection_var = Mock()
        frame._connect = Mock()
        frame._disconnect = Mock()
        frame._polling = True
        frame.daq = SimpleNamespace(is_connected=True)
        frame.after = Mock()
        frame.winfo_toplevel = Mock()
        return frame

    def test_only_development_configs_disable_device_manager(self):
        for group in AVAILABLE_CONFIGS.values():
            for unit in group["units"]:
                with self.subTest(module=unit["module"]):
                    config = importlib.import_module(unit["module"])
                    self.assertEqual(
                        getattr(config, "DEVICE_MANAGER_ENABLED", True),
                        not group.get("development", False),
                    )

    def test_development_connections_need_no_id_or_api(self):
        for group in AVAILABLE_CONFIGS.values():
            if not group.get("development"):
                continue
            for unit in group["units"]:
                config = importlib.import_module(unit["module"])
                for choice in ("USB", "Ethernet"):
                    with self.subTest(module=unit["module"], choice=choice):
                        frame = self.frame(config)
                        with patch("core.base_app.requests.post") as post, \
                                patch("core.base_app.messagebox.showwarning") as warning, \
                                patch("tkinter.simpledialog.askstring", return_value="192.0.2.10"):
                            frame._on_connection_choice(choice)
                            frame._release_checkout()
                            frame._check_session_status()
                        frame._connect.assert_called_once_with(
                            "T7", "USB" if choice == "USB" else "ETHERNET",
                            "ANY" if choice == "USB" else config.ETHERNET_ADDRESS or "192.0.2.10",
                        )
                        frame.student_id_var.get.assert_not_called()
                        frame.after.assert_not_called()
                        warning.assert_not_called()
                        post.assert_not_called()

    def test_default_and_explicitly_enabled_require_id(self):
        for settings in ({}, {"DEVICE_MANAGER_ENABLED": True}):
            for choice in ("USB", "Ethernet"):
                with self.subTest(settings=settings, choice=choice):
                    frame = self.frame(SimpleNamespace(**settings))
                    with patch("core.base_app.requests.post") as post, \
                            patch("core.base_app.messagebox.showwarning") as warning:
                        frame._on_connection_choice(choice)
                    frame._connect.assert_not_called()
                    frame._connection_var.set.assert_called_once_with("Connect to LabJack")
                    warning.assert_called_once()
                    post.assert_not_called()

    def test_enabled_checkout_and_release_keep_existing_api_contract(self):
        frame = self.frame(SimpleNamespace(ETHERNET_ADDRESS="192.0.2.10"))
        frame.student_id_var.get.return_value = " 123456 "
        with patch("core.base_app.requests.post", return_value=Mock(status_code=200)) as post:
            frame._on_connection_choice("USB")
            post.assert_called_once_with(
                "http://10.5.112.172:5000/checkout",
                json={"student_id": "123456", "unit_op": "TestUnit", "force": False}, timeout=3,
            )
            frame._connect.assert_called_once_with("T7", "USB", "ANY")
            post.reset_mock()
            frame._release_checkout()
            post.assert_called_once_with(
                "http://10.5.112.172:5000/release",
                json={"unit_op": "TestUnit", "student_id": "123456"}, timeout=2,
            )

    def test_busy_machine_can_be_declined_or_taken_over(self):
        for take_over in (False, True):
            with self.subTest(take_over=take_over):
                frame = self.frame(SimpleNamespace())
                frame.student_id_var.get.return_value = "123456"
                busy = Mock(status_code=409)
                busy.json.return_value = {"current_user": "999999"}
                with patch("core.base_app.requests.post", side_effect=[busy, Mock(status_code=200)]) as post, \
                        patch("core.base_app.messagebox.askyesno", return_value=take_over) as prompt:
                    self.assertEqual(frame._attempt_checkout(), take_over)
                prompt.assert_called_once()
                self.assertEqual(post.call_count, 2 if take_over else 1)
                self.assertFalse(post.call_args_list[0].kwargs["json"]["force"])
                if take_over:
                    self.assertEqual(post.call_args_list[1].kwargs["json"],
                                     {"student_id": "123456", "unit_op": "TestUnit", "force": True})

    def test_heartbeat_detects_takeover_and_keeps_current_owner_connected(self):
        for owner in ("123456", "999999"):
            with self.subTest(owner=owner):
                frame = self.frame(SimpleNamespace())
                frame.student_id_var.get.return_value = " 123456 "
                response = Mock(status_code=200)
                response.json.return_value = {"current_user": owner}
                with patch("core.base_app.requests.post", return_value=response) as post, \
                        patch("core.base_app.messagebox.showwarning") as warning:
                    frame._check_session_status()
                post.assert_called_once_with(
                    "http://10.5.112.172:5000/status",
                    json={"unit_op": "TestUnit", "student_id": "123456"}, timeout=2)
                self.assertEqual(frame._disconnect.called, owner != "123456")
                self.assertEqual(warning.called, owner != "123456")
                frame.after.assert_called_once_with(3000, frame._check_session_status)

    def test_heartbeat_stops_after_shutdown_and_waits_when_disconnected(self):
        frame = self.frame(SimpleNamespace())
        frame._polling = False
        with patch("core.base_app.requests.post") as post:
            frame._check_session_status()
        post.assert_not_called()
        frame.after.assert_not_called()
        frame._polling = True
        frame.daq.is_connected = False
        with patch("core.base_app.requests.post") as post:
            frame._check_session_status()
        post.assert_not_called()
        frame.after.assert_called_once_with(3000, frame._check_session_status)

    def test_heartbeat_retries_after_temporary_api_outage(self):
        frame = self.frame(SimpleNamespace())
        frame.student_id_var.get.return_value = "123456"
        with patch("core.base_app.requests.post", side_effect=requests.exceptions.ConnectionError("offline")):
            frame._check_session_status()
        frame._disconnect.assert_not_called()
        frame.after.assert_called_once_with(3000, frame._check_session_status)

    def test_rejection_and_api_outage_still_block_enabled_systems(self):
        for failure in (False, True):
            with self.subTest(network_failure=failure):
                frame = self.frame(SimpleNamespace())
                frame.student_id_var.get.return_value = "123456"
                response = Mock(status_code=403)
                response.json.return_value = {"message": "Already checked out"}
                with patch("core.base_app.requests.post", return_value=response,
                           side_effect=requests.exceptions.ConnectionError("offline") if failure else None), \
                        patch("core.base_app.messagebox.showerror") as error:
                    frame._on_connection_choice("USB")
                frame._connect.assert_not_called()
                error.assert_called_once()
