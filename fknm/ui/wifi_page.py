"""Wi-Fi tab: networks in range, connect, disconnect, edit."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from fknm.model import SECURITY_LABELS, WifiNetwork, signal_bars  # noqa: E402
from fknm.status import ipv4_address  # noqa: E402
from fknm.ui.list_page import ListPage, badge, row_button  # noqa: E402
from fknm.ui.password_dialog import PasswordDialog  # noqa: E402
from fknm.wifi import connect, disconnect, enable_radio, radio_state, scan  # noqa: E402

BARS = "▂▄▆█"


def signal_widget(signal: int, connected: bool) -> Gtk.Box:
    lit = signal_bars(signal)
    box = Gtk.Box(valign=Gtk.Align.CENTER, tooltip_text=f"Signál {signal} %")
    box.append(Gtk.Label(label=BARS[:lit], css_classes=["signal", "ok"] if connected else ["signal"]))
    box.append(Gtk.Label(label=BARS[lit:], css_classes=["signal", "dim"]))
    return box


class NetworkRow(Adw.ActionRow):
    def __init__(self, net: WifiNetwork, address: str | None, page: "WifiPage"):
        label = SECURITY_LABELS[net.security]
        subtitle = f"{address} · {label}" if net.in_use and address else label
        super().__init__(title=net.ssid, subtitle=subtitle, use_markup=False, activatable=True)
        self.item = net
        self.set_title_lines(1)
        if net.in_use:
            self.add_suffix(badge("Připojeno", ok=True))
        elif net.profile_uuid:
            self.add_suffix(badge("Uloženo", tooltip="Uložený profil"))
        self.add_suffix(signal_widget(net.signal, net.in_use))
        if net.profile_uuid:
            self.add_suffix(row_button("Upravit", lambda: page.edit(net), "Ctrl+E"))
        if net.in_use:
            self.add_suffix(row_button("Odpojit", lambda: page.disconnect(net)))
        else:
            self.add_suffix(row_button("Připojit", lambda: page.connect_network(net), "Enter", connect=True))


class WifiPage(ListPage):
    def __init__(self, window):
        self.window = window
        self.enable_button = Gtk.Button(label="Zapnout Wi-Fi", halign=Gtk.Align.CENTER,
                                        css_classes=["suggested-action"])
        self.enable_button.connect("clicked", lambda *_: self._enable())
        pages = {
            "off": Adw.StatusPage(title="Wi-Fi je vypnutá", child=self.enable_button),
            "missing": Adw.StatusPage(title="Žádná Wi-Fi karta"),
            "empty": Adw.StatusPage(title="Žádné sítě v dosahu", description="Ctrl+R naskenuje znovu."),
            "no-results": Adw.StatusPage(title="Nic nenalezeno", description="Esc vymaže hledání."),
        }
        super().__init__("Hledat síť", lambda net, q: q.lower() in net.ssid.lower(), self.connect_network, pages)

    # -- page interface ---------------------------------------------------------

    def refresh(self, rescan: bool = False) -> None:
        runner = self.window.runner

        def load():
            state = radio_state(runner)
            if state != "enabled":
                return state, [], ""
            nets = scan(runner, rescan)
            addr = runner(["ip", "-j", "addr"], None)
            return state, nets, addr.stdout if addr.returncode == 0 else ""

        def loaded(result, error):
            if error:
                self.window.toast(f"Sítě nejde načíst: {error}", timeout=6)
                return
            state, nets, addr_json = result
            if state != "enabled":
                self.force_page("off" if state == "disabled" else "missing")
                return
            rows = [NetworkRow(n, ipv4_address(addr_json, n.device), self) for n in nets]
            selected = self.selected_item()
            self.set_rows(rows, select=lambda n: selected is not None and n.ssid == selected.ssid)

        self.window.background(load, loaded)

    def set_live(self, visible: bool) -> None:
        if visible:
            self.refresh()

    def refresh_shortcut(self) -> None:
        self.refresh(rescan=True)

    def hints(self) -> list[tuple[str, str]]:
        return [("Enter", "Připojit"), ("Ctrl+E", "Upravit"), ("Ctrl+R", "Skenovat"), ("Ctrl+1/2/3", "Záložky")]

    def edit_selected(self) -> None:
        if net := self.selected_item():
            self.edit(net)

    def visible_networks(self) -> list[WifiNetwork]:
        return self.visible_items()

    def connect_selected(self) -> None:
        self.activate_selected()

    # -- actions ----------------------------------------------------------------

    def connect_network(self, net: WifiNetwork) -> None:
        if net.in_use:
            return
        if net.profile_uuid or net.security == "open":
            self._connect(net, None)
        elif net.security == "eap":
            self.window.open_eap(net.ssid)
        elif net.security == "wep":
            self.window.toast("WEP sítě nejsou podporované.", timeout=6)
        else:
            dialog = PasswordDialog(net.ssid, SECURITY_LABELS[net.security],
                                    on_connect=lambda password: self._connect(net, password, dialog))
            dialog.present(self.window)

    def edit(self, net: WifiNetwork) -> None:
        if net.profile_uuid:
            self.window.open_profile(net.profile_uuid, net.device)

    def disconnect(self, net: WifiNetwork) -> None:
        self.window.run_action(lambda: disconnect(self.window.runner, net), f"Odpojeno od {net.ssid}.",
                               error_prefix=f"Nejde odpojit {net.ssid}: ")

    def _connect(self, net: WifiNetwork, password: str | None, dialog=None) -> None:
        self.window.toast(f"Připojuji k {net.ssid}…")
        self.window.run_action(lambda: connect(self.window.runner, net, password), f"Připojeno k {net.ssid}.",
                               error_prefix=f"Nepřipojeno k {net.ssid}: ", dialog=dialog)

    def _enable(self) -> None:
        self.window.run_action(lambda: enable_radio(self.window.runner), "Wi-Fi zapnuta.")
