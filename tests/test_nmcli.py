import unittest

from fknm.nmcli import NmcliError, friendly_error, nmcli, parse_fields, run_command, split_terse
from tests.fakes import FakeRunner


class SplitTerseTest(unittest.TestCase):
    def test_split_terse_unescapes(self):
        self.assertEqual(split_terse(r"*:04\:F4\:1C\:B7\:AA\:A4:ToliLeng:73:WPA2:wlan0"),
                         ["*", "04:F4:1C:B7:AA:A4", "ToliLeng", "73", "WPA2", "wlan0"])
        self.assertEqual(split_terse(r"a\\b:c\:d:"), ["a\\b", "c:d", ""])

    def test_parse_fields_splits_on_first_colon(self):
        self.assertEqual(parse_fields("802-11-wireless.ssid:fknm probe:ssid\nipv4.method:auto\n\n"),
                         {"802-11-wireless.ssid": "fknm probe:ssid", "ipv4.method": "auto"})


class FriendlyErrorTest(unittest.TestCase):
    def test_friendly_errors(self):
        self.assertEqual(friendly_error(
            "Error: Connection activation failed: Secrets were required, but not provided.\n"), "špatné heslo")
        self.assertEqual(friendly_error("Error: No network with SSID 'X' found.\n"), "síť není v dosahu")
        self.assertEqual(friendly_error(
            "Error: Connection activation failed: No suitable device found for this connection.\n"),
            "zařízení není k dispozici (kabel nebo adaptér nezapojen?)")
        self.assertEqual(friendly_error("Error: foo bar.\n"), "foo bar.")
        self.assertEqual(friendly_error(""), "nmcli selhal")


class NmcliTest(unittest.TestCase):
    def test_nmcli_returns_stdout(self):
        runner = FakeRunner()
        runner.respond(["nmcli", "-t", "radio", "wifi"], "enabled\n")

        self.assertEqual(nmcli(runner, ["-t", "radio", "wifi"]), "enabled\n")
        self.assertEqual(runner.calls, [(["nmcli", "-t", "radio", "wifi"], None)])

    def test_nmcli_raises_friendly_error(self):
        runner = FakeRunner()
        runner.respond(["nmcli", "connection", "up"], returncode=4,
                       stderr="Error: No network with SSID 'X' found.\n")

        with self.assertRaises(NmcliError) as ctx:
            nmcli(runner, ["connection", "up", "uuid", "u1"])
        self.assertEqual(str(ctx.exception), "síť není v dosahu")


class RunCommandTest(unittest.TestCase):
    def test_run_command_forces_c_locale(self):
        self.assertEqual(run_command(["sh", "-c", "echo $LC_ALL"]).stdout, "C\n")

    def test_run_command_passes_stdin(self):
        self.assertEqual(run_command(["cat"], "tajne\n").stdout, "tajne\n")

    def test_run_command_missing_binary(self):
        self.assertEqual(run_command(["fknm-does-not-exist"]).returncode, 127)


class FakeRunnerTest(unittest.TestCase):
    def test_longest_prefix_wins_and_unknown_argv_fails(self):
        runner = FakeRunner()
        runner.respond(["nmcli"], "short")
        runner.respond(["nmcli", "connection"], "long")

        self.assertEqual(runner(["nmcli", "connection", "show"], None).stdout, "long")
        self.assertEqual(runner(["nmcli", "radio"], None).stdout, "short")
        with self.assertRaisesRegex(AssertionError, "ip"):
            runner(["ip", "-j", "addr"], None)
