import unittest

from fknm.model import Eap, WifiNetwork
from fknm.nmcli import NmcliError
from fknm.profiles import eap_args
from fknm.wifi import connect, connect_eap, disconnect, enable_radio, radio_state, saved_ssids, scan, sort_networks
from tests import fixtures
from tests.fakes import FakeRunner

NEW_UUID = "0b6c1d6e-1111-2222-3333-444455556666"
PROFILES = ["nmcli", "-t", "-f", "NAME,UUID,TYPE,DEVICE,ACTIVE,AUTOCONNECT,TIMESTAMP", "connection", "show"]


def scan_runner() -> FakeRunner:
    runner = FakeRunner()
    runner.respond(fixtures.SCAN_NO, fixtures.SCAN)
    runner.respond(fixtures.SCAN_YES, fixtures.SCAN)
    runner.respond(PROFILES, fixtures.PROFILES_LIST)
    runner.respond(fixtures.ssid_show("u1"), "802-11-wireless.ssid:ToliLeng\n")
    return runner


def connect_runner() -> FakeRunner:
    runner = FakeRunner()
    runner.respond(["nmcli", "connection", "add"], f"Connection 'x' ({NEW_UUID}) successfully added.\n")
    runner.respond(["nmcli", "connection", "edit"], f"Connection 'x' ({NEW_UUID}) successfully updated.\n")
    for verb in ("up", "down", "delete"):
        runner.respond(["nmcli", "connection", verb])
    runner.respond(["nmcli", "device", "wifi", "connect"])
    return runner


def new_psk_network() -> WifiNetwork:
    return WifiNetwork("Sousedi", 50, "sae", False, "wlan0")


class ScanTest(unittest.TestCase):
    def test_scan_unescapes_and_dedupes(self):
        nets = scan(scan_runner())

        self.assertEqual([(n.ssid, n.signal, n.security, n.in_use) for n in nets],
                         [("ToliLeng", 73, "psk", True), ("Cafe: A&B <x>", 62, "open", False),
                          ("Sousedi", 50, "sae", False), ("Firma", 30, "eap", False)])
        self.assertEqual(nets[0].profile_uuid, "u1")
        self.assertEqual(nets[0].device, "wlan0")

    def test_rescan_asks_nmcli_to_scan(self):
        runner = scan_runner()
        scan(runner, rescan=True)
        self.assertIn(fixtures.SCAN_YES, runner.argvs())

    def test_saved_profile_attached_newest_wins(self):
        runner = FakeRunner()
        runner.respond(PROFILES, "Old:u7:802-11-wireless::no:yes:10\nNew:u8:802-11-wireless::no:yes:20\n"
                                 "Kabel:u4:802-3-ethernet::no:yes:30\n")
        runner.respond(fixtures.ssid_show("u7"), "802-11-wireless.ssid:ToliLeng\n")
        runner.respond(fixtures.ssid_show("u8"), "802-11-wireless.ssid:ToliLeng\n")

        self.assertEqual(saved_ssids(runner), {"ToliLeng": "u8"})

    def test_sort_networks(self):
        nets = [WifiNetwork("weak", 10, "psk", False, "wlan0"), WifiNetwork("saved", 20, "psk", False, "wlan0", "u9"),
                WifiNetwork("strong", 90, "psk", False, "wlan0"), WifiNetwork("here", 5, "psk", True, "wlan0", "u1")]

        self.assertEqual([n.ssid for n in sort_networks(nets)], ["here", "saved", "strong", "weak"])

    def test_radio_state(self):
        runner = FakeRunner()
        runner.respond(["nmcli", "-t", "-f", "TYPE", "device"], "ethernet\nloopback\n")
        self.assertEqual(radio_state(runner), "missing")

        runner.respond(["nmcli", "-t", "-f", "TYPE", "device"], "wifi\nethernet\n")
        runner.respond(["nmcli", "-t", "radio", "wifi"], "disabled\n")
        self.assertEqual(radio_state(runner), "disabled")

        runner.respond(["nmcli", "-t", "radio", "wifi"], "enabled\n")
        self.assertEqual(radio_state(runner), "enabled")

    def test_enable_radio(self):
        runner = FakeRunner()
        runner.respond(["nmcli", "radio", "wifi", "on"])
        enable_radio(runner)
        self.assertEqual(runner.argvs(), [["nmcli", "radio", "wifi", "on"]])


