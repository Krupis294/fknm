"""Shared frame of the dialogs: Zrušit and one main button in the header, an error line on top."""

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402


class FormDialog(Adw.Dialog):
    def __init__(self, title: str, primary_label: str, content_width: int = 600):
        super().__init__(title=title, content_width=content_width)
        cancel = Gtk.Button(label="Zrušit")
        cancel.connect("clicked", lambda *_: self.close())
        self.primary_button = Gtk.Button(label=primary_label, css_classes=["suggested-action"])
        # emit("clicked") reaches the handler even when the button is insensitive.
        self.primary_button.connect("clicked", lambda *_: self.primary_button.get_sensitive() and self.on_primary())
        header = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
        header.pack_start(cancel)
        header.pack_end(self.primary_button)

        self.error_label = Gtk.Label(css_classes=["form-error"], wrap=True, xalign=0, visible=False)
        error_group = Adw.PreferencesGroup()
        error_group.add(self.error_label)
        self.page = Adw.PreferencesPage()
        self.page.add(error_group)

        toolbar = Adw.ToolbarView(content=self.page)
        toolbar.add_top_bar(header)
        self.set_child(toolbar)

    def on_primary(self) -> None:
        raise NotImplementedError

    def show_error(self, message: str | None) -> None:
        self.error_label.set_text(message or "")
        self.error_label.set_visible(bool(message))

    def set_busy(self, busy: bool) -> None:
        """While nmcli works the main button waits; the result re-enables it or closes the dialog."""
        self.primary_button.set_sensitive(not busy)


def entry_row(title: str, text: str = "", on_change=None, on_activate=None) -> Adw.EntryRow:
    row = Adw.EntryRow(title=title, text=text)
    if on_change:
        row.connect("changed", lambda *_: on_change())
    if on_activate:
        row.connect("entry-activated", lambda *_: on_activate())
    return row


def combo_row(title: str, labels: list[str], selected: int, on_change=None) -> Adw.ComboRow:
    row = Adw.ComboRow(title=title, model=Gtk.StringList.new(labels), selected=selected)
    if on_change:
        row.connect("notify::selected", lambda *_: on_change())
    return row


def add_button(callback) -> Gtk.Button:
    button = Gtk.Button(label="+ Přidat", valign=Gtk.Align.CENTER, css_classes=["flat"])
    button.connect("clicked", lambda *_: callback())
    return button


def remove_button(tooltip: str, callback) -> Gtk.Button:
    button = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, tooltip_text=tooltip,
                        css_classes=["flat"])
    button.connect("clicked", lambda *_: callback())
    return button


class FileRow(Adw.ActionRow):
    """A file picked with Gtk.FileDialog; the path shows as the subtitle."""

    def __init__(self, title: str, path: str = "", on_change=None):
        super().__init__(title=title)
        self.path = path
        self._on_change = on_change
        choose = Gtk.Button(icon_name="document-open-symbolic", valign=Gtk.Align.CENTER,
                            tooltip_text="Vybrat soubor", css_classes=["flat"])
        choose.connect("clicked", self._choose)
        self.add_suffix(choose)
        self._show()

    def set_path(self, path: str) -> None:
        self.path = path
        self._show()
        if self._on_change:
            self._on_change()

    def _show(self) -> None:
        self.set_subtitle(GLib.markup_escape_text(self.path) or "Nevybráno")

    def _choose(self, *_):
        dialog = Gtk.FileDialog(title=self.get_title())
        if self.path and Path(self.path).parent.is_dir():
            dialog.set_initial_folder(Gio.File.new_for_path(str(Path(self.path).parent)))
        root = self.get_root()
        dialog.open(root if isinstance(root, Gtk.Window) else None, None, self._on_chosen)

    def _on_chosen(self, dialog, result):
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return  # cancelled
        self.set_path(file.get_path())
