"""NetworkManager connection profiles: list, read, save, switch on and off, delete.

Secrets never go on the command line, where any process could read them;
``set_secrets`` feeds them to nmcli's interactive editor on stdin instead.
"""

import json

from fknm.model import Eap, Ipv4, Profile, ProfileSettings, check_secret, format_routes, parse_routes
from fknm.nmcli import NmcliError, Runner, friendly_error, nmcli, parse_fields, split_terse

PROFILE_FIELDS = [
    "connection.id", "connection.uuid", "connection.type", "connection.autoconnect",
    "connection.interface-name", "802-3-ethernet.mac-address", "802-11-wireless.ssid",
    "802-11-wireless-security.key-mgmt", "802-1x.eap", "802-1x.phase2-auth", "802-1x.identity",
    "802-1x.anonymous-identity", "802-1x.ca-cert", "802-1x.system-ca-certs", "802-1x.domain-suffix-match",
    "802-1x.client-cert", "802-1x.private-key", "ipv4.method", "ipv4.addresses", "ipv4.gateway", "ipv4.dns",
    "ipv4.ignore-auto-dns", "ipv4.routes", "ipv4.ignore-auto-routes",
]

SECRET_PROPS = {
    "psk": "802-11-wireless-security.psk",
    "password": "802-1x.password",
    "key_password": "802-1x.private-key-password",
}

_KINDS = {"802-11-wireless": "wifi", "802-3-ethernet": "ethernet"}
_SECURITY = {"": "open", "none": "open", "wpa-psk": "psk", "sae": "sae", "wpa-eap": "eap"}


def _yes(value: bool) -> str:
    return "yes" if value else "no"


def list_profiles(runner: Runner) -> list[Profile]:
    """Wifi and ethernet profiles; loopback, bridges and the like belong to someone else."""
    out = nmcli(runner, ["-t", "-f", "NAME,UUID,TYPE,DEVICE,ACTIVE,AUTOCONNECT,TIMESTAMP", "connection", "show"])
    profiles = []
    for line in filter(None, out.splitlines()):
        name, uuid, kind, device, active, autoconnect, timestamp = split_terse(line)
        if kind in _KINDS:
            profiles.append(Profile(uuid, name, _KINDS[kind], device, active == "yes", autoconnect == "yes",
                                    int(timestamp or 0)))
    return profiles


def ethernet_state(runner: Runner) -> str | None:
    """State of the first ethernet device ("unavailable" = no cable), None without one."""
    out = nmcli(runner, ["-t", "-f", "TYPE,STATE", "device"])
    for line in filter(None, out.splitlines()):
        kind, state = split_terse(line)[:2]
        if kind == "ethernet":
            return state
    return None


def read_settings(runner: Runner, uuid: str) -> ProfileSettings:
    fields = parse_fields(nmcli(runner, ["-t", "-f", ",".join(PROFILE_FIELDS), "connection", "show", "uuid", uuid]))
    get = lambda key: fields.get(key, "")  # noqa: E731 - absent settings are left out by nmcli
    kind = _KINDS.get(get("connection.type"), get("connection.type"))
    security = _SECURITY.get(get("802-11-wireless-security.key-mgmt"), "psk") if kind == "wifi" else ""
    ipv4 = Ipv4(
        method=get("ipv4.method") or "auto",
        addresses=[a for a in get("ipv4.addresses").split(", ") if a],
        gateway=get("ipv4.gateway"),
        dns=[d for d in get("ipv4.dns").split(",") if d],
        ignore_auto_dns=get("ipv4.ignore-auto-dns") == "yes",
        routes=parse_routes(get("ipv4.routes")),
        ignore_auto_routes=get("ipv4.ignore-auto-routes") == "yes",
    )
    eap = None
    if security == "eap":
        ca_cert = get("802-1x.ca-cert").removeprefix("file://")
        ca_mode = "system" if get("802-1x.system-ca-certs") == "yes" else ("file" if ca_cert else "none")
        eap = Eap(get("802-1x.eap").split(",")[0] or "peap", get("802-1x.phase2-auth") or "mschapv2",
                  get("802-1x.identity"), get("802-1x.anonymous-identity"), ca_mode,
                  ca_cert if ca_mode == "file" else "", get("802-1x.domain-suffix-match"),
                  get("802-1x.client-cert").removeprefix("file://"),
                  get("802-1x.private-key").removeprefix("file://"))
    return ProfileSettings(
        uuid=get("connection.uuid") or uuid, name=get("connection.id"), kind=kind,
        autoconnect=get("connection.autoconnect") != "no", interface_name=get("connection.interface-name"),
        mac_address=get("802-3-ethernet.mac-address"), ssid=get("802-11-wireless.ssid"), security=security,
        eap=eap, ipv4=ipv4,
    )


