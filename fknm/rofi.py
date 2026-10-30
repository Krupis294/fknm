"""Quick wifi picker in rofi: choose a network, type its password if it is new, connected.

Rows are fed to ``rofi -dmenu`` with the ``display`` row option: rofi renders
the Pango markup but filters on the plain ``search`` text (the SSID), so
typing never matches markup tags. rofi returns the row index.
"""

import argparse
import html
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from fknm.model import SECURITY_LABELS, WifiNetwork, check_psk, signal_bars
from fknm.nmcli import NmcliError, run_command
from fknm.status import ipv4_address, tailscale_running
from fknm.wifi import connect, radio_state, scan

ROOT = Path(__file__).resolve().parent.parent
THEME_PATH = ROOT / "data" / "fknm.rasi"
GUI_PATH = ROOT / "bin" / "fknm"
RESCAN_ENTRY = "↻ Skenovat znovu"
GUI_ENTRY = "Otevřít"
ACCENT = "#87d5a2"
BARS = "▂▄▆█"

_CONTROL = re.compile(r"[\n\r\0\x1f]+")


@dataclass
class Row:
    search: str
    display: str
    permanent: bool = False


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _dim(text: str) -> str:
    return f'<span alpha="60%">{_esc(text)}</span>'


def _accent(text: str) -> str:
    return f'<span foreground="{ACCENT}">{_esc(text)}</span>'


def network_rows(nets: list[WifiNetwork]) -> list[Row]:
    width = max((len(n.ssid) for n in nets), default=0)
    rows = []
    for net in nets:
        lit = signal_bars(net.signal)
        bars = (_accent(BARS[:lit]) if net.in_use else _esc(BARS[:lit])) + f'<span alpha="30%">{BARS[lit:]}</span>'
        label = SECURITY_LABELS[net.security]
        display = (f"<b>{_esc(net.ssid)}</b>" + " " * (width - len(net.ssid) + 2) + bars
                   + "  " + _dim(label.ljust(8)))
        if net.in_use:
            display += "  " + _accent("Připojeno")
        elif net.profile_uuid:
            display += "  " + _dim("Uloženo")
        rows.append(Row(net.ssid, display))
    return rows


def status_mesg(nets: list[WifiNetwork], ip_addr_json: str) -> str:
    """Message line: the current connection and whether Tailscale runs."""
    dot = _accent("●") if tailscale_running(ip_addr_json) else _dim("●")
    connected = next((n for n in nets if n.in_use), None)
    if connected is None:
        return f"Nepřipojeno · {dot} tailscale"
    parts = [connected.device, connected.ssid, ipv4_address(ip_addr_json, connected.device) or ""]
    return " · ".join(_esc(p) for p in parts if p) + f" · {dot} tailscale"


def encode(rows: list[Row]) -> str:
    """rofi dmenu input: one line per row with ``\\0option\\x1fvalue`` options."""
    lines = []
    for row in rows:
        line = f"{_clean(row.search)}\0display\x1f{_clean(row.display)}"
        if row.permanent:
            line += "\x1fpermanent\x1ftrue"
        lines.append(line + "\n")
    return "".join(lines)


def _clean(text: str) -> str:
    return _CONTROL.sub(" ", text)


def rofi_command(theme: Path | None, mesg: str | None, password: bool = False) -> list[str]:
    if password:
        argv = ["rofi", "-dmenu", "-password", "-p", "Heslo", "-l", "0"]
    else:
        argv = ["rofi", "-dmenu", "-i", "-markup-rows", "-no-custom", "-format", "i", "-p", "Wi-Fi"]
    if theme:
        argv += ["-theme", str(theme)]
        if password:
            # The bundled theme's placeholder says "Hledat síť".
            argv += ["-theme-str", 'entry { placeholder: "Heslo"; }']
    if mesg:
        argv += ["-mesg", mesg]
    return argv


def parse_selection(result: subprocess.CompletedProcess) -> int | None:
    """Index of the chosen row, or None when rofi was cancelled."""
    choice = result.stdout.strip()
    if result.returncode != 0 or not choice.isdigit():
        return None
    return int(choice)


def run(runner, rofi, theme: Path | None, open_gui, open_eap) -> int:
    """``rofi(argv, input_text)`` runs rofi and returns a CompletedProcess."""
    def error(message: str) -> int:
        rofi(["rofi", "-e", message] + (["-theme", str(theme)] if theme else []), "")
        return 1

    try:
        state = radio_state(runner)
        nets = scan(runner) if state == "enabled" else []
    except NmcliError as e:
        return error(f"Sítě nejde načíst: {e}")
    if state == "missing":
        return error("Žádná Wi-Fi karta.")
    if state == "disabled":
        return error("Wi-Fi je vypnutá. Zapni ji v fknm.")

    while True:
        addr = runner(["ip", "-j", "addr"], None)
        rows = network_rows(nets) + [Row(RESCAN_ENTRY, f"<i>{RESCAN_ENTRY}</i>", permanent=True),
                                     Row(GUI_ENTRY, f"<i>{GUI_ENTRY}</i>", permanent=True)]
        mesg = status_mesg(nets, addr.stdout if addr.returncode == 0 else "")
        index = parse_selection(rofi(rofi_command(theme, mesg), encode(rows)))
        if index is None:
            return 0
        if index == len(nets):
            try:
                nets = scan(runner, rescan=True)
            except NmcliError as e:
                return error(f"Sítě nejde načíst: {e}")
            continue
        if index > len(nets):
            open_gui()
            return 0
        net = nets[index]
        break

    if net.in_use:
        return 0
    if net.security == "wep" and not net.profile_uuid:
        return error("WEP sítě nejsou podporované.")
    if net.security == "eap" and not net.profile_uuid:
        open_eap(net.ssid)
        return 0
    password = None
    if net.security in ("psk", "sae") and not net.profile_uuid:
        mesg = f"{_esc(net.ssid)} · {SECURITY_LABELS[net.security]}"
        answer = rofi(rofi_command(theme, mesg, password=True), "")
        password = answer.stdout.removesuffix("\n") if answer.returncode == 0 else ""
        if not password:
            return 0
        if message := check_psk(password):
            return error(message)
    try:
        connect(runner, net, password)
    except NmcliError as e:
        return error(f"Nepřipojeno k {net.ssid}: {e}")
    return 0


def _run_rofi(argv: list[str], text: str) -> subprocess.CompletedProcess:
    return subprocess.run(argv, input=text, capture_output=True, text=True)


def _spawn(argv: list[str]) -> None:
    subprocess.Popen(argv, start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fknm-rofi", description=__doc__.splitlines()[0])
    parser.add_argument("--system-theme", action="store_true",
                        help="use your rofi config instead of the bundled theme")
    args = parser.parse_args(argv)

    # Like the other rofi menus: a second press of the shortcut replaces an open rofi.
    subprocess.run(["pkill", "-x", "rofi"], check=False)
    return run(run_command, _run_rofi, None if args.system_theme else THEME_PATH,
               open_gui=lambda: _spawn([str(GUI_PATH)]),
               open_eap=lambda ssid: _spawn([str(GUI_PATH), "--eap", ssid]))
