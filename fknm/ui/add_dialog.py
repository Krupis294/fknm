"""Quick "+ Přidat" from the Stav tab: a route or a DNS server for one interface's profile."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from fknm.model import Route, check_ipv4, check_route  # noqa: E402
from fknm.ui.form import FormDialog, combo_row, entry_row  # noqa: E402


class AddDialog(FormDialog):
    """``devices`` are (device, profile uuid) pairs; ``on_add(uuid, Route | server)``."""

    def __init__(self, kind: str, devices: list[tuple[str, str]], preselected: str | None, on_add):
        super().__init__(title="Přidat routu" if kind == "route" else "Přidat DNS", primary_label="Přidat",
                         content_width=480)
        self._kind = kind
        self._devices = devices
        self._on_add = on_add
        self.add_button = self.primary_button
        names = [dev for dev, _uuid in devices]
        self.device_row = combo_row("Rozhraní", names, names.index(preselected) if preselected in names else 0)

        group = Adw.PreferencesGroup()
        group.add(self.device_row)
        activate = lambda: self.add_button.emit("clicked")  # noqa: E731
        if kind == "route":
            self.dest_row = entry_row("Cíl", on_change=self._validate, on_activate=activate)
            self.gateway_row = entry_row("Brána (nepovinné)", on_change=self._validate, on_activate=activate)
            self.metric_row = entry_row("Metrika (nepovinné)", on_change=self._validate, on_activate=activate)
            rows = (self.dest_row, self.gateway_row, self.metric_row)
        else:
            self.server_row = entry_row("Server", on_change=self._validate, on_activate=activate)
            rows = (self.server_row,)
        for row in rows:
            group.add(row)
        self.page.add(group)
        self._validate()

    def value(self) -> Route | str:
        if self._kind == "dns":
            return self.server_row.get_text().strip()
        metric = self.metric_row.get_text().strip()
        return Route(self.dest_row.get_text().strip(), self.gateway_row.get_text().strip(),
                     int(metric) if metric else None)

    def validation_error(self) -> str | None:
        if self._kind == "dns":
            return check_ipv4(self.server_row.get_text().strip())
        return check_route(self.dest_row.get_text().strip(), self.gateway_row.get_text().strip(),
                           self.metric_row.get_text().strip())

    def on_primary(self) -> None:
        uuid = self._devices[self.device_row.get_selected()][1]
        self._on_add(uuid, self.value())
        if self.get_root() is not None:
            self.close()

    def _validate(self) -> None:
        error = self.validation_error()
        self.add_button.set_sensitive(error is None and bool(self._devices))
        self.add_button.set_tooltip_text(error)
