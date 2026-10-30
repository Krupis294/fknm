import subprocess
import unittest

import gi

gi.require_version("Pango", "1.0")
from gi.repository import Pango  # noqa: E402

from fknm.model import WifiNetwork  # noqa: E402
from fknm.rofi import (  # noqa: E402
    GUI_ENTRY, RESCAN_ENTRY, THEME_PATH, network_rows, rofi_command, run, status_mesg,
)
from tests import fixtures  # noqa: E402

NEW_UUID = "0b6c1d6e-1111-2222-3333-444455556666"


def visible_text(markup: str) -> str:
    """What rofi renders for a markup row; fails on invalid markup."""
    _ok, _attrs, text, _accel = Pango.parse_markup(markup, -1, "\0")
    return text


def done(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


class ScriptedRofi:
    """Answers rofi calls in order and records them; ``rofi -e`` always succeeds."""

    def __init__(self, *answers: subprocess.CompletedProcess):
        self.answers = list(answers)
        self.calls: list[tuple[list[str], str]] = []

    def __call__(self, argv, text):
        self.calls.append((argv, text))
        if argv[:2] == ["rofi", "-e"]:
            return done()
        return self.answers.pop(0)


def index_of(ssid: str) -> str:
    # Order of fixtures.SCAN after sorting: ToliLeng, Cafe, Sousedi, Firma.
    return str(["ToliLeng", "Cafe: A&B <x>", "Sousedi", "Firma"].index(ssid))


class RowsTest(unittest.TestCase):
    def test_rows_escape_markup(self):
        [row] = network_rows([WifiNetwork("Cafe: A&B <x>", 62, "open", False, "wlan0")])

        self.assertEqual(row.search, "Cafe: A&B <x>")
        self.assertIn("Cafe: A&B <x>", visible_text(row.display))
        self.assertIn("otevřená", visible_text(row.display))
        self.assertIn("▂▄▆█", visible_text(row.display))

    def test_rows_tag_connected_and_saved(self):
        rows = network_rows([WifiNetwork("ToliLeng", 73, "psk", True, "wlan0", "u1"),
                             WifiNetwork("Doma", 40, "psk", False, "wlan0", "u2")])

        self.assertTrue(visible_text(rows[0].display).endswith("Připojeno"))
        self.assertTrue(visible_text(rows[1].display).endswith("Uloženo"))

    def test_status_mesg(self):
        nets = [WifiNetwork("ToliLeng", 73, "psk", True, "wlan0", "u1")]

        self.assertEqual(visible_text(status_mesg(nets, fixtures.ADDR)),
                         "wlan0 · ToliLeng · 192.168.88.191/24 · ● tailscale")
        self.assertEqual(visible_text(status_mesg([], "[]")), "Nepřipojeno · ● tailscale")
        self.assertIn("#87d5a2", status_mesg([], fixtures.ADDR_TAILSCALE_WITH_INET))
        self.assertNotIn("#87d5a2", status_mesg([], "[]"))

    def test_rofi_command(self):
        self.assertEqual(rofi_command(None, None), ["rofi", "-dmenu", "-i", "-markup-rows", "-no-custom",
                                                    "-format", "i", "-p", "Wi-Fi"])
        self.assertEqual(rofi_command(THEME_PATH, "zpráva", password=True),
                         ["rofi", "-dmenu", "-password", "-p", "Heslo", "-l", "0", "-theme", str(THEME_PATH),
                          "-theme-str", 'entry { placeholder: "Heslo"; }', "-mesg", "zpráva"])

    def test_theme_file_exists(self):
        self.assertTrue(THEME_PATH.is_file())


class RunTest(unittest.TestCase):
    def setUp(self):
        self.runner = fixtures.standard_runner()
        self.runner.respond(["nmcli", "connection", "add"], f"Connection 'x' ({NEW_UUID}) successfully added.\n")
        self.runner.respond(["nmcli", "connection", "edit"], "successfully updated.\n")
        for verb in ("up", "delete"):
            self.runner.respond(["nmcli", "connection", verb])
        self.gui, self.eap = [], []

    def run_with(self, rofi: ScriptedRofi) -> int:
        return run(self.runner, rofi, None, open_gui=lambda: self.gui.append(True), open_eap=self.eap.append)

    def test_menu_rows_and_message(self):
        rofi = ScriptedRofi(done(returncode=1))

        self.assertEqual(self.run_with(rofi), 0)
        argv, text = rofi.calls[0]
        lines = text.splitlines()
        self.assertEqual(len(lines), 6)
        self.assertTrue(lines[-2].startswith(RESCAN_ENTRY))
        self.assertTrue(lines[-1].startswith(GUI_ENTRY))
        self.assertIn("wlan0 · ToliLeng · 192.168.88.191/24", visible_text(argv[argv.index("-mesg") + 1]))

    def test_new_psk_asks_password_and_connects(self):
        rofi = ScriptedRofi(done(index_of("Sousedi")), done("tajne heslo\n"))

        self.assertEqual(self.run_with(rofi), 0)

        self.assertIn("-password", rofi.calls[1][0])
        self.assertEqual(visible_text(rofi.calls[1][0][rofi.calls[1][0].index("-mesg") + 1]), "Sousedi · WPA3")
        self.assertIn(["nmcli", "connection", "up", "uuid", NEW_UUID], self.runner.argvs())
        self.assertFalse(any("tajne heslo" in " ".join(a) for a in self.runner.argvs()))
        self.assertIn("set 802-11-wireless-security.psk tajne heslo\n",
                      next(stdin for argv, stdin in self.runner.calls if argv[1:3] == ["connection", "edit"]))

    def test_password_cancelled(self):
        rofi = ScriptedRofi(done(index_of("Sousedi")), done(returncode=1))

        self.assertEqual(self.run_with(rofi), 0)
        self.assertFalse(any(a[1:3] == ["connection", "add"] for a in self.runner.argvs()))

    def test_wrong_password_shows_error(self):
        self.runner.respond(["nmcli", "connection", "up"], returncode=4,
                            stderr="Error: Connection activation failed: Secrets were required, but not provided.\n")
        rofi = ScriptedRofi(done(index_of("Sousedi")), done("spatne heslo\n"))

        self.assertEqual(self.run_with(rofi), 1)
        self.assertEqual(rofi.calls[-1][0], ["rofi", "-e", "Nepřipojeno k Sousedi: špatné heslo"])
        self.assertIn(["nmcli", "connection", "delete", "uuid", NEW_UUID], self.runner.argvs())

    def test_invalid_password_rejected_before_nmcli(self):
        rofi = ScriptedRofi(done(index_of("Sousedi")), done("short\n"))

        self.assertEqual(self.run_with(rofi), 1)
        self.assertEqual(rofi.calls[-1][0], ["rofi", "-e", "Heslo musí mít 8 až 63 znaků (nebo 64 hex znaků)."])
        self.assertFalse(any(a[1:3] == ["connection", "add"] for a in self.runner.argvs()))

    def test_open_network_connects(self):
        self.runner.respond(["nmcli", "device", "wifi", "connect"])
        rofi = ScriptedRofi(done(index_of("Cafe: A&B <x>")))

        self.assertEqual(self.run_with(rofi), 0)
        self.assertIn(["nmcli", "device", "wifi", "connect", "Cafe: A&B <x>", "ifname", "wlan0"], self.runner.argvs())

    def test_eap_opens_gui_dialog(self):
        rofi = ScriptedRofi(done(index_of("Firma")))

        self.assertEqual(self.run_with(rofi), 0)
        self.assertEqual(self.eap, ["Firma"])
        self.assertFalse(any(a[1:3] == ["connection", "add"] for a in self.runner.argvs()))

    def test_rescan_reopens_menu(self):
        rofi = ScriptedRofi(done("4"), done(returncode=1))

        self.assertEqual(self.run_with(rofi), 0)
        self.assertIn(fixtures.SCAN_YES, self.runner.argvs())
        self.assertEqual(len(rofi.calls), 2)

    def test_open_gui_entry(self):
        rofi = ScriptedRofi(done("5"))

        self.assertEqual(self.run_with(rofi), 0)
        self.assertEqual(self.gui, [True])

    def test_connected_network_does_nothing(self):
        rofi = ScriptedRofi(done(index_of("ToliLeng")))

        self.assertEqual(self.run_with(rofi), 0)
        self.assertFalse(any(a[1:3] == ["connection", "up"] for a in self.runner.argvs()))

    def test_radio_off_message(self):
        self.runner.respond(["nmcli", "-t", "radio", "wifi"], "disabled\n")
        rofi = ScriptedRofi()

        self.assertEqual(self.run_with(rofi), 1)
        self.assertEqual(rofi.calls, [(["rofi", "-e", "Wi-Fi je vypnutá. Zapni ji v fknm."], "")])

    def test_missing_card_message(self):
        self.runner.respond(["nmcli", "-t", "-f", "TYPE", "device"], "ethernet\n")
        rofi = ScriptedRofi()

        self.assertEqual(self.run_with(rofi), 1)
        self.assertEqual(rofi.calls, [(["rofi", "-e", "Žádná Wi-Fi karta."], "")])


class NetworkManagerDownTest(unittest.TestCase):
    def test_nmcli_failure_is_shown(self):
        runner = fixtures.standard_runner()
        runner.respond(["nmcli", "-t", "-f", "TYPE", "device"], returncode=8,
                       stderr="Error: NetworkManager is not running.\n")
        rofi = ScriptedRofi()

        self.assertEqual(run(runner, rofi, None, open_gui=lambda: None, open_eap=lambda _s: None), 1)
        self.assertEqual(rofi.calls, [(["rofi", "-e", "Sítě nejde načíst: NetworkManager is not running."], "")])
