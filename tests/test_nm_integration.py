"""Checks against the real NetworkManager, on throwaway profiles only.

Run with ``FKNM_NM_TESTS=1``. Every profile is called ``fknm-test-*``, has
``autoconnect no`` and is never activated, so the current connection stays
as it is.
"""

import os
import re
import unittest

from fknm.model import Eap, Ipv4, Route
from fknm.nmcli import nmcli, parse_fields, run_command
from fknm.profiles import eap_args, read_settings, save, set_secrets


@unittest.skipUnless(os.environ.get("FKNM_NM_TESTS") == "1", "set FKNM_NM_TESTS=1 to touch NetworkManager")
class NetworkManagerTest(unittest.TestCase):
    def add(self, *args: str) -> str:
        out = nmcli(run_command, ["connection", "add", *args, "autoconnect", "no"])
        uuid = re.search(r"\(([0-9a-f-]{36})\)", out).group(1)
        self.addCleanup(run_command, ["nmcli", "connection", "delete", "uuid", uuid])
        return uuid

    def secret(self, uuid: str, prop: str) -> str:
        out = nmcli(run_command, ["-s", "-t", "-f", prop, "connection", "show", "uuid", uuid])
        return parse_fields(out)[prop]

    def test_secret_round_trip(self):
        uuid = self.add("type", "wifi", "con-name", "fknm-test-wifi", "ssid", "fknm-test-ssid",
                        "wifi-sec.key-mgmt", "wpa-psk")

        set_secrets(run_command, uuid, {"psk": "sp ace pw: \\x"})

        self.assertEqual(self.secret(uuid, "802-11-wireless-security.psk"), "sp ace pw: \\x")

    def test_settings_round_trip(self):
        uuid = self.add("type", "ethernet", "con-name", "fknm-test-eth", "ifname", "fknm-test0")
        settings = read_settings(run_command, uuid)
        settings.ipv4 = Ipv4("manual", ["10.99.0.5/24", "10.99.1.5/24"], "10.99.0.1", ["1.1.1.1", "9.9.9.9"], True,
                             [Route("10.8.0.0/16", "10.99.0.9", 100), Route("10.0.0.0/8", "", 50)], True)
        settings.autoconnect = False

        save(run_command, settings)
        self.assertEqual(read_settings(run_command, uuid).ipv4, settings.ipv4)

        settings.ipv4.method = "auto"
        save(run_command, settings)
        back = read_settings(run_command, uuid).ipv4
        self.assertEqual((back.method, back.addresses, back.gateway), ("auto", [], ""))
        self.assertEqual(back.dns, ["1.1.1.1", "9.9.9.9"])

    def test_eap_round_trip(self):
        eap = Eap("peap", identity="jan", domain="example.cz")
        uuid = self.add("type", "wifi", "con-name", "fknm-test-eap", "ssid", "fknm-test-eap",
                        "wifi-sec.key-mgmt", "wpa-eap", *eap_args(eap))

        set_secrets(run_command, uuid, {"password": "x y"})

        self.assertEqual(read_settings(run_command, uuid).eap, eap)
        self.assertEqual(self.secret(uuid, "802-1x.password"), "x y")
