import json
import tempfile
import unittest
from pathlib import Path

from fknm.model import Route
from fknm.nmcli import NmcliError
from fknm.profiles import PROFILE_FIELDS
from fknm.status import (
    Interface, add_dns, add_route, ipv4_address, parse_interfaces, read_status, remove_dns, remove_route,
    resolv_summary, route_origin, route_text, tailscale_running,
)
from tests import fixtures
from tests.fakes import FakeRunner

SHOW = ["nmcli", "-t", "-f", ",".join(PROFILE_FIELDS), "connection", "show", "uuid"]


def status_runner(routes: str = fixtures.ROUTES, settings: str = fixtures.TOLILENG_SETTINGS) -> FakeRunner:
    runner = FakeRunner()
    runner.respond(["ip", "-j", "addr"], fixtures.ADDR)
    runner.respond(["ip", "-j", "route"], routes)
    runner.respond(["ip", "-j", "-6", "route"], fixtures.ROUTES6)
    runner.respond(fixtures.ACTIVE, fixtures.ACTIVE_LIST)
    runner.respond(SHOW + ["u1"], settings)
    runner.respond(fixtures.DEVICE_SHOW, fixtures.DEVICE_SHOW_OUT)
    return runner


def edit_runner(settings: str) -> FakeRunner:
    runner = FakeRunner()
    runner.respond(SHOW + ["u1"], settings)
    runner.respond(["nmcli", "connection", "modify"])
    runner.respond(["nmcli", "connection", "up"])
    return runner


def with_profile(routes: str = "", dns: str = "") -> str:
    return (fixtures.TOLILENG_SETTINGS.replace("ipv4.routes:\n", f"ipv4.routes:{routes}\n")
            .replace("ipv4.dns:\n", f"ipv4.dns:{dns}\n"))


class ParseTest(unittest.TestCase):
    def test_tailscale_running(self):
        self.assertFalse(tailscale_running(fixtures.ADDR))
        self.assertTrue(tailscale_running(fixtures.ADDR_TAILSCALE_WITH_INET))
        self.assertFalse(tailscale_running("[]"))

    def test_ipv4_address(self):
        self.assertEqual(ipv4_address(fixtures.ADDR, "wlan0"), "192.168.88.191/24")
        self.assertIsNone(ipv4_address(fixtures.ADDR, "tailscale0"))
        self.assertIsNone(ipv4_address(fixtures.ADDR, "eth9"))

    def test_interfaces_skip_lo_and_carry_profile(self):
        interfaces = parse_interfaces(fixtures.ADDR, {"wlan0": ("u1", "ToliLeng")})

        self.assertEqual([i.name for i in interfaces], ["enp197s0f4u1u1", "wlan0", "tailscale0", "virbr0"])
        self.assertEqual(interfaces[1], Interface("wlan0", "UP", "ToliLeng", "u1",
                                                  ["192.168.88.191/24", "fe80::a1fb:d68e:8f38:7ec4/64"]))
        self.assertIsNone(interfaces[2].profile)
        self.assertEqual(interfaces[0].addresses, [])

    def test_route_text_and_origin(self):
        default, lan, virbr = json.loads(fixtures.ROUTES)

        self.assertEqual(route_text(default), "default via 192.168.88.1 dev wlan0 metric 600")
        self.assertEqual(route_text(virbr), "192.168.122.0/24 dev virbr0 linkdown")
        self.assertEqual(route_text(json.loads(fixtures.ROUTES6)[1]), "fe80::/64 dev wlan0 metric 1024")
        self.assertEqual([route_origin(default, True), route_origin(lan, True), route_origin(virbr, False)],
                         ["DHCP", "kernel", "bez profilu"])
        self.assertEqual(route_origin({"protocol": "ra"}, True), "RA")
        self.assertEqual(route_origin({"protocol": "static"}, True), "profil")
        self.assertEqual(route_origin({"protocol": "boot"}, True), "boot")

    def test_resolv_summary(self):
        self.assertEqual(resolv_summary(fixtures.RESOLV), "127.0.0.53 (systemd-resolved)")
        self.assertEqual(resolv_summary("nameserver 1.1.1.1\nnameserver 9.9.9.9\n"), "1.1.1.1, 9.9.9.9")


