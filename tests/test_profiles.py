import unittest

from fknm.model import Eap, Ipv4, Profile, ProfileSettings, Route
from fknm.nmcli import NmcliError
from fknm.profiles import (
    PROFILE_FIELDS, activate, adapter_mac, deactivate, delete, eap_args, ethernet_state, list_profiles,
    profile_subtitle, read_settings, save, set_secrets, settings_args,
)
from tests import fixtures
from tests.fakes import FakeRunner

SHOW = ["nmcli", "-t", "-f", ",".join(PROFILE_FIELDS), "connection", "show", "uuid"]
UPDATED = "Connection 'x' (u1) successfully updated.\n"


def runner_with(settings_output: str) -> FakeRunner:
    runner = FakeRunner()
    runner.respond(SHOW, settings_output)
    return runner


def mutating_runner() -> FakeRunner:
    runner = FakeRunner()
    for verb in ("modify", "up", "down", "delete"):
        runner.respond(["nmcli", "connection", verb])
    runner.respond(["nmcli", "connection", "edit"], UPDATED)
    return runner


def wifi_settings() -> ProfileSettings:
    return ProfileSettings("u1", "ToliLeng", "wifi", ssid="ToliLeng", security="psk")


def ethernet_settings() -> ProfileSettings:
    return ProfileSettings("u4", "Wired connection 1", "ethernet", interface_name="enp197s0f4u1u1")


class ListProfilesTest(unittest.TestCase):
    def test_list_profiles_keeps_wifi_and_ethernet(self):
        runner = FakeRunner()
        runner.respond(["nmcli", "-t", "-f", "NAME,UUID,TYPE,DEVICE,ACTIVE,AUTOCONNECT,TIMESTAMP"],
                       fixtures.PROFILES_LIST)

        self.assertEqual(list_profiles(runner), [
            Profile("u1", "ToliLeng", "wifi", "wlan0", True, True, 1793392900),
            Profile("u4", "Wired connection 1", "ethernet", "", False, True, 0)])
        self.assertEqual(runner.argvs(), [["nmcli", "-t", "-f", "NAME,UUID,TYPE,DEVICE,ACTIVE,AUTOCONNECT,TIMESTAMP",
                                           "connection", "show"]])

    def test_escaped_name(self):
        runner = FakeRunner()
        runner.respond(["nmcli", "-t"], "Cafe\\: A:u9:802-11-wireless::no:no:5\n")

        self.assertEqual(list_profiles(runner)[0].name, "Cafe: A")

    def test_ethernet_state(self):
        runner = FakeRunner()
        runner.respond(["nmcli", "-t", "-f", "TYPE,STATE", "device"],
                       "wifi:connected\nethernet:unavailable\nloopback:connected (externally)\n")
        self.assertEqual(ethernet_state(runner), "unavailable")

        runner.respond(["nmcli", "-t", "-f", "TYPE,STATE", "device"], "wifi:connected\n")
        self.assertIsNone(ethernet_state(runner))


