"""Command output captured from NetworkManager 1.58 and iproute2, shared by the tests."""

PROFILES_LIST = (
    "ToliLeng:u1:802-11-wireless:wlan0:yes:yes:1793392900\n"
    "lo:u2:loopback:lo:yes:yes:1\n"
    "virbr0:u3:bridge:virbr0:yes:yes:1\n"
    "Wired connection 1:u4:802-3-ethernet::no:yes:0\n"
)

# A throwaway profile made while planning (`nmcli -t -f ... connection show`).
PROBE_ETHERNET = """\
connection.id:fknm-probe
connection.uuid:adafcb2c-b82c-4ac3-845a-7b2e09cf7dea
connection.type:802-3-ethernet
connection.interface-name:fknm-probe0
connection.autoconnect:no
802-3-ethernet.mac-address:
ipv4.method:manual
ipv4.addresses:10.99.0.5/24, 10.99.1.5/24
ipv4.gateway:10.99.0.1
ipv4.dns:1.1.1.1,9.9.9.9
ipv4.ignore-auto-dns:no
ipv4.routes:10.8.0.0/16 10.99.0.9 100, 172.16.0.0/12 10.99.0.9
ipv4.ignore-auto-routes:no
"""

TOLILENG_SETTINGS = """\
connection.id:ToliLeng
connection.uuid:u1
connection.type:802-11-wireless
connection.autoconnect:yes
connection.interface-name:
802-11-wireless.ssid:ToliLeng
802-11-wireless-security.key-mgmt:wpa-psk
ipv4.method:auto
ipv4.addresses:
ipv4.gateway:
ipv4.dns:
ipv4.ignore-auto-dns:no
ipv4.routes:
ipv4.ignore-auto-routes:no
"""

WIRED_SETTINGS = """\
connection.id:Wired connection 1
connection.uuid:u4
connection.type:802-3-ethernet
connection.autoconnect:yes
connection.interface-name:enp197s0f4u1u1
802-3-ethernet.mac-address:
ipv4.method:auto
ipv4.addresses:
ipv4.gateway:
ipv4.dns:
ipv4.ignore-auto-dns:no
ipv4.routes:
ipv4.ignore-auto-routes:no
"""

EDUROAM_SETTINGS = """\
connection.id:eduroam
connection.uuid:u5
connection.type:802-11-wireless
connection.autoconnect:yes
connection.interface-name:
802-11-wireless.ssid:eduroam
802-11-wireless-security.key-mgmt:wpa-eap
802-1x.eap:peap
802-1x.phase2-auth:mschapv2
802-1x.identity:jan
802-1x.anonymous-identity:
802-1x.ca-cert:/etc/ssl/certs/eduroam-vsb-ca.pem
802-1x.system-ca-certs:no
802-1x.domain-suffix-match:vsb.cz
802-1x.client-cert:
802-1x.private-key:
ipv4.method:auto
ipv4.addresses:
ipv4.gateway:
ipv4.dns:
ipv4.ignore-auto-dns:no
ipv4.routes:
ipv4.ignore-auto-routes:no
"""

ADAPTER_LINK = '[{"ifname":"enp197s0f4u1u1","address":"f4:a8:0d:67:d0:a7","permaddr":null,"operstate":"DOWN"}]'

SCAN_NO = ["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY,DEVICE", "device", "wifi", "list", "--rescan", "no"]
SCAN_YES = SCAN_NO[:-1] + ["yes"]

# Includes an escaped SSID seen on two BSSIDs and a hidden network (empty SSID).
SCAN = (
    "*:ToliLeng:73:WPA2:wlan0\n"
    " :Cafe\\: A&B <x>:40:--:wlan0\n"
    " :Cafe\\: A&B <x>:62:--:wlan0\n"
    " ::80:WPA2:wlan0\n"
    " :Firma:30:WPA2 802.1X:wlan0\n"
    " :Sousedi:50:WPA3:wlan0\n"
)


def ssid_show(uuid: str) -> list[str]:
    return ["nmcli", "-t", "-f", "802-11-wireless.ssid", "connection", "show", "uuid", uuid]
