"""What is in effect right now: addresses, routes, DNS and Tailscale, plus quick edits.

Live values come from ``ip -j`` and nmcli; edits go into the profile running on
the interface (``ipv4.routes``/``ipv4.dns``), which is then brought up again.
"""

import ipaddress
import json
from dataclasses import dataclass
from pathlib import Path

from fknm.model import Route
from fknm.nmcli import NmcliError, Runner, nmcli, split_terse
from fknm.profiles import read_settings, save


@dataclass
class Interface:
    name: str
    state: str
    profile: str | None
    uuid: str | None
    addresses: list[str]


@dataclass
class RouteEntry:
    text: str
    dev: str
    origin: str
    route: Route | None  # the profile's route when it can be removed, else None


@dataclass
class DnsEntry:
    server: str
    dev: str
    origin: str
    removable: bool


@dataclass
class Status:
    interfaces: list[Interface]
    routes: list[RouteEntry]
    dns: list[DnsEntry]
    resolv: str
    tailscale: bool


_ORIGINS = {"dhcp": "DHCP", "ra": "RA", "kernel": "kernel", "static": "profil"}
_OUR_TYPES = ("802-11-wireless", "802-3-ethernet")


def _json_list(ip_addr_json: str) -> list[dict]:
    try:
        return json.loads(ip_addr_json or "[]")
    except ValueError:
        return []


def tailscale_running(ip_addr_json: str) -> bool:
    """Same rule as the waybar script: tailscale0 exists and has an IPv4 address."""
    return ipv4_address(ip_addr_json, "tailscale0") is not None


def ipv4_address(ip_addr_json: str, dev: str) -> str | None:
    for link in _json_list(ip_addr_json):
        if link.get("ifname") == dev:
            for addr in link.get("addr_info", []):
                if addr.get("family") == "inet":
                    return f"{addr['local']}/{addr['prefixlen']}"
    return None


def parse_interfaces(ip_addr_json: str, active: dict[str, tuple[str, str]]) -> list[Interface]:
    """``active`` maps a device to the (uuid, name) of the profile running on it."""
    interfaces = []
    for link in _json_list(ip_addr_json):
        name = link.get("ifname", "")
        if name == "lo":
            continue
        uuid, profile = active.get(name, (None, None))
        addresses = [f"{a['local']}/{a['prefixlen']}" for a in link.get("addr_info", []) if "local" in a]
        interfaces.append(Interface(name, link.get("operstate", ""), profile, uuid, addresses))
    return interfaces


def route_text(r: dict) -> str:
    parts = [r.get("dst", "")]
    if r.get("gateway"):
        parts += ["via", r["gateway"]]
    parts += ["dev", r.get("dev", "")]
    if r.get("metric") is not None:
        parts += ["metric", str(r["metric"])]
    if "linkdown" in r.get("flags", []):
        parts.append("linkdown")
    return " ".join(parts)


def route_origin(r: dict, has_profile: bool) -> str:
    if not has_profile:
        return "bez profilu"
    protocol = r.get("protocol", "")
    return _ORIGINS.get(protocol, protocol)


def resolv_summary(text: str) -> str:
    servers = [line.split()[1] for line in text.splitlines()
               if line.startswith("nameserver") and len(line.split()) > 1]
    if "127.0.0.53" in servers:
        return "127.0.0.53 (systemd-resolved)"
    return ", ".join(servers)


def _run_json(runner: Runner, argv: list[str]) -> list[dict]:
    result = runner(argv, None)
    if result.returncode != 0:
        raise NmcliError(result.stderr.strip() or f"{' '.join(argv)} selhal")
    return _json_list(result.stdout)


def _route_dest(dst: str) -> str:
    """``ip route``'s dst in the form a profile stores it ("default" -> 0.0.0.0/0, host -> /32)."""
    if dst == "default":
        return "0.0.0.0/0"
    return dst if "/" in dst else f"{dst}/32"


def _profile_route(r: dict, routes: list[Route]) -> Route | None:
    try:
        dest = ipaddress.ip_network(_route_dest(r.get("dst", "")), strict=False)
    except ValueError:
        return None
    for route in routes:
        try:
            same = ipaddress.ip_network(route.dest, strict=False) == dest
        except ValueError:
            continue
        if same and route.gateway == r.get("gateway", ""):
            return route
    return None


def _device_dns(text: str) -> dict[str, list[str]]:
    dns: dict[str, list[str]] = {}
    device = ""
    for line in text.splitlines():
        key, _, value = line.partition(":")
        if key == "GENERAL.DEVICE":
            device = value
        elif key.startswith("IP4.DNS") and value:
            dns.setdefault(device, []).append(value)
    return dns


def read_status(runner: Runner, resolv_path: Path = Path("/etc/resolv.conf")) -> Status:
    addr_json = json.dumps(_run_json(runner, ["ip", "-j", "addr"]))
    routes = _run_json(runner, ["ip", "-j", "route"]) + _run_json(runner, ["ip", "-j", "-6", "route"])

    active: dict[str, tuple[str, str]] = {}
    for line in filter(None, nmcli(runner, ["-t", "-f", "DEVICE,UUID,NAME,TYPE", "connection", "show",
                                            "--active"]).splitlines()):
        dev, uuid, name, kind = split_terse(line)[:4]
        if dev and kind in _OUR_TYPES:
            active[dev] = (uuid, name)
    settings = {dev: read_settings(runner, uuid) for dev, (uuid, _name) in active.items()}

    route_entries = []
    for r in routes:
        dev = r.get("dev", "")
        origin = route_origin(r, dev in active)
        route = _profile_route(r, settings[dev].ipv4.routes) if origin == "profil" else None
        route_entries.append(RouteEntry(route_text(r), dev, origin, route))

    dns_entries = []
    for dev, servers in _device_dns(nmcli(runner, ["-t", "-f", "GENERAL.DEVICE,IP4.DNS", "device", "show"])).items():
        for server in servers:
            if dev not in active:
                dns_entries.append(DnsEntry(server, dev, "bez profilu", False))
            elif server in settings[dev].ipv4.dns:
                dns_entries.append(DnsEntry(server, dev, "profil", True))
            else:
                dns_entries.append(DnsEntry(server, dev, "DHCP", False))

    try:
        resolv = resolv_summary(resolv_path.read_text())
    except OSError:
        resolv = ""
    return Status(parse_interfaces(addr_json, active), route_entries, dns_entries, resolv,
                  tailscale_running(addr_json))


def _edit(runner: Runner, uuid: str, device: str, change) -> None:
    settings = read_settings(runner, uuid)
    change(settings.ipv4)
    save(runner, settings, device=device, reactivate=True, write_eap=False)


def add_route(runner: Runner, uuid: str, device: str, route: Route) -> None:
    _edit(runner, uuid, device, lambda ipv4: ipv4.routes.append(route))


def remove_route(runner: Runner, uuid: str, device: str, route: Route) -> None:
    def change(ipv4):
        ipv4.routes = [r for r in ipv4.routes if r != route]
    _edit(runner, uuid, device, change)


def add_dns(runner: Runner, uuid: str, device: str, server: str) -> None:
    def change(ipv4):
        if server not in ipv4.dns:
            ipv4.dns.append(server)
    _edit(runner, uuid, device, change)


def remove_dns(runner: Runner, uuid: str, device: str, server: str) -> None:
    def change(ipv4):
        ipv4.dns = [d for d in ipv4.dns if d != server]
    _edit(runner, uuid, device, change)