def eap_args(eap: Eap) -> list[str]:
    """802.1X properties for ``connection add``/``modify``, without the secrets."""
    args = ["802-1x.eap", eap.method, "802-1x.identity", eap.identity,
            "802-1x.anonymous-identity", eap.anonymous_identity, "802-1x.domain-suffix-match", eap.domain]
    if eap.method != "tls":
        args += ["802-1x.phase2-auth", eap.phase2]
    args += ["802-1x.system-ca-certs", _yes(eap.ca_mode == "system"),
             "802-1x.ca-cert", eap.ca_cert if eap.ca_mode == "file" else ""]
    if eap.method == "tls":
        args += ["802-1x.client-cert", eap.client_cert, "802-1x.private-key", eap.private_key]
    return args


def settings_args(settings: ProfileSettings) -> list[str]:
    """Property/value pairs for ``connection modify``; every editable property, every time."""
    ipv4 = settings.ipv4
    static = ipv4.method == "manual"
    enabled = ipv4.method != "disabled"
    return [
        "connection.id", settings.name, "connection.autoconnect", _yes(settings.autoconnect),
        "ipv4.method", ipv4.method,
        "ipv4.addresses", ",".join(ipv4.addresses) if static else "",
        "ipv4.gateway", ipv4.gateway if static else "",
        "ipv4.dns", ",".join(ipv4.dns) if enabled else "",
        "ipv4.ignore-auto-dns", _yes(ipv4.ignore_auto_dns),
        "ipv4.routes", format_routes(ipv4.routes) if enabled else "",
        "ipv4.ignore-auto-routes", _yes(ipv4.ignore_auto_routes),
    ]


def set_secrets(runner: Runner, uuid: str, secrets: dict[str, str]) -> None:
    """Store secrets (keys of SECRET_PROPS) in the profile through the editor on stdin.

    The editor exits 0 even when a ``set`` fails, so success is read from its output.
    """
    if not secrets:
        return
    for value in secrets.values():
        if error := check_secret(value):
            raise NmcliError(error)
    script = "nmcli save-confirmation no\n"
    script += "".join(f"set {SECRET_PROPS[key]} {value}\n" for key, value in secrets.items())
    script += "save persistent\nquit\n"
    result = runner(["nmcli", "connection", "edit", "uuid", uuid], script)
    if result.returncode != 0:
        raise NmcliError(friendly_error(result.stderr))
    output = result.stdout + result.stderr
    if "successfully updated" not in output:
        error = next((line.split("Error: ", 1)[1] for line in output.splitlines() if "Error: " in line), None)
        raise NmcliError(error or "nmcli neuložil heslo")


def adapter_mac(runner: Runner, ifname: str) -> str | None:
    """Permanent MAC address of an interface, None when it is not plugged in."""
    if not ifname:
        return None
    result = runner(["ip", "-j", "link", "show", ifname], None)
    if result.returncode != 0:
        return None
    try:
        link = json.loads(result.stdout)[0]
    except (ValueError, IndexError):
        return None
    return link.get("permaddr") or link.get("address")


def save(runner: Runner, settings: ProfileSettings, secrets: dict[str, str] | None = None,
         device: str = "", reactivate: bool = False) -> None:
    """Write the profile, then its secrets, then bring it up again so the change applies now.

    An ethernet profile is bound to its adapter's MAC instead of the interface
    name: a USB adapter's name follows the port it is plugged into.
    """
    args = settings_args(settings)
    if settings.eap:
        args += eap_args(settings.eap)
    if settings.kind == "ethernet" and (mac := adapter_mac(runner, device or settings.interface_name)):
        args += ["802-3-ethernet.mac-address", mac, "connection.interface-name", ""]
    nmcli(runner, ["connection", "modify", "uuid", settings.uuid, *args])
    set_secrets(runner, settings.uuid, secrets or {})
    if reactivate:
        activate(runner, settings.uuid)


def activate(runner: Runner, uuid: str) -> None:
    nmcli(runner, ["connection", "up", "uuid", uuid])


def deactivate(runner: Runner, uuid: str) -> None:
    nmcli(runner, ["connection", "down", "uuid", uuid])


def delete(runner: Runner, uuid: str) -> None:
    nmcli(runner, ["connection", "delete", "uuid", uuid])


def profile_subtitle(profile: Profile, settings: ProfileSettings, ethernet_state: str | None) -> str:
    """Where the profile is and how it gets its address, e.g. "wlan0 · DHCP"."""
    parts = []
    if profile.active and profile.device:
        parts.append(profile.device)
    elif profile.kind == "ethernet" and ethernet_state == "unavailable":
        parts.append("kabel nezapojen")
    elif profile.kind == "ethernet" and ethernet_state is None:
        parts.append("adaptér nepřipojen")
    ipv4 = settings.ipv4
    if ipv4.method == "manual":
        parts += ["ručně", ", ".join(ipv4.addresses)]
        if ipv4.dns:
            parts.append("DNS " + ", ".join(ipv4.dns))
    elif ipv4.method == "disabled":
        parts.append("vypnuto")
    else:
        parts.append("DHCP")
    return " · ".join(p for p in parts if p)