class ReadSettingsTest(unittest.TestCase):
    def test_read_settings_parses_probe_output(self):
        runner = runner_with(fixtures.PROBE_ETHERNET)
        s = read_settings(runner, "adafcb2c-b82c-4ac3-845a-7b2e09cf7dea")

        self.assertEqual(runner.argvs(), [SHOW + ["adafcb2c-b82c-4ac3-845a-7b2e09cf7dea"]])
        self.assertEqual((s.uuid, s.name, s.kind, s.autoconnect, s.interface_name),
                         ("adafcb2c-b82c-4ac3-845a-7b2e09cf7dea", "fknm-probe", "ethernet", False, "fknm-probe0"))
        self.assertEqual(s.ipv4, Ipv4("manual", ["10.99.0.5/24", "10.99.1.5/24"], "10.99.0.1",
                                      ["1.1.1.1", "9.9.9.9"], False,
                                      [Route("10.8.0.0/16", "10.99.0.9", 100), Route("172.16.0.0/12", "10.99.0.9")],
                                      False))
        self.assertIsNone(s.eap)

    def test_read_settings_wifi(self):
        s = read_settings(runner_with(fixtures.TOLILENG_SETTINGS), "u1")

        self.assertEqual((s.kind, s.ssid, s.security), ("wifi", "ToliLeng", "psk"))
        self.assertEqual(s.ipv4, Ipv4())

    def test_read_settings_open_wifi(self):
        open_wifi = fixtures.TOLILENG_SETTINGS.replace("802-11-wireless-security.key-mgmt:wpa-psk\n", "")

        self.assertEqual(read_settings(runner_with(open_wifi), "u1").security, "open")

    def test_read_settings_eap(self):
        s = read_settings(runner_with(fixtures.EDUROAM_SETTINGS), "u5")

        self.assertEqual(s.security, "eap")
        self.assertEqual(s.eap, Eap("peap", "mschapv2", "jan", "", "file", "/etc/ssl/certs/eduroam-vsb-ca.pem",
                                    "vsb.cz"))

    def test_read_settings_eap_system_ca(self):
        text = (fixtures.EDUROAM_SETTINGS
                .replace("802-1x.ca-cert:/etc/ssl/certs/eduroam-vsb-ca.pem", "802-1x.ca-cert:")
                .replace("802-1x.system-ca-certs:no", "802-1x.system-ca-certs:yes"))

        self.assertEqual(read_settings(runner_with(text), "u5").eap.ca_mode, "system")


class SettingsArgsTest(unittest.TestCase):
    def test_settings_args_dhcp_clears_static(self):
        s = ProfileSettings("u1", "ToliLeng", "wifi", ipv4=Ipv4("auto", ["10.0.0.5/24"], "10.0.0.1", ["1.1.1.1"]))

        self.assertEqual(settings_args(s), [
            "connection.id", "ToliLeng", "connection.autoconnect", "yes",
            "ipv4.method", "auto", "ipv4.addresses", "", "ipv4.gateway", "",
            "ipv4.dns", "1.1.1.1", "ipv4.ignore-auto-dns", "no",
            "ipv4.routes", "", "ipv4.ignore-auto-routes", "no"])

    def test_settings_args_manual(self):
        s = ProfileSettings("u1", "Lab", "wifi", autoconnect=False,
                            ipv4=Ipv4("manual", ["10.0.0.5/24", "10.0.1.5/24"], "10.0.0.1", ["1.1.1.1", "9.9.9.9"],
                                      True, [Route("10.8.0.0/16", "10.0.0.9", 100)], True))

        self.assertEqual(settings_args(s), [
            "connection.id", "Lab", "connection.autoconnect", "no",
            "ipv4.method", "manual", "ipv4.addresses", "10.0.0.5/24,10.0.1.5/24", "ipv4.gateway", "10.0.0.1",
            "ipv4.dns", "1.1.1.1,9.9.9.9", "ipv4.ignore-auto-dns", "yes",
            "ipv4.routes", "10.8.0.0/16 10.0.0.9 100", "ipv4.ignore-auto-routes", "yes"])

    def test_settings_args_disabled_clears_everything(self):
        s = ProfileSettings("u1", "Lab", "wifi", ipv4=Ipv4("disabled", ["10.0.0.5/24"], "10.0.0.1", ["1.1.1.1"],
                                                           routes=[Route("10.8.0.0/16")]))
        args = settings_args(s)

        for prop in ("ipv4.addresses", "ipv4.gateway", "ipv4.dns", "ipv4.routes"):
            self.assertEqual(args[args.index(prop) + 1], "", prop)

    def test_eap_args(self):
        self.assertEqual(eap_args(Eap("ttls", "pap", "jan", "anon", "system", "", "example.cz")), [
            "802-1x.eap", "ttls", "802-1x.identity", "jan", "802-1x.anonymous-identity", "anon",
            "802-1x.domain-suffix-match", "example.cz", "802-1x.phase2-auth", "pap",
            "802-1x.system-ca-certs", "yes", "802-1x.ca-cert", ""])

        tls = eap_args(Eap("tls", identity="jan", ca_mode="file", ca_cert="/ca.pem", client_cert="/c.pem",
                           private_key="/k.pem"))
        self.assertNotIn("802-1x.phase2-auth", tls)
        self.assertEqual(tls[-8:], ["802-1x.system-ca-certs", "no", "802-1x.ca-cert", "/ca.pem",
                                    "802-1x.client-cert", "/c.pem", "802-1x.private-key", "/k.pem"])

        unverified = eap_args(Eap("peap", identity="jan", ca_mode="none"))
        self.assertEqual(unverified[-4:], ["802-1x.system-ca-certs", "no", "802-1x.ca-cert", ""])


