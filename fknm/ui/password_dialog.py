"""Password for a new WPA2/WPA3 network."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from fknm.model import check_psk  # noqa: E402
from fknm.ui.form import FormDialog  # noqa: E402


class PasswordDialog(FormDialog):
    def __init__(self, ssid: str, security_label: str, on_connect):
        super().__init__(title=ssid, primary_label="Připojit", content_width=480)
        self._on_connect = on_connect
        self.connect_button = self.primary_button
        self.password_row = Adw.PasswordEntryRow(title="Heslo")
        self.password_row.connect("changed", lambda *_: self._validate())
        self.password_row.connect("entry-activated", lambda *_: self.connect_button.emit("clicked"))
        group = Adw.PreferencesGroup(description=f"Zabezpečení {security_label}")
        group.add(self.password_row)
        self.page.add(group)
        self._validate()
        self.set_focus(self.password_row)

    def on_primary(self) -> None:
        self._on_connect(self.password_row.get_text())

    def _validate(self) -> None:
        password = self.password_row.get_text()
        error = check_psk(password)
        self.connect_button.set_sensitive(error is None)
        # An empty field is not an error yet, just not ready.
        self.show_error(error if password else None)
