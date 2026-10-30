"""Tests of the Profily tab. They need a display, so they skip without one."""

import unittest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from tests import fixtures  # noqa: E402
from tests.fakes import sync_background  # noqa: E402

HAS_DISPLAY = Gtk.init_check()
if HAS_DISPLAY:
    Adw.init()


@unittest.skipUnless(HAS_DISPLAY, "needs a display")
class ProfilesPageTest(unittest.TestCase):
    def setUp(self):
        self.runner = fixtures.standard_runner()
        for verb in ("up", "down", "delete"):
            self.runner.respond(["nmcli", "connection", verb])

    def make(self):
        from fknm.ui.window import MainWindow

        window = MainWindow(runner=self.runner, background=sync_background)
        self.addCleanup(window.destroy)
        window.view_stack.set_visible_child_name("profiles")
        return window, window.pages["profiles"]

    def test_only_wifi_and_ethernet_listed(self):
        _window, page = self.make()
        self.assertEqual([p.name for p in page.visible_profiles()], ["ToliLeng", "Wired connection 1"])

    def test_subtitles(self):
        _window, page = self.make()
        self.assertEqual([r.get_subtitle() for r in page.rows()], ["wlan0 · DHCP", "kabel nezapojen · DHCP"])

    def test_search(self):
        _window, page = self.make()
        page.search_entry.set_text("wired")
        self.assertEqual([p.name for p in page.visible_profiles()], ["Wired connection 1"])

    def test_toggle_active_deactivates(self):
        window, page = self.make()

        page.toggle_selected()

        self.assertIn(["nmcli", "connection", "down", "uuid", "u1"], self.runner.argvs())
        self.assertEqual(window.last_toast, "ToliLeng vypnut.")

    def test_toggle_inactive_activates(self):
        window, page = self.make()
        page.search_entry.set_text("Wired")

        page.toggle_selected()

        self.assertIn(["nmcli", "connection", "up", "uuid", "u4"], self.runner.argvs())
        self.assertEqual(window.last_toast, "Wired connection 1 zapnut.")

    def test_toggle_failure_toasts(self):
        self.runner.respond(["nmcli", "connection", "up"], returncode=10, stderr=(
            "Error: Connection activation failed: No suitable device found for this connection.\n"))
        window, page = self.make()
        page.search_entry.set_text("Wired")

        page.toggle_selected()

        self.assertEqual(window.last_toast,
                         "Nepřipojeno k Wired connection 1: zařízení není k dispozici (kabel nebo adaptér nezapojen?)")

    def test_delete_asks_first(self):
        window, page = self.make()

        page.delete_selected()

        dialog = window.get_visible_dialog()
        self.assertIsInstance(dialog, Adw.AlertDialog)
        self.assertEqual(dialog.get_heading(), "Smazat ToliLeng?")
        self.assertFalse(any(a[1:3] == ["connection", "delete"] for a in self.runner.argvs()))

        dialog.emit("response", "delete")
        self.assertIn(["nmcli", "connection", "delete", "uuid", "u1"], self.runner.argvs())
        self.assertEqual(window.last_toast, "ToliLeng smazán.")

    def test_edit_opens_dialog_with_device(self):
        from fknm.ui.profile_dialog import ProfileDialog

        window, page = self.make()
        page.edit_selected()
        self.assertIsInstance(window.get_visible_dialog(), ProfileDialog)

    def test_empty(self):
        self.runner.respond(["nmcli", "-t", "-f", "NAME,UUID,TYPE,DEVICE,ACTIVE,AUTOCONNECT,TIMESTAMP",
                             "connection", "show"], "")
        _window, page = self.make()
        self.assertEqual(page.stack.get_visible_child_name(), "empty")

    def test_hints(self):
        _window, page = self.make()
        self.assertEqual(page.hints(), [("Enter", "Zapnout/Vypnout"), ("Ctrl+E", "Upravit"), ("Delete", "Smazat"),
                                        ("Ctrl+1/2/3", "Záložky")])