class SecretsTest(unittest.TestCase):
    def test_set_secrets_uses_editor_stdin(self):
        runner = FakeRunner()
        runner.respond(["nmcli", "connection", "edit"], UPDATED)

        set_secrets(runner, "u1", {"psk": "tajne heslo"})

        argv, stdin = runner.calls[-1]
        self.assertEqual(argv, ["nmcli", "connection", "edit", "uuid", "u1"])
        self.assertEqual(stdin, "nmcli save-confirmation no\nset 802-11-wireless-security.psk tajne heslo\n"
                                "save persistent\nquit\n")

    def test_set_secrets_eap(self):
        runner = FakeRunner()
        runner.respond(["nmcli", "connection", "edit"], UPDATED)

        set_secrets(runner, "u5", {"password": "x y", "key_password": "k"})

        self.assertIn("set 802-1x.password x y\nset 802-1x.private-key-password k\n", runner.calls[-1][1])

    def test_set_secrets_detects_editor_error(self):
        runner = FakeRunner()
        runner.respond(["nmcli", "connection", "edit"], "nmcli> Error: failed to set 'psk' property: invalid psk.\n")

        with self.assertRaises(NmcliError) as ctx:
            set_secrets(runner, "u1", {"psk": "x"})
        self.assertEqual(str(ctx.exception), "failed to set 'psk' property: invalid psk.")

    def test_set_secrets_without_confirmation(self):
        runner = FakeRunner()
        runner.respond(["nmcli", "connection", "edit"], "nmcli> quit\n")

        with self.assertRaisesRegex(NmcliError, "^nmcli neuložil heslo$"):
            set_secrets(runner, "u1", {"psk": "password1"})

    def test_set_secrets_rejects_untrimmable_value(self):
        runner = FakeRunner()

        with self.assertRaisesRegex(NmcliError, "^Heslo nesmí začínat ani končit mezerou.$"):
            set_secrets(runner, "u1", {"psk": " password1"})
        self.assertEqual(runner.calls, [])

    def test_no_secrets_no_call(self):
        runner = FakeRunner()
        set_secrets(runner, "u1", {})
        self.assertEqual(runner.calls, [])


