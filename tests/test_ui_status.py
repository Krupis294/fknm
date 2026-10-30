"""Tests of the Stav tab. They need a display, so they skip without one."""

import unittest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from fknm.profiles import PROFILE_FIELDS  # noqa: E402
from fknm.status import DnsEntry, Interface, RouteEntry  # noqa: E402
from tests import fixtures  # noqa: E402
from tests.fakes import sync_background  # noqa: E402

HAS_DISPLAY = Gtk.init_check()
if HAS_DISPLAY:
    Adw.init()

SHOW_U1 = ["nmcli", "-t", "-f", ",".join(PROFILE_FIELDS), "connection", "show", "uuid", "u1"]
WITH_ROUTE = fixtures.TOLILENG_SETTINGS.replace("ipv4.routes:\n", "ipv4.routes:10.8.0.0/16 192.168.88.5 100\n")


@unittest.skipUnless(HAS_DISPLAY, "needs a display")
class StatusPageTest(unittest.TestCase):
    def setUp(self):
        self.runner = fixtures.standard_runner()
        self.runner.respond(["nmcli", "connection", "modify"])
        self.runner.respond(["nmcli", "connection", "up"])

    def make(self):
        from fknm.ui.window import MainWindow

        window = MainWindow(runner=self.runner, background=sync_background)
        self.addCleanup(window.destroy)
        window.view_stack.set_visible_child_name("status")
        return window, window.pages["status"]

    def with_profile_route(self):
        self.runner.respond(["ip", "-j", "route"], fixtures.ROUTES_WITH_PROFILE)
        self.runner.respond(SHOW_U1, WITH_ROUTE)

    def row_for(self, page, text: str):
        return next(r for r in page.rows if getattr(r.entry, "text", None) == text)

    def test_sections_and_origins(self):
        _window, page = self.make()

        titles = [r.get_title() for r in page.rows]
        self.assertIn("wlan0 · ToliLeng", titles)
        self.assertIn("default via 192.168.88.1 dev wlan0 metric 600", titles)
        self.assertEqual(self.row_for(page, "default via 192.168.88.1 dev wlan0 metric 600").origin_label.get_text(),
                         "DHCP")
        self.assertIn("/etc/resolv.conf → 127.0.0.53 (systemd-resolved)", titles)
        self.assertEqual([r.get_text() for r in page.section_titles], ["Adresy", "Routy", "DNS"])
        kinds = {type(r.entry) for r in page.rows if r.entry is not None}
        self.assertEqual(kinds, {Interface, RouteEntry, DnsEntry})

    def test_interface_without_profile_is_read_only(self):
        _window, page = self.make()
        row = next(r for r in page.rows if isinstance(r.entry, Interface) and r.entry.name == "virbr0")
        self.assertIsNone(row.edit_button)
        self.assertEqual(row.origin_label.get_text(), "bez profilu")

    def test_remove_only_profile_items(self):
        self.with_profile_route()
        _window, page = self.make()

        removable = [r.entry.text for r in page.rows if r.remove_button is not None]
        self.assertEqual(removable, ["10.8.0.0/16 via 192.168.88.5 dev wlan0 metric 100"])

        page.listbox.select_row(self.row_for(page, "default via 192.168.88.1 dev wlan0 metric 600"))
        page.remove_selected()
        self.assertFalse(any(a[1:3] == ["connection", "modify"] for a in self.runner.argvs()))

    def test_remove_profile_route_saves(self):
        self.with_profile_route()
        window, page = self.make()

        page.listbox.select_row(self.row_for(page, "10.8.0.0/16 via 192.168.88.5 dev wlan0 metric 100"))
        page.remove_selected()

        modify = next(a for a in self.runner.argvs() if a[1:3] == ["connection", "modify"])
        self.assertEqual(modify[modify.index("ipv4.routes") + 1], "")
        self.assertIn(["nmcli", "connection", "up", "uuid", "u1"], self.runner.argvs())
        self.assertEqual(window.last_toast, "Uloženo.")

    def test_add_dialog_preselects_row_device(self):
        from fknm.ui.add_dialog import AddDialog

        window, page = self.make()
        page.listbox.select_row(self.row_for(page, "192.168.88.0/24 dev wlan0 metric 600"))
        page.add("route")

        dialog = window.get_visible_dialog()
        self.assertIsInstance(dialog, AddDialog)
        self.assertEqual(dialog.device_row.get_selected_item().get_string(), "wlan0")

    def test_add_dns_saves(self):
        window, page = self.make()

        page.add_value("dns", "u1", "1.1.1.1")

        modify = next(a for a in self.runner.argvs() if a[1:3] == ["connection", "modify"])
        self.assertEqual(modify[modify.index("ipv4.dns") + 1], "1.1.1.1")
        self.assertEqual(window.last_toast, "Uloženo.")

    def test_edit_selected_opens_profile(self):
        from fknm.ui.profile_dialog import ProfileDialog

        window, page = self.make()
        page.listbox.select_row(next(r for r in page.rows if isinstance(r.entry, Interface)
                                     and r.entry.name == "wlan0"))
        page.edit_selected()
        self.assertIsInstance(window.get_visible_dialog(), ProfileDialog)

    def test_refresh_failure_does_not_toast(self):
        self.runner.respond(["ip", "-j", "addr"], returncode=1, stderr="Cannot open netlink socket\n")
        window, page = self.make()

        self.assertIsNone(window.last_toast)
        self.assertTrue(page.error_label.get_visible())
        self.assertTrue(page.error_label.get_text().startswith("Stav nejde načíst:"))

        self.runner.respond(["ip", "-j", "addr"], fixtures.ADDR)
        page.refresh()
        self.assertFalse(page.error_label.get_visible())

    def test_refresh_skips_while_running(self):
        window, page = self.make()
        pending = []
        window.background = lambda fn, on_done: pending.append((fn, on_done))

        page.refresh()
        page.refresh()

        self.assertEqual(len(pending), 1)
        fn, on_done = pending[0]
        on_done(fn(), None)
        page.refresh()
        self.assertEqual(len(pending), 2)

    def test_live_timer_stops_when_hidden(self):
        window, page = self.make()
        self.assertIsNotNone(page._timer_id)

        window.view_stack.set_visible_child_name("wifi")
        self.assertIsNone(page._timer_id)

    def test_hints(self):
        _window, page = self.make()
        self.assertEqual(page.hints(), [("Ctrl+E", "Upravit rozhraní"), ("Delete", "Odebrat"), ("Ctrl+R", "Obnovit")])
