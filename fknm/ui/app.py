"""Application entry point."""

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib  # noqa: E402

from fknm.nmcli import Runner, run_command  # noqa: E402
from fknm.ui.style import apply_style  # noqa: E402
from fknm.ui.window import MainWindow  # noqa: E402

APP_ID = "io.github.krupis294.Fknm"


class FknmApp(Adw.Application):
    """One instance only: a second ``fknm`` (or ``fknm --eap SSID`` from rofi) goes to the running window."""

    def __init__(self, runner: Runner):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self._runner = runner
        self.add_main_option("eap", 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING,
                             "Otevřít dialog 802.1X pro síť", "SSID")

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Control>q"])
        for index in (1, 2, 3):
            self.set_accels_for_action(f"win.tab-{index}", [f"<Control>{index}"])
        self.set_accels_for_action("win.refresh", ["<Control>r"])
        self.set_accels_for_action("win.edit", ["<Control>e"])

    def do_startup(self):
        Adw.Application.do_startup(self)
        apply_style()

    def do_command_line(self, command_line):
        options = command_line.get_options_dict().end().unpack()
        window = self.props.active_window or MainWindow(runner=self._runner, application=self)
        window.present()
        if ssid := options.get("eap"):
            window.open_eap(ssid)
        return 0


def main() -> int:
    return FknmApp(run_command).run(sys.argv)