class SaveTest(unittest.TestCase):
    def test_save_reactivates_and_keeps_secrets_out_of_argv(self):
        runner = mutating_runner()

        save(runner, wifi_settings(), {"psk": "tajne heslo"}, device="wlan0", reactivate=True)

        self.assertEqual([a[:3] for a in runner.argvs()], [["nmcli", "connection", "modify"],
                                                          ["nmcli", "connection", "edit"],
                                                          ["nmcli", "connection", "up"]])
        self.assertEqual(runner.argvs()[0][:5], ["nmcli", "connection", "modify", "uuid", "u1"])
        self.assertEqual(runner.argvs()[0][5:], settings_args(wifi_settings()))
        self.assertEqual(runner.argvs()[-1], ["nmcli", "connection", "up", "uuid", "u1"])
        self.assertFalse(any("tajne heslo" in " ".join(a) for a in runner.argvs()))

    def test_save_without_reactivate_does_not_touch_connection(self):
        runner = mutating_runner()

        save(runner, wifi_settings())

        self.assertEqual([a[:3] for a in runner.argvs()], [["nmcli", "connection", "modify"]])

    def test_save_eap_writes_eap_args(self):
        runner = mutating_runner()
        settings = wifi_settings()
        settings.security, settings.eap = "eap", Eap(identity="jan", domain="example.cz")

        save(runner, settings)

        self.assertEqual(runner.argvs()[0][-len(eap_args(settings.eap)):], eap_args(settings.eap))

    def test_save_ethernet_binds_mac(self):
        runner = mutating_runner()
        runner.respond(["ip", "-j", "link", "show", "enp197s0f4u1u1"], fixtures.ADAPTER_LINK)

        save(runner, ethernet_settings(), device="enp197s0f4u1u1")

        self.assertEqual(runner.argvs()[-1][-4:], ["802-3-ethernet.mac-address", "f4:a8:0d:67:d0:a7",
                                                   "connection.interface-name", ""])

    def test_save_ethernet_prefers_permaddr(self):
        runner = FakeRunner()
        runner.respond(["ip", "-j", "link", "show"],
                       '[{"ifname":"enx","address":"f4:a8:0d:67:d0:a7","permaddr":"aa:bb:cc:dd:ee:ff"}]')

        self.assertEqual(adapter_mac(runner, "enx"), "aa:bb:cc:dd:ee:ff")
        self.assertIsNone(adapter_mac(runner, ""))

    def test_save_ethernet_without_adapter_keeps_binding(self):
        runner = mutating_runner()
        runner.respond(["ip", "-j", "link", "show"], returncode=1,
                       stderr='Device "enp197s0f4u1u1" does not exist.\n')

        save(runner, ethernet_settings(), device="")

        self.assertIn(["ip", "-j", "link", "show", "enp197s0f4u1u1"], runner.argvs())
        self.assertNotIn("802-3-ethernet.mac-address", runner.argvs()[-1])

    def test_activate_deactivate_delete(self):
        runner = mutating_runner()

        activate(runner, "u1")
        deactivate(runner, "u1")
        delete(runner, "u1")

        self.assertEqual(runner.argvs(), [["nmcli", "connection", verb, "uuid", "u1"]
                                          for verb in ("up", "down", "delete")])


class SubtitleTest(unittest.TestCase):
    def test_profile_subtitle(self):
        active_wifi = Profile("u1", "ToliLeng", "wifi", "wlan0", True, True, 1)
        inactive_wifi = Profile("u6", "Lab", "wifi", "", False, True, 1)
        inactive_eth = Profile("u4", "Wired connection 1", "ethernet", "", False, True, 0)
        dhcp = ProfileSettings("u1", "x", "wifi")
        manual = ProfileSettings("u6", "Lab", "wifi",
                                 ipv4=Ipv4("manual", ["10.0.12.40/24"], dns=["10.0.12.1"]))
        disabled = ProfileSettings("u6", "Lab", "wifi", ipv4=Ipv4("disabled"))

        self.assertEqual(profile_subtitle(active_wifi, dhcp, None), "wlan0 · DHCP")
        self.assertEqual(profile_subtitle(inactive_eth, dhcp, "unavailable"), "kabel nezapojen · DHCP")
        self.assertEqual(profile_subtitle(inactive_eth, dhcp, None), "adaptér nepřipojen · DHCP")
        self.assertEqual(profile_subtitle(inactive_eth, dhcp, "disconnected"), "DHCP")
        self.assertEqual(profile_subtitle(inactive_wifi, manual, None), "ručně · 10.0.12.40/24 · DNS 10.0.12.1")
        self.assertEqual(profile_subtitle(inactive_wifi, disabled, None), "vypnuto")


class SecurityMappingTest(unittest.TestCase):
    def test_owe_profile_has_no_password(self):
        text = fixtures.TOLILENG_SETTINGS.replace("key-mgmt:wpa-psk", "key-mgmt:owe")
        self.assertEqual(read_settings(runner_with(text), "u1").security, "open")

    def test_unknown_key_mgmt_has_no_password(self):
        text = fixtures.TOLILENG_SETTINGS.replace("key-mgmt:wpa-psk", "key-mgmt:something-new")
        self.assertEqual(read_settings(runner_with(text), "u1").security, "open")

    def test_save_can_leave_eap_untouched(self):
        runner = mutating_runner()
        settings = wifi_settings()
        settings.security, settings.eap = "eap", Eap(identity="jan")

        save(runner, settings, write_eap=False)

        self.assertNotIn("802-1x.eap", runner.argvs()[0])
