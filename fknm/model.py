"""Profiles, networks and the checks for what the user types into them."""

import ipaddress
import string
from dataclasses import dataclass, field


@dataclass
class Route:
    dest: str
    gateway: str = ""
    metric: int | None = None
    # Route attributes such as "table=100", kept so saving does not drop them.
    extra: tuple[str, ...] = ()


def parse_routes(text: str) -> list[Route]:
    """nmcli's ``ipv4.routes``: ``"10.8.0.0/16 10.99.0.9 100, 172.16.0.0/12 10.99.0.9"``."""
    routes = []
    for item in filter(None, (part.strip() for part in text.split(","))):
        dest, *rest = item.split()
        route = Route(dest)
        extra = []
        for token in rest:
            if "=" in token:
                extra.append(token)
            elif token.isdigit():
                route.metric = int(token)
            else:
                route.gateway = token
        route.extra = tuple(extra)
        routes.append(route)
    return routes


def format_routes(routes: list[Route]) -> str:
    parts = []
    for route in routes:
        tokens = [route.dest, route.gateway, "" if route.metric is None else str(route.metric), *route.extra]
        parts.append(" ".join(t for t in tokens if t))
    return ", ".join(parts)


@dataclass
class Ipv4:
    method: str = "auto"  # "auto", "manual" or "disabled"
    addresses: list[str] = field(default_factory=list)
    gateway: str = ""
    dns: list[str] = field(default_factory=list)
    ignore_auto_dns: bool = False
    routes: list[Route] = field(default_factory=list)
    ignore_auto_routes: bool = False


@dataclass
class Eap:
    method: str = "peap"  # "peap", "ttls" or "tls"
    phase2: str = "mschapv2"  # "mschapv2", "pap" or "gtc"; unused by TLS
    identity: str = ""
    anonymous_identity: str = ""
    ca_mode: str = "system"  # "system", "file" or "none"
    ca_cert: str = ""
    domain: str = ""
    client_cert: str = ""
    private_key: str = ""


@dataclass
class ProfileSettings:
    uuid: str
    name: str
    kind: str  # "wifi" or "ethernet"
    autoconnect: bool = True
    interface_name: str = ""
    mac_address: str = ""
    ssid: str = ""
    security: str = ""  # "open", "psk", "sae" or "eap"; "" for ethernet
    eap: Eap | None = None
    ipv4: Ipv4 = field(default_factory=Ipv4)


@dataclass
class Profile:
    uuid: str
    name: str
    kind: str
    device: str
    active: bool
    autoconnect: bool
    timestamp: int


@dataclass
class WifiNetwork:
    ssid: str
    signal: int
    security: str  # "open", "psk", "sae", "eap" or "wep"
    in_use: bool
    device: str
    profile_uuid: str | None = None


SECURITY_LABELS = {"open": "otevřená", "psk": "WPA2", "sae": "WPA3", "eap": "802.1X", "wep": "WEP"}


def classify_security(text: str) -> str:
    """Kind of security from the SECURITY column of ``nmcli device wifi list``."""
    if text in ("", "--"):
        return "open"
    if "802.1X" in text:
        return "eap"
    if "WPA3" in text and "WPA2" not in text and "WPA1" not in text:
        return "sae"
    if "WPA" in text:
        return "psk"
    return "wep"


def signal_bars(signal: int) -> int:
    """How many of the four signal bars are lit."""
    for bars, threshold in ((4, 75), (3, 50), (2, 25), (1, 0)):
        if signal > threshold:
            return bars
    return 0


# -- input checks: None when fine, otherwise a message for the user ----------

ADDRESS_ERROR = "Adresa musí být IPv4 s prefixem, např. 192.168.1.10/24."
IPV4_ERROR = "Neplatná IPv4 adresa."
ROUTE_DEST_ERROR = "Cíl routy musí být síť s prefixem, např. 10.8.0.0/16."
ROUTE_HOST_BITS_ERROR = "Cíl routy má nastavené bity hostu, správně je např. 10.8.0.0/16."
METRIC_ERROR = "Metrika musí být celé číslo od 0 do 4294967295."
PSK_ERROR = "Heslo musí mít 8 až 63 znaků (nebo 64 hex znaků)."


def check_address(text: str) -> str | None:
    if "/" not in text:
        return ADDRESS_ERROR
    try:
        ipaddress.IPv4Interface(text)
    except ValueError:
        return ADDRESS_ERROR
    return None


def check_ipv4(text: str) -> str | None:
    try:
        ipaddress.IPv4Address(text)
    except ValueError:
        return IPV4_ERROR
    return None


def check_route(dest: str, gateway: str, metric_text: str) -> str | None:
    if "/" not in dest:
        return ROUTE_DEST_ERROR
    try:
        ipaddress.IPv4Network(dest, strict=False)
    except ValueError:
        return ROUTE_DEST_ERROR
    try:
        ipaddress.IPv4Network(dest)
    except ValueError:
        return ROUTE_HOST_BITS_ERROR
    if gateway and (error := check_ipv4(gateway)):
        return error
    if metric_text and not (metric_text.isdigit() and int(metric_text) <= 4294967295):
        return METRIC_ERROR
    return None


def check_secret(text: str) -> str | None:
    """nmcli's editor, which keeps secrets off the command line, trims spaces and reads one line."""
    if "\n" in text or "\r" in text:
        return "Heslo nesmí obsahovat nový řádek."
    if text != text.strip():
        return "Heslo nesmí začínat ani končit mezerou."
    return None


def check_psk(password: str) -> str | None:
    if error := check_secret(password):
        return error
    if len(password) == 64 and all(c in string.hexdigits for c in password):
        return None
    if 8 <= len(password) <= 63 and all(" " <= c <= "~" for c in password):
        return None
    return PSK_ERROR


def check_ipv4_settings(ipv4: Ipv4) -> str | None:
    if ipv4.method == "manual" and not ipv4.addresses:
        return "Při ruční metodě je potřeba aspoň jedna adresa."
    errors = [check_address(a) for a in ipv4.addresses]
    if ipv4.gateway:
        errors.append(check_ipv4(ipv4.gateway))
    errors += [check_ipv4(d) for d in ipv4.dns]
    errors += [check_route(r.dest, r.gateway, "" if r.metric is None else str(r.metric)) for r in ipv4.routes]
    return next((e for e in errors if e), None)
