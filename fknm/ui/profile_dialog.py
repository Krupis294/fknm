"""Editing one profile: name, password, 802.1X, IPv4 method, addresses, DNS and routes."""

from dataclasses import replace

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from fknm.model import (  # noqa: E402
    Ipv4, ProfileSettings, Route, check_address, check_ipv4, check_psk, check_route,
)
from fknm.ui.eap_form import EapForm  # noqa: E402
from fknm.ui.form import FormDialog, add_button, combo_row, entry_row, remove_button  # noqa: E402

METHODS = [("auto", "Automaticky (DHCP)"), ("manual", "Ručně"), ("disabled", "Vypnuto")]


class ValueRow(Adw.EntryRow):
    """One address or DNS server with a remove button."""

    def __init__(self, title: str, text: str, on_change, on_remove):
        super().__init__(title=title, text=text)
        self.remove_button = remove_button("Odebrat", lambda: on_remove(self))
        self.add_suffix(self.remove_button)
        self.connect("changed", lambda *_: on_change())

    def value(self) -> str:
        return self.get_text().strip()


class RouteRow(Adw.PreferencesRow):
    """One route: destination → gateway, metric."""

    def __init__(self, route: Route | None, on_change, on_remove):
        super().__init__(activatable=False, css_classes=["route-row"])
        route = route or Route("")
        self._extra = route.extra
        self.dest_entry = Gtk.Entry(hexpand=True, placeholder_text="cíl/prefix", text=route.dest,
                                    valign=Gtk.Align.CENTER)
        self.gateway_entry = Gtk.Entry(hexpand=True, placeholder_text="brána", text=route.gateway,
                                       valign=Gtk.Align.CENTER)
        self.metric_entry = Gtk.Entry(width_chars=6, max_width_chars=6, placeholder_text="metrika",
                                      text="" if route.metric is None else str(route.metric),
                                      input_purpose=Gtk.InputPurpose.DIGITS, valign=Gtk.Align.CENTER)
        self.remove_button = remove_button("Odebrat routu", lambda: on_remove(self))
        box = Gtk.Box(spacing=8)
        for widget in (self.dest_entry, Gtk.Label(label="→", css_classes=["dim-label"]), self.gateway_entry,
                       Gtk.Label(label="metrika", css_classes=["dim-label"]), self.metric_entry,
                       self.remove_button):
            box.append(widget)
        self.set_child(box)
        for entry in (self.dest_entry, self.gateway_entry, self.metric_entry):
            entry.connect("changed", lambda *_: on_change())

    def error(self) -> str | None:
        return check_route(self.dest_entry.get_text().strip(), self.gateway_entry.get_text().strip(),
                           self.metric_entry.get_text().strip())

    def route(self) -> Route:
        metric = self.metric_entry.get_text().strip()
        return Route(self.dest_entry.get_text().strip(), self.gateway_entry.get_text().strip(),
                     int(metric) if metric.isdigit() else None, self._extra)


