"""Searchable list behind a ">" prompt, as in SSH Wallet; base of the Wi-Fi and Profily tabs."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gdk, Gtk  # noqa: E402


def badge(text: str, ok: bool = False, tooltip: str | None = None) -> Gtk.Label:
    return Gtk.Label(label=text, valign=Gtk.Align.CENTER, tooltip_text=tooltip,
                     css_classes=["badge", "ok"] if ok else ["badge"])


def row_button(label: str, callback, tooltip: str | None = None, connect: bool = False) -> Gtk.Button:
    button = Gtk.Button(label=label, valign=Gtk.Align.CENTER, tooltip_text=tooltip,
                        css_classes=["flat", "row-action", "connect"] if connect else ["flat", "row-action"])
    button.connect("clicked", lambda *_: callback())
    return button


class ListPage(Gtk.Box):
    """Rows carry their item in ``row.item``; ``matches(item, query)`` filters them.

    The stack shows "list", "empty" (no items), "no-results" (nothing matches)
    or a page set with ``force_page`` (e.g. Wi-Fi switched off).
    """

    def __init__(self, placeholder: str, matches, on_activate, pages: dict[str, Gtk.Widget], on_delete=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._matches = matches
        self._on_activate = on_activate
        self._on_delete = on_delete
        self._rows: list[Gtk.ListBoxRow] = []
        self._forced: str | None = None

        self.search_entry = Gtk.SearchEntry(placeholder_text=placeholder, hexpand=True)
        self.search_entry.connect("changed", lambda *_: self._update_view())
        self.search_entry.connect("activate", lambda *_: self.activate_selected())
        self.search_entry.connect("stop-search", lambda entry: entry.set_text(""))
        search_keys = Gtk.EventControllerKey()
        search_keys.connect("key-pressed", self._on_search_key)
        self.search_entry.add_controller(search_keys)
        self.search_entry.set_key_capture_widget(self)
        # The search glyph is replaced by the ">" prompt (hidden here; 0px in CSS logs criticals).
        self.search_entry.get_first_child().set_visible(False)
        prompt_bar = Gtk.Box(css_classes=["prompt-bar"])
        prompt_bar.append(Gtk.Label(label=">", css_classes=["prompt"]))
        prompt_bar.append(self.search_entry)

        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, css_classes=["item-list"],
                                   valign=Gtk.Align.START)
        self.listbox.set_filter_func(lambda row: self._matches(row.item, self.search_entry.get_text()))
        self.listbox.connect("row-activated", lambda _, row: self._on_activate(row.item))
        list_keys = Gtk.EventControllerKey()
        list_keys.connect("key-pressed", self._on_list_key)
        self.listbox.add_controller(list_keys)

        self.stack = Gtk.Stack(vexpand=True)
        self.stack.add_named(Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                                child=self.listbox), "list")
        for name, widget in pages.items():
            self.stack.add_named(widget, name)

        self.append(prompt_bar)
        self.append(self.stack)

    # -- items ----------------------------------------------------------------

    def set_rows(self, rows: list[Gtk.ListBoxRow], select=None) -> None:
        """Replace the rows; keep the selection on the row whose item satisfies ``select``."""
        selected = self.selected_item()
        for row in self._rows:
            self.listbox.remove(row)
        self._rows = rows
        for row in rows:
            self.listbox.append(row)
        self._forced = None
        self._update_view(select or (lambda item: item == selected))

    def force_page(self, name: str | None) -> None:
        self._forced = name
        self._update_view()

    def rows(self) -> list[Gtk.ListBoxRow]:
        query = self.search_entry.get_text()
        return [row for row in self._rows if self._matches(row.item, query)]

    def visible_items(self) -> list:
        return [row.item for row in self.rows()]

    def selected_item(self):
        row = self.listbox.get_selected_row()
        return row.item if row else None

    def activate_selected(self) -> None:
        """Act on the selected row, or the first match when the selection is filtered out."""
        rows = self.rows()
        row = self.listbox.get_selected_row()
        if row not in rows:
            row = rows[0] if rows else None
        if row:
            self._on_activate(row.item)

    def select_next(self, step: int) -> None:
        rows = self.rows()
        if not rows:
            return
        current = self.listbox.get_selected_row()
        index = rows.index(current) + step if current in rows else 0
        row = rows[max(0, min(index, len(rows) - 1))]
        self.listbox.select_row(row)
        if self.listbox.get_focus_child() is not None:
            row.grab_focus()

    # -- internals --------------------------------------------------------------

    def _update_view(self, select=None) -> None:
        self.listbox.invalidate_filter()
        rows = self.rows()
        if self._forced:
            self.stack.set_visible_child_name(self._forced)
        elif not self._rows:
            self.stack.set_visible_child_name("empty")
        elif not rows:
            self.stack.set_visible_child_name("no-results")
        else:
            self.stack.set_visible_child_name("list")

        wanted = next((r for r in rows if select and select(r.item)), None)
        if wanted is None and self.listbox.get_selected_row() not in rows:
            wanted = rows[0] if rows else None
        if wanted is not None:
            self.listbox.select_row(wanted)
        elif not rows:
            self.listbox.unselect_all()

    def _on_search_key(self, _controller, keyval, _keycode, _state) -> bool:
        if keyval in (Gdk.KEY_Down, Gdk.KEY_Up):
            self.select_next(1 if keyval == Gdk.KEY_Down else -1)
            return True
        return False

    def _on_list_key(self, _controller, keyval, _keycode, _state) -> bool:
        item = self.selected_item()
        if keyval == Gdk.KEY_Delete and item is not None and self._on_delete:
            self._on_delete(item)
            return True
        return False