class ReadStatusTest(unittest.TestCase):
    def read(self, runner: FakeRunner):
        with tempfile.TemporaryDirectory() as tmp:
            resolv = Path(tmp) / "resolv.conf"
            resolv.write_text(fixtures.RESOLV)
            return read_status(runner, resolv)

    def test_read_status(self):
        status = self.read(status_runner())

        self.assertFalse(status.tailscale)
        self.assertEqual(status.resolv, "127.0.0.53 (systemd-resolved)")
        wlan = next(i for i in status.interfaces if i.name == "wlan0")
        self.assertEqual((wlan.profile, wlan.uuid), ("ToliLeng", "u1"))
        virbr = next(i for i in status.interfaces if i.name == "virbr0")
        self.assertIsNone(virbr.profile)  # lo and virbr0 profiles are not ours to edit
        self.assertEqual([(r.text, r.origin) for r in status.routes], [
            ("default via 192.168.88.1 dev wlan0 metric 600", "DHCP"),
            ("192.168.88.0/24 dev wlan0 metric 600", "kernel"),
            ("192.168.122.0/24 dev virbr0 linkdown", "bez profilu"),
            ("fe80::/64 dev tailscale0 metric 256", "bez profilu"),
            ("fe80::/64 dev wlan0 metric 1024", "kernel")])
        self.assertTrue(all(r.route is None for r in status.routes))

    def test_profile_route_is_removable(self):
        settings = with_profile(routes="10.8.0.0/16 192.168.88.5 100")
        status = self.read(status_runner(fixtures.ROUTES_WITH_PROFILE, settings))

        entry = next(e for e in status.routes if e.text.startswith("10.8.0.0/16"))
        self.assertEqual((entry.origin, entry.route, entry.dev), ("profil", Route("10.8.0.0/16", "192.168.88.5", 100),
                                                                  "wlan0"))

    def test_static_default_route_is_not_removable(self):
        static_default = fixtures.ROUTES.replace('"protocol": "dhcp"', '"protocol": "static"')
        status = self.read(status_runner(static_default, with_profile()))

        default = status.routes[0]
        self.assertEqual((default.origin, default.route), ("profil", None))

    def test_dns_origins(self):
        runner = status_runner(settings=with_profile(dns="192.168.88.1"))
        status = self.read(runner)

        self.assertEqual([(d.server, d.dev, d.origin, d.removable) for d in status.dns],
                         [("192.168.88.239", "wlan0", "DHCP", False), ("192.168.88.1", "wlan0", "profil", True)])

    def test_failed_command_raises(self):
        runner = status_runner()
        runner.respond(["ip", "-j", "addr"], returncode=1, stderr="boom\n")

        with self.assertRaisesRegex(NmcliError, "boom"):
            self.read(runner)


class EditTest(unittest.TestCase):
    def modify_value(self, runner: FakeRunner, prop: str) -> str:
        modify = next(a for a in runner.argvs() if a[1:3] == ["connection", "modify"])
        return modify[modify.index(prop) + 1]

    def test_add_route_saves_and_reactivates(self):
        runner = edit_runner(fixtures.TOLILENG_SETTINGS)

        add_route(runner, "u1", "wlan0", Route("10.8.0.0/16", "192.168.88.5", 100))

        self.assertEqual(self.modify_value(runner, "ipv4.routes"), "10.8.0.0/16 192.168.88.5 100")
        self.assertEqual(runner.argvs()[-1], ["nmcli", "connection", "up", "uuid", "u1"])

    def test_remove_route(self):
        runner = edit_runner(with_profile(routes="10.8.0.0/16 192.168.88.5 100, 172.16.0.0/12 192.168.88.5"))

        remove_route(runner, "u1", "wlan0", Route("10.8.0.0/16", "192.168.88.5", 100))

        self.assertEqual(self.modify_value(runner, "ipv4.routes"), "172.16.0.0/12 192.168.88.5")

    def test_add_dns(self):
        runner = edit_runner(with_profile(dns="9.9.9.9"))

        add_dns(runner, "u1", "wlan0", "1.1.1.1")

        self.assertEqual(self.modify_value(runner, "ipv4.dns"), "9.9.9.9,1.1.1.1")

    def test_remove_dns(self):
        runner = edit_runner(with_profile(dns="1.1.1.1,9.9.9.9"))

        remove_dns(runner, "u1", "wlan0", "1.1.1.1")

        self.assertEqual(self.modify_value(runner, "ipv4.dns"), "9.9.9.9")
        self.assertEqual(runner.argvs()[-1], ["nmcli", "connection", "up", "uuid", "u1"])


class EapUntouchedTest(unittest.TestCase):
    def test_dns_edit_does_not_rewrite_eap(self):
        runner = edit_runner(fixtures.EDUROAM_SETTINGS.replace("connection.uuid:u5", "connection.uuid:u1"))

        add_dns(runner, "u1", "wlan0", "1.1.1.1")

        modify = next(a for a in runner.argvs() if a[1:3] == ["connection", "modify"])
        self.assertNotIn("802-1x.eap", modify)
