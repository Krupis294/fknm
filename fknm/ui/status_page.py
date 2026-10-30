"""Stav tab: addresses, routes and DNS in effect now, with quick edits saved to the profile."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from fknm.status import (  # noqa: E402
    DnsEntry, Interface, RouteEntry, Status, add_dns, add_route, read_status, remove_dns, remove_route,
)
from fknm.ui.add_dialog import AddDialog  # noqa: E402
from fknm.ui.list_page import badge, row_button  # noqa: E402


class EntryRow(Adw.ActionRow):
    """One interface, route or DNS server; ``entry`` is None for the resolv.conf line."""

    def __init__(self, title: str, entry, subtitle: str = ""):
        super().__init__(title=title, subtitle=subtitle, use_markup=False, activatable=entry is not None)
        self.entry = entry
        self.origin_label: Gtk.Label | None = None
        self.edit_button: Gtk.Button | None = None
        self.remove_button: Gtk.Button | None = None

    def add_origin(self, origin: str) -> None:
        self.origin_label = Gtk.Label(label=origin, valign=Gtk.Align.CENTER, css_classes=["origin"])
        self.add_suffix(self.origin_label)


class StatusPage(Gtk.Box):
    def __init__(self, window, interval: int = 3):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.interval = interval
        self.rows: list[EntryRow] = []
        self.section_titles: list[Gtk.Label] = []
        self._section_rows: list[Gtk.ListBoxRow] = []
        self._devices: dict[str, str] = {}  # device -> uuid of the profile running on it
        self._loading = False
        self._timer_id: int | None = None

        self.error_label = Gtk.Label(xalign=0, wrap=True, css_classes=["load-error"], visible=False)
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, css_classes=["item-list"],
                                   valign=Gtk.Align.START)
        self.listbox.connect("row-activated", lambda *_: self.edit_selected())
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.listbox.add_controller(keys)
        self.append(self.error_label)
        self.append(Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER, child=self.listbox))

    # -- page interface ---------------------------------------------------------

    def refresh(self) -> None:
        # A slow read (e.g. while a profile reconnects) must not pile up ticks.
        if self._loading:
            return
        self._loading = True

        def done(status, error):
            self._loading = False
            if error:
                self.error_label.set_text(f"Stav nejde načíst: {error}")
                self.error_label.set_visible(True)
                return
            self.error_label.set_visible(False)
            self._show(status)

        self.window.background(lambda: read_status(self.window.runner), done)

    def set_live(self, visible: bool) -> None:
        if visible and self._timer_id is None:
            self.refresh()
            self._timer_id = GLib.timeout_add_seconds(self.interval, self._tick)
        elif not visible and self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def refresh_shortcut(self) -> None:
        self.refresh()

    def hints(self) -> list[tuple[str, str]]:
        return [("Ctrl+E", "Upravit rozhraní"), ("Delete", "Odebrat"), ("Ctrl+R", "Obnovit")]

    def edit_selected(self) -> None:
        entry = self._selected_entry()
        if isinstance(entry, Interface) and entry.uuid:
            self.window.open_profile(entry.uuid, entry.name)
        elif isinstance(entry, (RouteEntry, DnsEntry)) and entry.dev in self._devices:
            self.window.open_profile(self._devices[entry.dev], entry.dev)

    def remove_selected(self) -> None:
        row = self.listbox.get_selected_row()
        if isinstance(row, EntryRow) and row.remove_button is not None:
            self.remove(row.entry)

    # -- edits ------------------------------------------------------------------

    def add(self, kind: str) -> None:
        devices = list(self._devices.items())
        if not devices:
            self.window.toast("Žádné rozhraní s profilem.")
            return
        entry = self._selected_entry()
        preselected = entry.name if isinstance(entry, Interface) else getattr(entry, "dev", None)
        dialog = AddDialog(kind, devices, preselected, on_add=lambda uuid, value: self.add_value(kind, uuid, value))
        dialog.present(self.window)

    def add_value(self, kind: str, uuid: str, value) -> None:
        device = next((dev for dev, u in self._devices.items() if u == uuid), "")
        change = add_route if kind == "route" else add_dns
        self.window.run_action(lambda: change(self.window.runner, uuid, device, value), "Uloženo.",
                               error_prefix="Nejde uložit: ")

    def remove(self, entry: RouteEntry | DnsEntry) -> None:
        uuid = self._devices.get(entry.dev)
        if uuid is None:
            return
        runner = self.window.runner
        if isinstance(entry, RouteEntry):
            work = lambda: remove_route(runner, uuid, entry.dev, entry.route)  # noqa: E731
        else:
            work = lambda: remove_dns(runner, uuid, entry.dev, entry.server)  # noqa: E731
        self.window.run_action(work, "Uloženo.", error_prefix="Nejde uložit: ")

    # -- internals --------------------------------------------------------------

    def _tick(self) -> bool:
        self.refresh()
        return GLib.SOURCE_CONTINUE

    def _selected_entry(self):
        row = self.listbox.get_selected_row()
        return row.entry if isinstance(row, EntryRow) else None

    def _section(self, title: str, add_kind: str | None = None) -> None:
        box = Gtk.Box(css_classes=["section-title"])
        label = Gtk.Label(label=title, xalign=0, hexpand=True)
        box.append(label)
        if add_kind:
            button = Gtk.Button(label="+ Přidat", css_classes=["flat"], valign=Gtk.Align.CENTER)
            button.connect("clicked", lambda *_: self.add(add_kind))
            box.append(button)
        row = Gtk.ListBoxRow(child=box, selectable=False, activatable=False)
        self.section_titles.append(label)
        self._section_rows.append(row)
        self.listbox.append(row)

    def _add_row(self, row: EntryRow) -> None:
        self.rows.append(row)
        self.listbox.append(row)

    def _remove_button(self, row: EntryRow) -> None:
        row.remove_button = row_button("✕", lambda: self.remove(row.entry), "Odebrat (Delete)")
        row.add_suffix(row.remove_button)

    def _show(self, status: Status) -> None:
        selected = self.listbox.get_selected_row()
        selected_key = (type(selected.entry), selected.get_title()) if isinstance(selected, EntryRow) else None
        for row in self.rows + self._section_rows:
            self.listbox.remove(row)
        self.rows, self.section_titles, self._section_rows = [], [], []
        self._devices = {i.name: i.uuid for i in status.interfaces if i.uuid}

        self._section("Adresy")
        for interface in status.interfaces:
            title = f"{interface.name} · {interface.profile}" if interface.profile else interface.name
            row = EntryRow(title, interface, " · ".join(interface.addresses) or "bez adresy")
            row.add_suffix(badge(interface.state, ok=interface.state == "UP"))
            if interface.uuid:
                row.edit_button = row_button("Upravit", lambda i=interface: self.window.open_profile(i.uuid, i.name),
                                             "Ctrl+E")
                row.add_suffix(row.edit_button)
            else:
                row.add_origin("bez profilu")
            self._add_row(row)

        self._section("Routy", "route")
        for route in status.routes:
            row = EntryRow(route.text, route)
            row.add_origin(route.origin)
            if route.route is not None:
                self._remove_button(row)
            self._add_row(row)

        self._section("DNS", "dns")
        for dns in status.dns:
            row = EntryRow(f"{dns.server} · {dns.dev}", dns)
            row.add_origin(dns.origin)
            if dns.removable:
                self._remove_button(row)
            self._add_row(row)
        self._add_row(EntryRow(f"/etc/resolv.conf → {status.resolv}", None))

        for row in self.rows:
            if selected_key == (type(row.entry), row.get_title()):
                self.listbox.select_row(row)

    def _on_key(self, _controller, keyval, _keycode, _state) -> bool:
        if keyval == Gdk.KEY_Delete:
            self.remove_selected()
            return True
        return False
