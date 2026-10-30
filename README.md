# fknm

Náhrada nmtui v GTK4 + libadwaita, ve stejném tmavém stylu jako
[SSH Wallet](../ssh_wallet). Všechny změny dělá přes `nmcli`, takže to, co
nastavíš, je obyčejný profil NetworkManageru.

- **Wi-Fi:** sítě v dosahu, připojení k uložené, otevřené, WPA2/WPA3 i 802.1X síti
- **Profily:** uložená připojení (wifi a kabel), zapnutí, vypnutí, úprava, smazání
- **Stav:** co právě platí (`ip addr`, `ip route`, DNS) a rychlé přidání nebo
  odebrání rout a DNS
- **Tailscale:** v hlavičce je vidět, jestli běží (jen zobrazení)
- **rofi:** rychlý výběr wifi sítě

## Požadavky

Arch Linux: `python` (3.11+), `python-gobject`, `gtk4`, `libadwaita`,
`networkmanager` (nmcli), `iproute2` a pro rychlý výběr `rofi`.

## Instalace

```sh
./install.sh
```

Vytvoří `~/.local/bin/fknm`, `~/.local/bin/fknm-rofi` (symlinky do tohoto
adresáře) a položku v nabídce aplikací. Aplikace běží přímo z tohoto adresáře,
takže ho po instalaci nepřesouvej (případně spusť `install.sh` znovu).

## Ovládání

| Klávesa | Akce |
|---|---|
| Ctrl+1 / 2 / 3 | záložka Wi-Fi / Profily / Stav |
| psaní, ↑ / ↓, Esc | hledání a výběr v seznamu (Wi-Fi, Profily) |
| Enter | Wi-Fi: připojit; Profily: zapnout nebo vypnout; Stav: upravit profil |
| Ctrl+E | upravit profil vybrané sítě, profilu nebo rozhraní |
| Ctrl+R | Wi-Fi: znovu naskenovat; Stav: obnovit |
| Delete | Profily: smazat profil (po potvrzení); Stav: odebrat routu nebo DNS z profilu |
| Ctrl+Q | konec |

### Wi-Fi

K uložené a otevřené síti se připojí rovnou, u nové WPA2/WPA3 se zeptá na heslo,
u nové 802.1X sítě (eduroam, firemní wifi) otevře dialog s metodou (PEAP, TTLS,
TLS), uživatelem, heslem a ověřením serveru. Bez CA certifikátu a domény serveru
upozorní, že heslo by mohla ukrást falešná síť se stejným názvem.

Když se připojení k nové síti nepovede (třeba špatné heslo), profil se zase smaže,
aby v Profilech nezůstal viset.

### Dialog profilu

Název, heslo (prázdné pole = beze změny), připojit automaticky, 802.1X, IPv4
metoda (Automaticky (DHCP) / Ručně / Vypnuto), adresy, brána, DNS a routy.
DNS a routy jdou přidat i k DHCP; přepínače „Ignorovat DNS/routy z DHCP“ vypnou ty
z DHCP. Po uložení se profil, který běží, znovu nahodí, aby změna platila hned.
IPv6 se jen zobrazuje, upravovat nejde.

### Stav

Adresy na rozhraních, routy (IPv4 i IPv6) a DNS, obnovuje se každé 3 s, dokud je
záložka vidět. U každé routy a DNS je, odkud pochází: `profil`, `DHCP`, `RA`,
`kernel` nebo `bez profilu`. Odebrat (✕ / Delete) jde jen to, co je z profilu;
routy a DNS z DHCP NetworkManager jen přebírá, ty jdou vypnout v dialogu profilu
najednou. `+ Přidat` uloží routu nebo DNS do profilu, který na rozhraní běží.
Rozhraní bez profilu (`tailscale0`, `virbr0`) jsou jen pro čtení.

### Kabel přes USB adaptér

Název USB síťového adaptéru (`enp197s0f4u1u1`) se odvozuje od portu, do kterého
je zapojený. Kdyby byl kabelový profil navázaný na název, v jiném portu by
NetworkManager založil nový „Wired connection 2“ a tvoje nastavení by se
nepoužilo. Proto fknm při uložení kabelového profilu naváže profil na MAC adresu
adaptéru (`802-3-ethernet.mac-address`) místo názvu rozhraní. Když adaptér
zrovna není zapojený, vazbu nechá, jak je.

## Rofi

`fknm-rofi` je rychlý výběr wifi: napíšeš kus názvu sítě, Enter a připojí se.
Nahoře je vidět aktuální připojení a stav Tailscale. U nové WPA2/WPA3 sítě se
zeptá na heslo, u nové 802.1X sítě otevře dialog v GTK aplikaci. Na konci jsou
položky `↻ Skenovat znovu` a `Otevřít fknm`. Chyby ukáže v rofi okně.

```sh
fknm-rofi                  # vlastní motiv (data/fknm.rasi)
fknm-rofi --system-theme   # tvůj rofi config
```

Klávesová zkratka v Hyprlandu (klávesu si vyber sám,
`~/.config/hypr/UserConfigs/UserKeybinds.conf`):

```
bindd = $mainMod, W, wifi, exec, $HOME/.local/bin/fknm-rofi
```

## Vzhled

Stejný jako SSH Wallet: písmo FantasqueSansM Nerd Font Mono (záložně Fira Code /
monospace), téměř černé pozadí a jediný zelený akcent. Barvy jsou v
[`fknm/ui/style.css`](fknm/ui/style.css) (proměnné nahoře v `:root`).

## Jak to funguje

- Čtení: `nmcli -t` (profily, sítě, DNS), `ip -j addr` / `ip -j route`
  (Stav), `/etc/resolv.conf`.
- Změny: jen `nmcli` (`connection add/modify/up/down/delete`,
  `device wifi connect`, `radio wifi on`). Všechno běží mimo hlavní vlákno,
  okno nezamrzne.
- Hesla (wifi, 802.1X, heslo ke klíči) si ukládá NetworkManager do systémového
  profilu. fknm je předává `nmcli connection edit` přes stdin, takže se nikdy
  neobjeví v příkazové řádce (`ps`) ani v proměnných prostředí. Editor nmcli
  ořezává mezery na začátku a konci, proto heslo s takovou mezerou fknm odmítne.
- Tailscale „běží“, když `tailscale0` má IPv4 adresu (stejně jako waybar skript).

## Testy

```sh
python -m unittest discover -s tests -t .
```

Testy nahrazují `nmcli` a `ip` falešnou verzí, takže na síti nic nemění. UI testy
potřebují grafický displej (jinak se přeskočí). Testy proti skutečnému
NetworkManageru běží jen s `FKNM_NM_TESTS=1`; zakládají a mažou jen dočasné
profily `fknm-test-*` s `autoconnect no`, které nikdy neaktivují.
