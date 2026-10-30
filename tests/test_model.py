import unittest

from fknm.model import (
    Ipv4, Route, check_address, check_ipv4, check_ipv4_settings, check_psk, check_route, check_secret,
    classify_security, format_routes, parse_routes, signal_bars,
)


class RoutesTest(unittest.TestCase):
    def test_routes_round_trip(self):
        text = "10.8.0.0/16 10.99.0.9 100, 172.16.0.0/12 10.99.0.9, 10.0.0.0/8 50 table=100"
        routes = parse_routes(text)

        self.assertEqual(routes, [Route("10.8.0.0/16", "10.99.0.9", 100), Route("172.16.0.0/12", "10.99.0.9"),
                                  Route("10.0.0.0/8", "", 50, ("table=100",))])
        self.assertEqual(format_routes(routes), text)

    def test_empty_routes(self):
        self.assertEqual(parse_routes(""), [])
        self.assertEqual(format_routes([]), "")


class SecurityTest(unittest.TestCase):
    def test_classify_security(self):
        for text, kind in [("", "open"), ("--", "open"), ("WPA2", "psk"), ("WPA1 WPA2", "psk"),
                           ("WPA2 WPA3", "psk"), ("WPA3", "sae"), ("WPA2 802.1X", "eap"), ("WEP", "wep")]:
            self.assertEqual(classify_security(text), kind, text)

    def test_signal_bars(self):
        self.assertEqual([signal_bars(s) for s in (0, 10, 30, 60, 76)], [0, 1, 2, 3, 4])


class ValidationTest(unittest.TestCase):
    def test_check_address(self):
        self.assertIsNone(check_address("192.168.88.50/24"))
        for bad in ("192.168.88.50", "192.168.88.300/24", "fe80::1/64", "x/24", "10.0.0.1/33"):
            self.assertEqual(check_address(bad), "Adresa musí být IPv4 s prefixem, např. 192.168.1.10/24.", bad)

    def test_check_ipv4(self):
        self.assertIsNone(check_ipv4("1.1.1.1"))
        self.assertEqual(check_ipv4("1.1.1"), "Neplatná IPv4 adresa.")
        self.assertEqual(check_ipv4("1.1.1.1/32"), "Neplatná IPv4 adresa.")

    def test_check_route(self):
        self.assertIsNone(check_route("10.8.0.0/16", "192.168.88.5", "100"))
        self.assertIsNone(check_route("10.8.0.0/16", "", ""))
        self.assertEqual(check_route("10.8.0.1/16", "", ""),
                         "Cíl routy má nastavené bity hostu, správně je např. 10.8.0.0/16.")
        self.assertEqual(check_route("10.8.0.0", "", ""), "Cíl routy musí být síť s prefixem, např. 10.8.0.0/16.")
        self.assertEqual(check_route("10.8.0.0/16", "x", ""), "Neplatná IPv4 adresa.")
        self.assertEqual(check_route("10.8.0.0/16", "", "-1"), "Metrika musí být celé číslo od 0 do 4294967295.")
        self.assertEqual(check_route("10.8.0.0/16", "", "4294967296"),
                         "Metrika musí být celé číslo od 0 do 4294967295.")

    def test_check_psk(self):
        self.assertIsNone(check_psk("sp ace pw: \\x"))
        self.assertIsNone(check_psk("a" * 63))
        self.assertIsNone(check_psk("0123456789abcdef" * 4))
        self.assertEqual(check_psk("short"), "Heslo musí mít 8 až 63 znaků (nebo 64 hex znaků).")
        self.assertEqual(check_psk("ž" * 10), "Heslo musí mít 8 až 63 znaků (nebo 64 hex znaků).")
        self.assertEqual(check_psk("g" * 64), "Heslo musí mít 8 až 63 znaků (nebo 64 hex znaků).")
        self.assertEqual(check_psk(" password1"), "Heslo nesmí začínat ani končit mezerou.")

    def test_check_secret(self):
        self.assertIsNone(check_secret("heslo s mezerou"))
        self.assertEqual(check_secret("heslo "), "Heslo nesmí začínat ani končit mezerou.")
        self.assertEqual(check_secret("a\nb"), "Heslo nesmí obsahovat nový řádek.")

    def test_check_ipv4_settings(self):
        self.assertEqual(check_ipv4_settings(Ipv4(method="manual")),
                         "Při ruční metodě je potřeba aspoň jedna adresa.")
        self.assertIsNone(check_ipv4_settings(Ipv4(method="manual", addresses=["10.0.0.5/24"])))
        self.assertEqual(check_ipv4_settings(Ipv4(method="manual", addresses=["10.0.0.5/24"], gateway="x")),
                         "Neplatná IPv4 adresa.")
        self.assertEqual(check_ipv4_settings(Ipv4(dns=["1.1.1"])), "Neplatná IPv4 adresa.")
        self.assertEqual(check_ipv4_settings(Ipv4(routes=[Route("10.8.0.1/16")])),
                         "Cíl routy má nastavené bity hostu, správně je např. 10.8.0.0/16.")
        self.assertIsNone(check_ipv4_settings(Ipv4()))
