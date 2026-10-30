"""802.1X fields, shared by the profile dialog and the dialog for a new 802.1X network."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from fknm.model import Eap, check_secret  # noqa: E402
from fknm.ui.form import FileRow, FormDialog, combo_row  # noqa: E402

METHODS = [("peap", "PEAP"), ("ttls", "TTLS"), ("tls", "TLS")]
PHASE2 = [("mschapv2", "MSCHAPv2"), ("pap", "PAP"), ("gtc", "GTC")]
CA_MODES = [("system", "Systémové certifikáty"), ("file", "Soubor…"), ("none", "Neověřovat")]
WARNING = ("⚠ Bez CA certifikátu a domény nejde ověřit, že je to opravdu tvoje síť. "
           "Heslo by mohla ukrást falešná síť se stejným názvem.")


def _index(options: list[tuple[str, str]], value: str) -> int:
    return next((i for i, (key, _label) in enumerate(options) if key == value), 0)


class EapForm:
    """``saved``: the profile already has its secrets, so empty password fields keep them."""

    def __init__(self, eap: Eap | None, saved: bool = False, on_change=None):
        eap = eap or Eap()
        self._saved = saved
        self._on_change = on_change
        changed = self._changed

        self.method_row = combo_row("Metoda EAP", [label for _k, label in METHODS], _index(METHODS, eap.method),
                                    changed)
        self.phase2_row = combo_row("Vnitřní ověření", [label for _k, label in PHASE2], _index(PHASE2, eap.phase2),
                                    changed)
        self.identity_row = Adw.EntryRow(title="Uživatel (identita)", text=eap.identity)
        self.anonymous_row = Adw.EntryRow(title="Anonymní identita (nepovinné)", text=eap.anonymous_identity)
        self.password_row = Adw.PasswordEntryRow(title="Heslo (prázdné = ponechat)" if saved else "Heslo")
        login = Adw.PreferencesGroup(title="Přihlášení")
        for row in (self.method_row, self.phase2_row, self.identity_row, self.anonymous_row, self.password_row):
            login.add(row)

        self.ca_row = combo_row("CA certifikát", [label for _k, label in CA_MODES], _index(CA_MODES, eap.ca_mode),
                                changed)
        self.ca_file_row = FileRow("Soubor s CA certifikátem", eap.ca_cert, changed)
        self.domain_row = Adw.EntryRow(title="Doména serveru", text=eap.domain)
        self.warning = Gtk.Label(label=WARNING, wrap=True, xalign=0, css_classes=["warning"], margin_top=8)
        server = Adw.PreferencesGroup(title="Ověření serveru")
        for row in (self.ca_row, self.ca_file_row, self.domain_row):
            server.add(row)
        server.add(self.warning)

        self.client_cert_row = FileRow("Klientský certifikát", eap.client_cert, changed)
        self.private_key_row = FileRow("Soukromý klíč", eap.private_key, changed)
        self.key_password_row = Adw.PasswordEntryRow(
            title="Heslo ke klíči (prázdné = ponechat)" if saved else "Heslo ke klíči")
        self.tls_group = Adw.PreferencesGroup(title="Jen pro metodu TLS")
        for row in (self.client_cert_row, self.private_key_row, self.key_password_row):
            self.tls_group.add(row)

        for row in (self.identity_row, self.anonymous_row, self.password_row, self.domain_row,
                    self.key_password_row):
            row.connect("changed", lambda *_: changed())

        self.groups = [login, server, self.tls_group]
        self._update_visibility()

    def eap(self) -> Eap:
        method = METHODS[self.method_row.get_selected()][0]
        ca_mode = CA_MODES[self.ca_row.get_selected()][0]
        tls = method == "tls"
        return Eap(method=method, phase2=PHASE2[self.phase2_row.get_selected()][0],
                   identity=self.identity_row.get_text().strip(),
                   anonymous_identity=self.anonymous_row.get_text().strip(), ca_mode=ca_mode,
                   ca_cert=self.ca_file_row.path if ca_mode == "file" else "",
                   domain=self.domain_row.get_text().strip(),
                   client_cert=self.client_cert_row.path if tls else "",
                   private_key=self.private_key_row.path if tls else "")

    def secrets(self) -> dict[str, str]:
        tls = self.eap().method == "tls"
        secrets = {}
        if not tls and (password := self.password_row.get_text()):
            secrets["password"] = password
        if tls and (key_password := self.key_password_row.get_text()):
            secrets["key_password"] = key_password
        return secrets

    def validation_error(self) -> str | None:
        eap = self.eap()
        if eap.method == "tls" and not (eap.client_cert and eap.private_key):
            return "Metoda TLS potřebuje klientský certifikát a soukromý klíč."
        if not eap.identity:
            return "Vyplň uživatele."
        if eap.method != "tls" and not self._saved and not self.password_row.get_text():
            return "Vyplň heslo."
        if eap.ca_mode == "file" and not eap.ca_cert:
            return "Vyber soubor s CA certifikátem."
        return next((e for e in map(check_secret, self.secrets().values()) if e), None)

    def _changed(self) -> None:
        self._update_visibility()
        if self._on_change:
            self._on_change()

    def _update_visibility(self) -> None:
        eap = self.eap()
        tls = eap.method == "tls"
        self.phase2_row.set_visible(not tls)
        self.password_row.set_visible(not tls)
        self.tls_group.set_visible(tls)
        self.ca_file_row.set_visible(eap.ca_mode == "file")
        self.warning.set_visible(eap.ca_mode == "none" or not eap.domain)


class EapDialog(FormDialog):
    """Connect to a new 802.1X network: ``on_connect(eap, secrets)``."""

    def __init__(self, ssid: str, device: str, on_connect):
        super().__init__(title=f"{ssid} · 802.1X", primary_label="Připojit")
        self.ssid, self.device = ssid, device
        self._on_connect = on_connect
        self.connect_button = self.primary_button
        self.form = EapForm(None, on_change=self._validate)
        for group in self.form.groups:
            self.page.add(group)
        self._validate()

    def on_primary(self) -> None:
        self._on_connect(self.form.eap(), self.form.secrets())

    def _validate(self) -> None:
        error = self.form.validation_error()
        self.connect_button.set_sensitive(error is None)
        self.connect_button.set_tooltip_text(error)
