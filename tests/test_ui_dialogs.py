"""Tests of the dialogs. They need a display, so they skip without one."""

import unittest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from fknm.model import Eap, Ipv4, ProfileSettings, Route  # noqa: E402
from tests import fixtures  # noqa: E402
from tests.fakes import sync_background  # noqa: E402

HAS_DISPLAY = Gtk.init_check()
if HAS_DISPLAY:
    Adw.init()

MANUAL_SETTINGS = ProfileSettings(
    "u1", "ToliLeng", "wifi", autoconnect=False, ssid="ToliLeng", security="psk",
    ipv4=Ipv4("manual", ["192.168.88.50/24"], "192.168.88.1", ["1.1.1.1"], True,
              [Route("10.8.0.0/16", "192.168.88.5", 100)], False))
EAP_SETTINGS = ProfileSettings("u5", "eduroam", "wifi", ssid="eduroam", security="eap",
                               eap=Eap("peap", "mschapv2", "jan", "", "file", "/ca.pem", "vsb.cz"))


@unittest.skipUnless(HAS_DISPLAY, "needs a display")
class ProfileDialogTest(unittest.TestCase):
    def make(self, settings=MANUAL_SETTINGS):
        from fknm.ui.profile_dialog import ProfileDialog

        self.saved, self.deleted = [], []
        return ProfileDialog(settings, on_save=lambda s, secrets: self.saved.append((s, secrets)),
                             on_delete=lambda: self.deleted.append(True))

    def test_profile_dialog_round_trips_settings(self):
        self.assertEqual(self.make().collect(), MANUAL_SETTINGS)

    def test_eap_profile_round_trips(self):
        d = self.make(EAP_SETTINGS)
        self.assertEqual(d.collect(), EAP_SETTINGS)
        self.assertFalse(d.password_row.get_visible())  # the 802.1X password lives in the EAP form

    def test_switching_to_dhcp_hides_addresses_and_keeps_dns(self):
        d = self.make()

        d.method_row.set_selected(0)

        self.assertFalse(d.addresses_group.get_visible())
        self.assertFalse(d.gateway_row.get_visible())
        self.assertTrue(d.dns_group.get_visible())
        self.assertEqual(d.collect().ipv4.method, "auto")

    def test_disabled_hides_dns_and_routes(self):
        d = self.make()
        d.method_row.set_selected(2)
        self.assertFalse(d.dns_group.get_visible())
        self.assertFalse(d.routes_group.get_visible())

    def test_invalid_route_disables_save(self):
        d = self.make()

        d.add_route_row()
        d.route_rows[-1].dest_entry.set_text("10.8.0.1/16")

        self.assertFalse(d.save_button.get_sensitive())
        self.assertEqual(d.validation_error(), "Cíl routy má nastavené bity hostu, správně je např. 10.8.0.0/16.")
        self.assertTrue(d.route_rows[-1].has_css_class("error"))

    def test_removing_rows_updates_settings(self):
        d = self.make()
        d.route_rows[0].remove_button.emit("clicked")
        d.dns_rows[0].remove_button.emit("clicked")

        self.assertEqual((d.collect().ipv4.routes, d.collect().ipv4.dns), ([], []))

    def test_save_passes_password_only_when_typed(self):
        d = self.make()
        d.save_button.emit("clicked")
        d.password_row.set_text("nove heslo")
        d.save_button.emit("clicked")

        self.assertEqual([secrets for _s, secrets in self.saved], [{}, {"psk": "nove heslo"}])

    def test_short_password_blocks_save(self):
        d = self.make()
        d.password_row.set_text("short")
        self.assertFalse(d.save_button.get_sensitive())

    def test_manual_without_address_blocks_save(self):
        d = self.make()
        d.address_rows[0].remove_button.emit("clicked")
        self.assertEqual(d.validation_error(), "Při ruční metodě je potřeba aspoň jedna adresa.")

    def test_show_error(self):
        d = self.make()
        d.show_error("unknown connection 'u1'.")
        self.assertTrue(d.error_label.get_visible())
        self.assertEqual(d.error_label.get_text(), "unknown connection 'u1'.")