class ProfileDialog(FormDialog):
    """``on_save(settings, secrets)``; secrets hold only what was typed (empty = keep)."""

    def __init__(self, settings: ProfileSettings, on_save, on_delete):
        super().__init__(title=settings.name, primary_label="Uložit")
        self._settings = settings
        self._on_save = on_save
        self._on_delete = on_delete
        self.save_button = self.primary_button
        self.address_rows: list[ValueRow] = []
        self.dns_rows: list[ValueRow] = []
        self.route_rows: list[RouteRow] = []
        validate = self._validate
        ipv4 = settings.ipv4

        self.name_row = entry_row("Název", settings.name, validate)
        self.password_row = Adw.PasswordEntryRow(title="Heslo (prázdné = ponechat)",
                                                 visible=settings.security in ("psk", "sae"))
        self.password_row.connect("changed", lambda *_: validate())
        self.autoconnect_row = Adw.SwitchRow(title="Připojit automaticky", active=settings.autoconnect)
        general = Adw.PreferencesGroup()
        for row in (self.name_row, self.password_row, self.autoconnect_row):
            general.add(row)
        self.page.add(general)

        self.eap_form = EapForm(settings.eap, saved=True, on_change=validate) if settings.security == "eap" else None
        for group in self.eap_form.groups if self.eap_form else []:
            self.page.add(group)

        self.method_row = combo_row("Metoda", [label for _k, label in METHODS],
                                    next((i for i, (k, _l) in enumerate(METHODS) if k == ipv4.method), 0),
                                    self._on_method_changed)
        self.gateway_row = entry_row("Brána", ipv4.gateway, validate)
        ipv4_group = Adw.PreferencesGroup(title="IPv4")
        ipv4_group.add(self.method_row)
        ipv4_group.add(self.gateway_row)
        self.page.add(ipv4_group)

        self.addresses_group = Adw.PreferencesGroup(title="Adresy", header_suffix=add_button(self.add_address_row))
        self.page.add(self.addresses_group)

        self.ignore_dns_row = Adw.SwitchRow(title="Ignorovat DNS z DHCP", active=ipv4.ignore_auto_dns)
        self.dns_group = Adw.PreferencesGroup(title="DNS", header_suffix=add_button(self.add_dns_row))
        self.dns_group.add(self.ignore_dns_row)
        self.page.add(self.dns_group)

        self.ignore_routes_row = Adw.SwitchRow(title="Ignorovat routy z DHCP", active=ipv4.ignore_auto_routes)
        self.routes_group = Adw.PreferencesGroup(title="Routy", header_suffix=add_button(self.add_route_row))
        self.routes_group.add(self.ignore_routes_row)
        self.page.add(self.routes_group)

        delete = Gtk.Button(label="Smazat profil", halign=Gtk.Align.CENTER, css_classes=["destructive-action"])
        delete.connect("clicked", lambda *_: self._confirm_delete())
        delete_group = Adw.PreferencesGroup()
        delete_group.add(delete)
        self.page.add(delete_group)

        for address in ipv4.addresses:
            self.add_address_row(address)
        for server in ipv4.dns:
            self.add_dns_row(server)
        for route in ipv4.routes:
            self.add_route_row(route)
        self._on_method_changed()

    # -- rows ---------------------------------------------------------------

    def add_address_row(self, text: str = "") -> None:
        row = ValueRow("Adresa (např. 192.168.1.10/24)", text, self._validate,
                       lambda r: self._remove(r, self.address_rows, self.addresses_group))
        self.address_rows.append(row)
        self.addresses_group.add(row)
        self._validate()

    def add_dns_row(self, text: str = "") -> None:
        row = ValueRow("Server", text, self._validate, lambda r: self._remove(r, self.dns_rows, self.dns_group))
        self.dns_rows.append(row)
        self._insert_before_switch(self.dns_group, row, self.ignore_dns_row)

    def add_route_row(self, route: Route | None = None) -> None:
        row = RouteRow(route, self._validate, lambda r: self._remove(r, self.route_rows, self.routes_group))
        self.route_rows.append(row)
        self._insert_before_switch(self.routes_group, row, self.ignore_routes_row)

    def _insert_before_switch(self, group: Adw.PreferencesGroup, row, switch: Adw.SwitchRow) -> None:
        # PreferencesGroup only appends; keep the "Ignorovat z DHCP" switch last.
        group.remove(switch)
        group.add(row)
        group.add(switch)
        self._validate()

    def _remove(self, row, rows: list, group: Adw.PreferencesGroup) -> None:
        rows.remove(row)
        group.remove(row)
        self._validate()

    # -- values -------------------------------------------------------------

    def method(self) -> str:
        return METHODS[self.method_row.get_selected()][0]

    def collect(self) -> ProfileSettings:
        ipv4 = Ipv4(method=self.method(), addresses=[r.value() for r in self.address_rows],
                    gateway=self.gateway_row.get_text().strip(), dns=[r.value() for r in self.dns_rows],
                    ignore_auto_dns=self.ignore_dns_row.get_active(),
                    routes=[r.route() for r in self.route_rows],
                    ignore_auto_routes=self.ignore_routes_row.get_active())
        return replace(self._settings, name=self.name_row.get_text().strip(),
                       autoconnect=self.autoconnect_row.get_active(),
                       eap=self.eap_form.eap() if self.eap_form else self._settings.eap, ipv4=ipv4)

    def secrets(self) -> dict[str, str]:
        secrets = self.eap_form.secrets() if self.eap_form else {}
        if self.password_row.get_visible() and (password := self.password_row.get_text()):
            secrets["psk"] = password
        return secrets

    def validation_error(self) -> str | None:
        method = self.method()
        errors = [] if self.name_row.get_text().strip() else ["Vyplň název."]

        def mark(row, error):
            (row.add_css_class if error else row.remove_css_class)("error")
            errors.append(error)

        for row in self.address_rows:
            mark(row, check_address(row.value()) if method == "manual" else None)
        gateway = self.gateway_row.get_text().strip()
        mark(self.gateway_row, check_ipv4(gateway) if method == "manual" and gateway else None)
        for row in self.dns_rows:
            mark(row, check_ipv4(row.value()) if method != "disabled" else None)
        for row in self.route_rows:
            mark(row, row.error() if method != "disabled" else None)
        if method == "manual" and not self.address_rows:
            errors.append("Při ruční metodě je potřeba aspoň jedna adresa.")
        if self.password_row.get_visible() and (password := self.password_row.get_text()):
            errors.append(check_psk(password))
        if self.eap_form:
            errors.append(self.eap_form.validation_error())
        return next((e for e in errors if e), None)

    # -- behaviour ----------------------------------------------------------

    def on_primary(self) -> None:
        self._on_save(self.collect(), self.secrets())

    def _on_method_changed(self) -> None:
        method = self.method()
        self.gateway_row.set_visible(method == "manual")
        self.addresses_group.set_visible(method == "manual")
        self.dns_group.set_visible(method != "disabled")
        self.routes_group.set_visible(method != "disabled")
        self._validate()

    def _validate(self) -> None:
        # Rows are added while the dialog is still being built.
        if not hasattr(self, "routes_group"):
            return
        error = self.validation_error()
        self.save_button.set_sensitive(error is None)
        self.save_button.set_tooltip_text(error)
        self.show_error(error)

    def _confirm_delete(self) -> None:
        name = self._settings.name
        dialog = Adw.AlertDialog(heading=f"Smazat {name}?", body="Profil bude odstraněn z NetworkManageru.")
        dialog.add_response("cancel", "Zrušit")
        dialog.add_response("delete", "Smazat")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, response: response == "delete" and self._delete())
        dialog.present(self)

    def _delete(self) -> None:
        self.close()
        self._on_delete()