class ConnectTest(unittest.TestCase):
    def test_connect_saved_activates_profile(self):
        runner = connect_runner()
        connect(runner, WifiNetwork("ToliLeng", 73, "psk", False, "wlan0", "u1"))
        self.assertEqual(runner.argvs(), [["nmcli", "connection", "up", "uuid", "u1"]])

    def test_connect_open(self):
        runner = connect_runner()
        connect(runner, WifiNetwork("Cafe", 40, "open", False, "wlan0"))
        self.assertEqual(runner.argvs(), [["nmcli", "device", "wifi", "connect", "Cafe", "ifname", "wlan0"]])

    def test_connect_new_psk(self):
        runner = connect_runner()

        connect(runner, new_psk_network(), password="tajne heslo")

        self.assertEqual(runner.argvs()[0], ["nmcli", "connection", "add", "type", "wifi", "con-name", "Sousedi",
                                             "ifname", "wlan0", "ssid", "Sousedi", "wifi-sec.key-mgmt", "sae"])
        self.assertEqual(runner.argvs()[1], ["nmcli", "connection", "edit", "uuid", NEW_UUID])
        self.assertIn("set 802-11-wireless-security.psk tajne heslo\n", runner.calls[1][1])
        self.assertEqual(runner.argvs()[2], ["nmcli", "connection", "up", "uuid", NEW_UUID])
        self.assertFalse(any("tajne heslo" in " ".join(a) for a in runner.argvs()))

    def test_wpa2_uses_wpa_psk(self):
        runner = connect_runner()
        connect(runner, WifiNetwork("Doma", 50, "psk", False, "wlan0"), password="password1")
        self.assertEqual(runner.argvs()[0][-1], "wpa-psk")

    def test_failed_new_connection_is_deleted(self):
        runner = connect_runner()
        runner.respond(["nmcli", "connection", "up"], returncode=4,
                       stderr="Error: Connection activation failed: Secrets were required, but not provided.\n")

        with self.assertRaises(NmcliError) as ctx:
            connect(runner, new_psk_network(), password="spatne heslo")

        self.assertEqual(str(ctx.exception), "špatné heslo")
        self.assertEqual(runner.argvs()[-1], ["nmcli", "connection", "delete", "uuid", NEW_UUID])

    def test_failed_secret_deletes_new_connection(self):
        runner = connect_runner()
        runner.respond(["nmcli", "connection", "edit"], "Error: invalid psk.\n")

        with self.assertRaises(NmcliError):
            connect(runner, new_psk_network(), password="password1")
        self.assertEqual(runner.argvs()[-1], ["nmcli", "connection", "delete", "uuid", NEW_UUID])

    def test_failed_saved_connection_is_kept(self):
        runner = connect_runner()
        runner.respond(["nmcli", "connection", "up"], returncode=4, stderr="Error: boom.\n")

        with self.assertRaises(NmcliError):
            connect(runner, WifiNetwork("ToliLeng", 73, "psk", False, "wlan0", "u1"))
        self.assertFalse(any(a[2] == "delete" for a in runner.argvs()))

    def test_connect_wep_refused(self):
        runner = connect_runner()

        with self.assertRaisesRegex(NmcliError, "^WEP sítě nejsou podporované.$"):
            connect(runner, WifiNetwork("Old", 40, "wep", False, "wlan0"))
        self.assertEqual(runner.calls, [])

    def test_connect_new_psk_without_password(self):
        with self.assertRaises(ValueError):
            connect(connect_runner(), new_psk_network())

    def test_connect_eap(self):
        runner = connect_runner()
        eap = Eap("peap", identity="jan", domain="example.cz")

        connect_eap(runner, "Firma", "wlan0", eap, {"password": "x y"})

        self.assertEqual(runner.argvs()[0][:13], ["nmcli", "connection", "add", "type", "wifi", "con-name", "Firma",
                                                  "ifname", "wlan0", "ssid", "Firma", "wifi-sec.key-mgmt", "wpa-eap"])
        self.assertEqual(runner.argvs()[0][13:], eap_args(eap))
        self.assertIn("set 802-1x.password x y\n", runner.calls[1][1])
        self.assertEqual(runner.argvs()[2], ["nmcli", "connection", "up", "uuid", NEW_UUID])

    def test_failed_eap_is_deleted(self):
        runner = connect_runner()
        runner.respond(["nmcli", "connection", "up"], returncode=4, stderr="Error: boom.\n")

        with self.assertRaises(NmcliError):
            connect_eap(runner, "Firma", "wlan0", Eap(identity="jan"), {"password": "x"})
        self.assertEqual(runner.argvs()[-1], ["nmcli", "connection", "delete", "uuid", NEW_UUID])

    def test_disconnect(self):
        runner = connect_runner()
        disconnect(runner, WifiNetwork("ToliLeng", 73, "psk", True, "wlan0", "u1"))
        self.assertEqual(runner.argvs(), [["nmcli", "connection", "down", "uuid", "u1"]])
