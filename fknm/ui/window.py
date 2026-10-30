"""Main window: Wi-Fi, Profily and Stav tabs with the Tailscale state in the header."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from fknm.nmcli import NmcliError, Runner  # noqa: E402
from fknm.profiles import delete, list_profiles, read_settings, save  # noqa: E402
from fknm.status import tailscale_running  # noqa: E402
from fknm.ui.background import Background, run_in_background  # noqa: E402
from fknm.ui.eap_form import EapDialog  # noqa: E402
from fknm.ui.profile_dialog import ProfileDialog  # noqa: E402
from fknm.ui.profiles_page import ProfilesPage  # noqa: E402
from fknm.ui.wifi_page import WifiPage  # noqa: E402
from fknm.wifi import connect_eap, scan  # noqa: E402

TABS = [("wifi", "Wi-Fi"), ("profiles", "Profily"), ("status", "Stav")]
TAILSCALE_INTERVAL = 3


def hints_bar(pairs: list[tuple[str, str]]) -> Gtk.Box:
    """Bottom status line with the keyboard shortcuts of the visible tab."""
    box = Gtk.Box(spacing=20, css_classes=["hints"])
    for key, action in pairs:
        pair = Gtk.Box(spacing=6)
        pair.append(Gtk.Label(label=key, css_classes=["key"]))
        pair.append(Gtk.Label(label=action))
        box.append(pair)
    return box


def read_addr(runner: Runner) -> str:
    result = runner(["ip", "-j", "addr"], None)
    if result.returncode != 0:
        raise NmcliError(result.stderr.strip() or "ip addr selhal")
    return result.stdout


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, runner: Runner, background: Background = run_in_background, pages: bool = True,
                 **kwargs):
        super().__init__(title="fknm", default_width=820, default_height=700, **kwargs)
        self.runner = runner
        self.background = background
        self.last_toast: str | None = None

        self.view_stack = Adw.ViewStack(vexpand=True)
        self.pages = {}
        for name, title in TABS:
            page = self._build_page(name) if pages else Gtk.Box()
            self.pages[name] = page
            self.view_stack.add_titled(page, name, title)
        self.view_stack.connect("notify::visible-child-name", lambda *_: self._on_tab_changed())

        self.tailscale_label = Gtk.Label(label="● tailscale", css_classes=["tailscale", "off"],
                                         tooltip_text="Tailscale neběží")
        header = Adw.HeaderBar(title_widget=Adw.ViewSwitcher(stack=self.view_stack,
                                                             policy=Adw.ViewSwitcherPolicy.WIDE))
        header.pack_end(self.tailscale_label)

        self.toast_overlay = Adw.ToastOverlay(child=self.view_stack)
        self.toolbar = Adw.ToolbarView(content=self.toast_overlay)
        self.toolbar.add_top_bar(header)
        self._hints = None
        self.set_content(self.toolbar)

        for index, (name, _title) in enumerate(TABS, start=1):
            self._add_action(f"tab-{index}", lambda name=name: self.view_stack.set_visible_child_name(name))
        self._add_action("refresh", lambda: self._call_page("refresh_shortcut"))
        self._add_action("edit", lambda: self._call_page("edit_selected"))

        self._tailscale_timer = GLib.timeout_add_seconds(TAILSCALE_INTERVAL, self._tailscale_tick)
        self.connect("destroy", lambda *_: self._stop_timers())
        self.refresh_tailscale()
        self._on_tab_changed()

    # -- public API -------------------------------------------------------

    def toast(self, message: str, timeout: int = 4) -> None:
        self.last_toast = message
        self.toast_overlay.add_toast(Adw.Toast(title=GLib.markup_escape_text(message), timeout=timeout))

    def refresh_tailscale(self) -> None:
        def done(addr, error):
            self._show_tailscale(error is None and tailscale_running(addr))
        self.background(lambda: read_addr(self.runner), done)

    def refresh_all(self) -> None:
        for page in self.pages.values():
            if hasattr(page, "refresh"):
                page.refresh()

    def open_profile(self, uuid: str, device: str) -> None:
        """Edit a profile; ``device`` is where it runs or last ran, for the ethernet MAC binding."""
        def load():
            active = any(p.uuid == uuid and p.active for p in list_profiles(self.runner))
            return read_settings(self.runner, uuid), active

        def loaded(result, error):
            if error:
                self.toast(f"Profil nejde načíst: {error}", timeout=6)
                return
            settings, active = result
            dialog = ProfileDialog(
                settings, on_save=lambda s, secrets: self._save(dialog, s, secrets, device, active),
                on_delete=lambda: self._delete(settings.uuid, settings.name))
            dialog.present(self)

        self.background(load, loaded)

    def open_eap(self, ssid: str) -> None:
        """Dialog for a new 802.1X network, also reached through ``fknm --eap SSID`` from rofi."""
        def scanned(nets, error):
            net = next((n for n in nets or [] if n.ssid == ssid), None)
            if error or net is None:
                self.toast(f"Síť {ssid} není v dosahu.", timeout=6)
                return
            dialog = EapDialog(ssid, net.device,
                               on_connect=lambda eap, secrets: self._connect_eap(dialog, eap, secrets))
            dialog.present(self)

        self.background(lambda: scan(self.runner), scanned)

    def run_action(self, work, done_message: str, error_prefix: str = "", dialog=None) -> None:
        """Run a change in the background; report it as a toast (or in ``dialog``) and refresh."""
        if dialog:
            dialog.set_busy(True)

        def done(_result, error):
            if error:
                message = f"{error_prefix}{error}"
                if dialog:
                    dialog.set_busy(False)
                    dialog.show_error(message)
                else:
                    self.toast(message, timeout=8)
                return
            if dialog:
                dialog.close()
            self.toast(done_message)
            self.refresh_all()

        self.background(work, done)

    def _save(self, dialog, settings, secrets, device: str, active: bool) -> None:
        self.run_action(lambda: save(self.runner, settings, secrets, device=device, reactivate=active),
                        "Uloženo.", dialog=dialog)

    def _delete(self, uuid: str, name: str) -> None:
        self.run_action(lambda: delete(self.runner, uuid), f"{name} smazán.")

    def _connect_eap(self, dialog: EapDialog, eap, secrets) -> None:
        self.toast(f"Připojuji k {dialog.ssid}…")
        self.run_action(lambda: connect_eap(self.runner, dialog.ssid, dialog.device, eap, secrets),
                        f"Připojeno k {dialog.ssid}.", dialog=dialog)

    # -- internals --------------------------------------------------------

    def _build_page(self, name: str) -> Gtk.Widget:
        builders = {"wifi": WifiPage, "profiles": ProfilesPage}
        return builders[name](self) if name in builders else Gtk.Box()

    def _add_action(self, name: str, callback) -> None:
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", lambda *_: callback())
        self.add_action(action)

    def _current_page(self):
        return self.pages.get(self.view_stack.get_visible_child_name())

    def _call_page(self, method: str) -> None:
        # The window shortcuts stay active under an open dialog; leave the pages alone then.
        page = self._current_page()
        if self.get_visible_dialog() is None and hasattr(page, method):
            getattr(page, method)()

    def _on_tab_changed(self) -> None:
        current = self._current_page()
        for page in self.pages.values():
            if hasattr(page, "set_live"):
                page.set_live(page is current)
        if self._hints is not None:
            self.toolbar.remove(self._hints)
        self._hints = hints_bar(current.hints() if hasattr(current, "hints") else [])
        self.toolbar.add_bottom_bar(self._hints)

    def _show_tailscale(self, running: bool) -> None:
        self.tailscale_label.remove_css_class("off" if running else "on")
        self.tailscale_label.add_css_class("on" if running else "off")
        self.tailscale_label.set_tooltip_text("Tailscale běží" if running else "Tailscale neběží")

    def _tailscale_tick(self) -> bool:
        self.refresh_tailscale()
        return GLib.SOURCE_CONTINUE

    def _stop_timers(self) -> None:
        if self._tailscale_timer:
            GLib.source_remove(self._tailscale_timer)
            self._tailscale_timer = 0
        for page in self.pages.values():
            if hasattr(page, "set_live"):
                page.set_live(False)
