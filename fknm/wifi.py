"""Wifi networks in range and connecting to them."""

import re

from fknm.model import Eap, WifiNetwork, classify_security
from fknm.nmcli import NmcliError, Runner, nmcli, parse_fields, split_terse
from fknm.profiles import activate, deactivate, delete, eap_args, list_profiles, set_secrets

_UUID = re.compile(r"\(([0-9a-f-]{36})\)")
_KEY_MGMT = {"psk": "wpa-psk", "sae": "sae"}


def saved_ssids(runner: Runner) -> dict[str, str]:
    """SSID -> uuid of its profile; with several profiles for one SSID the last used wins."""
    newest: dict[str, tuple[int, str]] = {}
    for profile in list_profiles(runner):
        if profile.kind != "wifi":
            continue
        out = nmcli(runner, ["-t", "-f", "802-11-wireless.ssid", "connection", "show", "uuid", profile.uuid])
        ssid = parse_fields(out).get("802-11-wireless.ssid", "")
        if ssid and profile.timestamp >= newest.get(ssid, (-1, ""))[0]:
            newest[ssid] = (profile.timestamp, profile.uuid)
    return {ssid: uuid for ssid, (_ts, uuid) in newest.items()}


def scan(runner: Runner, rescan: bool = False) -> list[WifiNetwork]:
    """Networks in range, one per SSID, sorted like the user sees them.

    Without ``rescan`` this is the last scan, so it returns at once.
    """
    out = nmcli(runner, ["-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY,DEVICE", "device", "wifi", "list",
                         "--rescan", "yes" if rescan else "no"])
    by_ssid: dict[str, WifiNetwork] = {}
    for line in filter(None, out.splitlines()):
        in_use, ssid, signal, security, device = split_terse(line)[:5]
        if not ssid:
            continue  # hidden network
        net = WifiNetwork(ssid, int(signal or 0), classify_security(security), in_use == "*", device)
        known = by_ssid.get(ssid)
        if known is None or (net.in_use, net.signal) > (known.in_use, known.signal):
            by_ssid[ssid] = net
    saved = saved_ssids(runner)
    for net in by_ssid.values():
        net.profile_uuid = saved.get(net.ssid)
    return sort_networks(list(by_ssid.values()))


def sort_networks(nets: list[WifiNetwork]) -> list[WifiNetwork]:
    return sorted(nets, key=lambda n: (not n.in_use, n.profile_uuid is None, -n.signal))


def radio_state(runner: Runner) -> str:
    """"enabled", "disabled", or "missing" when there is no wifi card."""
    if "wifi" not in nmcli(runner, ["-t", "-f", "TYPE", "device"]).split():
        return "missing"
    return "enabled" if nmcli(runner, ["-t", "radio", "wifi"]).strip() == "enabled" else "disabled"


def enable_radio(runner: Runner) -> None:
    nmcli(runner, ["radio", "wifi", "on"])


def _add_and_activate(runner: Runner, add_args: list[str], secrets: dict[str, str]) -> None:
    """Create a profile, store its secrets and bring it up; a profile that fails is deleted again."""
    out = nmcli(runner, add_args)
    match = _UUID.search(out)
    if not match:
        raise NmcliError("nmcli nevrátil nový profil")
    uuid = match.group(1)
    try:
        set_secrets(runner, uuid, secrets)
        activate(runner, uuid)
    except NmcliError:
        try:
            delete(runner, uuid)
        except NmcliError:
            pass  # the activation error is the one worth showing
        raise


def _add_wifi_args(ssid: str, device: str) -> list[str]:
    args = ["connection", "add", "type", "wifi", "con-name", ssid]
    if device:
        args += ["ifname", device]
    return args + ["ssid", ssid]


def connect(runner: Runner, net: WifiNetwork, password: str | None = None) -> None:
    """Connect to a saved, open or WPA network; 802.1X networks go through ``connect_eap``."""
    if net.profile_uuid:
        activate(runner, net.profile_uuid)
    elif net.security == "wep":
        raise NmcliError("WEP sítě nejsou podporované.")
    elif net.security == "open":
        nmcli(runner, ["device", "wifi", "connect", net.ssid, *(["ifname", net.device] if net.device else [])])
    elif net.security in _KEY_MGMT:
        if password is None:
            raise ValueError("a new WPA network needs a password")
        args = _add_wifi_args(net.ssid, net.device) + ["wifi-sec.key-mgmt", _KEY_MGMT[net.security]]
        _add_and_activate(runner, args, {"psk": password})
    else:
        raise ValueError("802.1X networks connect through connect_eap")


def connect_eap(runner: Runner, ssid: str, device: str, eap: Eap, secrets: dict[str, str]) -> None:
    _add_and_activate(runner, _add_wifi_args(ssid, device) + ["wifi-sec.key-mgmt", "wpa-eap", *eap_args(eap)],
                      secrets)


def disconnect(runner: Runner, net: WifiNetwork) -> None:
    if not net.profile_uuid:
        raise ValueError("only a network with a profile can be disconnected")
    deactivate(runner, net.profile_uuid)