@unittest.skipUnless(HAS_DISPLAY, "needs a display")
class WindowDialogsTest(unittest.TestCase):
    def setUp(self):
        from fknm.ui.window import MainWindow

        self.runner = fixtures.standard_runner()
        self.window = MainWindow(runner=self.runner, background=sync_background, pages=False)
        self.addCleanup(self.window.destroy)

    def test_save_error_keeps_dialog_open(self):
        self.runner.respond(["nmcli", "connection", "modify"], returncode=10,
                            stderr="Error: unknown connection 'u1'.\n")

        self.window.open_profile("u1", "wlan0")
        dialog = self.window.get_visible_dialog()
        dialog.save_button.emit("clicked")

        self.assertIs(self.window.get_visible_dialog(), dialog)
        self.assertEqual(dialog.error_label.get_text(), "unknown connection 'u1'.")

    def test_save_reactivates_active_profile_and_toasts(self):
        self.runner.respond(["nmcli", "connection", "modify"])
        self.runner.respond(["nmcli", "connection", "up"])

        self.window.open_profile("u1", "wlan0")
        self.window.get_visible_dialog().save_button.emit("clicked")

        self.assertIn(["nmcli", "connection", "up", "uuid", "u1"], self.runner.argvs())
        self.assertIsNone(self.window.get_visible_dialog())
        self.assertEqual(self.window.last_toast, "Uloženo.")

    def test_save_inactive_profile_does_not_reactivate(self):
        self.runner.respond(["nmcli", "connection", "modify"])

        self.window.open_profile("u4", "")
        self.window.get_visible_dialog().save_button.emit("clicked")

        self.assertFalse(any(a[1:3] == ["connection", "up"] for a in self.runner.argvs()))

    def test_open_eap_out_of_range(self):
        self.window.open_eap("Nikde")
        self.assertEqual(self.window.last_toast, "Síť Nikde není v dosahu.")

    def test_open_eap_connects(self):
        from fknm.ui.eap_form import EapDialog

        self.runner.respond(["nmcli", "connection", "add"],
                            "Connection 'Firma' (0b6c1d6e-1111-2222-3333-444455556666) successfully added.\n")
        self.runner.respond(["nmcli", "connection", "edit"], "successfully updated.\n")
        self.runner.respond(["nmcli", "connection", "up"])

        self.window.open_eap("Firma")
        dialog = self.window.get_visible_dialog()
        self.assertIsInstance(dialog, EapDialog)
        dialog.form.identity_row.set_text("jan")
        dialog.form.password_row.set_text("x y")
        dialog.form.domain_row.set_text("example.cz")
        dialog.connect_button.emit("clicked")

        self.assertEqual(self.window.last_toast, "Připojeno k Firma.")
        self.assertIsNone(self.window.get_visible_dialog())


@unittest.skipUnless(HAS_DISPLAY, "needs a display")
class SmallDialogsTest(unittest.TestCase):
    def test_password_dialog_blocks_invalid(self):
        from fknm.ui.password_dialog import PasswordDialog

        calls = []
        d = PasswordDialog("Sousedi", "WPA3", on_connect=calls.append)

        d.password_row.set_text(" password1")
        self.assertFalse(d.connect_button.get_sensitive())
        self.assertEqual(d.error_label.get_text(), "Heslo nesmí začínat ani končit mezerou.")
        d.connect_button.emit("clicked")
        self.assertEqual(calls, [])

        d.password_row.set_text("password1")
        d.connect_button.emit("clicked")
        self.assertEqual(calls, ["password1"])

    def test_eap_warning_and_tls_fields(self):
        from fknm.ui.eap_form import EapForm

        f = EapForm(None)
        self.assertTrue(f.warning.get_visible())
        f.domain_row.set_text("example.cz")
        self.assertFalse(f.warning.get_visible())
        f.ca_row.set_selected(2)  # Neověřovat
        self.assertTrue(f.warning.get_visible())

        f.method_row.set_selected(2)  # TLS
        self.assertFalse(f.phase2_row.get_visible())
        self.assertTrue(f.tls_group.get_visible())
        self.assertEqual(f.validation_error(), "Metoda TLS potřebuje klientský certifikát a soukromý klíč.")

    def test_eap_requires_identity_and_password_for_new_network(self):
        from fknm.ui.eap_form import EapForm

        f = EapForm(None)
        self.assertEqual(f.validation_error(), "Vyplň uživatele.")
        f.identity_row.set_text("jan")
        self.assertEqual(f.validation_error(), "Vyplň heslo.")
        f.password_row.set_text("x y")
        self.assertIsNone(f.validation_error())
        f.ca_row.set_selected(1)  # Soubor…
        self.assertEqual(f.validation_error(), "Vyber soubor s CA certifikátem.")

    def test_eap_secrets_only_non_empty(self):
        from fknm.ui.eap_form import EapForm

        f = EapForm(Eap(identity="jan"), saved=True)
        self.assertEqual(f.secrets(), {})
        self.assertIsNone(f.validation_error())  # a saved profile keeps its password
        f.password_row.set_text("x y")
        self.assertEqual(f.secrets(), {"password": "x y"})

    def test_eap_form_round_trip(self):
        from fknm.ui.eap_form import EapForm

        eap = Eap("ttls", "pap", "jan", "anon", "system", "", "example.cz")
        self.assertEqual(EapForm(eap, saved=True).eap(), eap)

    def test_add_dialog_route(self):
        from fknm.ui.add_dialog import AddDialog

        got = []
        d = AddDialog("route", [("wlan0", "u1"), ("enp197s0f4u1u1", "u4")], "enp197s0f4u1u1",
                      on_add=lambda u, v: got.append((u, v)))
        self.assertFalse(d.add_button.get_sensitive())
        d.dest_row.set_text("10.8.0.0/16")
        d.gateway_row.set_text("192.168.88.5")
        d.metric_row.set_text("100")
        d.add_button.emit("clicked")

        self.assertEqual(got, [("u4", Route("10.8.0.0/16", "192.168.88.5", 100))])

    def test_add_dialog_dns(self):
        from fknm.ui.add_dialog import AddDialog

        got = []
        d = AddDialog("dns", [("wlan0", "u1")], None, on_add=lambda u, v: got.append((u, v)))
        d.server_row.set_text("1.1.1")
        self.assertFalse(d.add_button.get_sensitive())
        d.server_row.set_text("1.1.1.1")
        d.add_button.emit("clicked")

        self.assertEqual(got, [("u1", "1.1.1.1")])

