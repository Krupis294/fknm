"""Tests of the Wi-Fi tab. They need a display, so they skip without one."""

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
class WifiPageTest(unittest.TestCase):
    def setUp(self):
        self.runner = fixtures.standard_runner()

    def make(self):
        from fknm.ui.window import MainWindow

        window = MainWindow(runner=self.runner, background=sync_background)
        self.addCleanup(window.destroy)
        return window, window.pages["wifi"]

    def test_networks_listed_connected_first(self):
        _window, page = self.make()

        self.assertEqual([n.ssid for n in page.visible_networks()], ["ToliLeng", "Cafe: A&B <x>", "Sousedi", "Firma"])
        self.assertEqual(page.stack.get_visible_child_name(), "list")

    def test_connected_row_shows_address(self):
        _window, page = self.make()
        self.assertEqual(page.rows()[0].get_subtitle(), "192.168.88.191/24 · WPA2")

    def test_search_filters(self):
        _window, page = self.make()

        page.search_entry.set_text("caf")
        self.assertEqual([n.ssid for n in page.visible_networks()], ["Cafe: A&B <x>"])

        page.search_entry.set_text("zzz")
        self.assertEqual(page.stack.get_visible_child_name(), "no-results")

    def test_radio_off_shows_status_page(self):
        self.runner.respond(["nmcli", "-t", "radio", "wifi"], "disabled\n")
        self.runner.respond(["nmcli", "radio", "wifi", "on"])
        _window, page = self.make()

        self.assertEqual(page.stack.get_visible_child_name(), "off")
        page.enable_button.emit("clicked")
        self.assertIn(["nmcli", "radio", "wifi", "on"], self.runner.argvs())

    def test_missing_card_shows_status_page(self):
        self.runner.respond(["nmcli", "-t", "-f", "TYPE", "device"], "ethernet\nloopback\n")
        _window, page = self.make()
        self.assertEqual(page.stack.get_visible_child_name(), "missing")

    def test_no_networks_shows_empty(self):
        self.runner.respond(fixtures.SCAN_NO, "")
        _window, page = self.make()
        self.assertEqual(page.stack.get_visible_child_name(), "empty")

    def test_connect_new_psk_opens_password_dialog(self):
        from fknm.ui.password_dialog import PasswordDialog

        window, page = self.make()
        page.search_entry.set_text("Sousedi")
        page.connect_selected()

        self.assertIsInstance(window.get_visible_dialog(), PasswordDialog)

    def test_new_eap_opens_eap_dialog(self):
        from fknm.ui.eap_form import EapDialog

        window, page = self.make()
        page.search_entry.set_text("Firma")
        page.connect_selected()

        self.assertIsInstance(window.get_visible_dialog(), EapDialog)

    def test_connect_failure_toasts(self):
        self.runner.respond(fixtures.SCAN_NO, fixtures.SCAN.replace("*:ToliLeng", " :ToliLeng"))
        self.runner.respond(["nmcli", "connection", "up"], returncode=4,
                            stderr="Error: Connection activation failed: Secrets were required, but not provided.\n")
        window, page = self.make()

        page.search_entry.set_text("ToliLeng")
        page.connect_selected()

        self.assertEqual(window.last_toast, "Nepřipojeno k ToliLeng: špatné heslo")

    def test_open_network_connects_and_toasts(self):
        self.runner.respond(["nmcli", "device", "wifi", "connect"])
        window, page = self.make()

        page.search_entry.set_text("Cafe")
        page.connect_selected()

        self.assertIn(["nmcli", "device", "wifi", "connect", "Cafe: A&B <x>", "ifname", "wlan0"], self.runner.argvs())
        self.assertEqual(window.last_toast, "Připojeno k Cafe: A&B <x>.")

    def test_enter_on_connected_does_nothing(self):
        _window, page = self.make()
        calls = len(self.runner.calls)

        page.connect_selected()

        self.assertEqual(len(self.runner.calls), calls)

    def test_refresh_shortcut_rescans(self):
        _window, page = self.make()
        page.refresh_shortcut()
        self.assertIn(fixtures.SCAN_YES, self.runner.argvs())

    def test_edit_opens_profile_dialog(self):
        from fknm.ui.profile_dialog import ProfileDialog

        window, page = self.make()
        page.edit_selected()
        self.assertIsInstance(window.get_visible_dialog(), ProfileDialog)

    def test_hints(self):
        _window, page = self.make()
        self.assertEqual(page.hints(), [("Enter", "Připojit"), ("Ctrl+E", "Upravit"), ("Ctrl+R", "Skenovat"),
                                        ("Ctrl+1/2/3", "Záložky")])
