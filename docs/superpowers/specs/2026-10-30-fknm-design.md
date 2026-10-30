# fknm: návrh

Datum: 2026-10-30

## Záměr

nmtui funguje, ale je ošklivý a nepřehledný. fknm ho nahradí ve stylu
ssh_wallet (`/home/kuba/ssh_wallet`): GTK4 okno pro správu sítě a k tomu rofi
pro rychlé připojení k wifi. Používá se hlavně na připojení k wifi, nastavení
IP adresy, rout a DNS a na rychlý pohled na to, co právě platí (`ip addr`,
`ip route`, DNS).

Uživatel používá wifi a ethernet. Z VPN jen Tailscale, a u něj stačí vidět, jestli běží.

V textu je u každého rozhodnutí poznamenáno, kdo ho udělal: **(uživatel)**
znamená, že rozhodl uživatel, **(návrh)** je rozhodnutí z brainstormingu,
které uživatel viděl v ukázce nebo shrnutí a odsouhlasil ho, ale sám ho neřekl.

## Cíle

- Připojit se k wifi z GTK okna i z rofi (uživatel).
- Měnit IPv4 adresy, bránu, routy a DNS v profilech připojení (uživatel).
- Vidět aktuální adresy, routy a DNS a rovnou je tam upravovat (uživatel).
- Podporovat 802.1X wifi: PEAP, TTLS a TLS (uživatel).
- Ukazovat stav Tailscale (uživatel).
- Vzhled a ovládání stejné jako ssh_wallet (uživatel).

## Mimo rozsah

Rozhodnutí (návrh), uživatel seznam viděl a odsouhlasil:

- Správa VPN. Tailscale se jen zobrazuje a nepřepíná.
- Úpravy IPv6. IPv6 adresy a routy se jen zobrazí a nastavení zůstává automatické.
- Hostname a globální DNS.
- Skryté sítě.
- Bond, bridge, VLAN, hotspot.
- 802.1X přes kabel. 802.1X bude jen na wifi.
- Zakládání nových profilů (uživatel). Kabelový profil je jen jeden a
  wifi profily vznikají připojením k síti.
- V rofi se nic neupravuje: žádné IP, DNS, routy ani mazání profilů.

## Čeho se vyvarovat

- Vzhled jako nmtui. Musí to vypadat jako ssh_wallet, jinak aplikace nemá smysl.
- Okno, které při volání nmcli zamrzne. Připojení k síti trvá i desítky sekund.
- Tichá ztráta připojení nebo tichá chyba. Každé selhání nmcli musí uživatel vidět.
- Hesla v příkazové řádce. ssh_wallet si zakládá na tom, že se heslo neobjeví
  v `ps` ani v proměnných prostředí, a tady to platí taky (návrh, viz Omezení).

## Omezení a prostředí

- Arch Linux. Python 3.14 (kód cílí na 3.11+), python-gobject 3.58, GTK 4.24,
  libadwaita 1.10, NetworkManager/nmcli 1.58, rofi 2.0, `notify-send` je k dispozici.
- Změny dělá jen `nmcli` (uživatel). Adresy a routy pro záložku Stav se čtou
  z `ip -j addr` a `ip -j route` (návrh), protože uživatel chtěl vidět přesně
  `ip addr` a `ip route`. DNS se čte z nmcli (`IP4.DNS` u zařízení) a
  `/etc/resolv.conf`. systemd-resolved běží a `resolv.conf` ukazuje na 127.0.0.53.
- Práva: `nmcli general permissions` hlásí `yes` u `network-control`,
  `settings.modify.system`, `settings.modify.own` a `wifi.scan`. Polkit tedy
  nevyskočí. Hostname a globální DNS potřebují `auth`, ale nejsou v rozsahu.
- Stav Tailscale se zjišťuje stejně jako ve `~/.config/waybar/scripts/tailscale-status.sh`:
  běží, když `tailscale0` existuje a má IPv4 adresu.
- Hesla (wifi PSK, 802.1X heslo i heslo ke klíči) se nesmí objevit v argv
  ani v env (návrh). nmcli k tomu má `--ask` (heslo čte ze stdin) a
  `passwd-file` u `connection up`. U secretů s flags 0 by je NetworkManager
  po úspěšné aktivaci měl uložit do profilu. Builder musí ověřit, že to
  v NM 1.58 opravdu funguje. Pokud nějaká cesta jinak než přes argv nejde
  (třeba změna hesla u uloženého profilu), musí to říct, ne to tiše obejít.
- Hesla si ukládá NetworkManager sám do systémového profilu (flags 0) jako
  při běžném použití nmcli. Keyring se nepoužívá (návrh).

## Vzhled

Přebírá se z ssh_wallet: `ssh_wallet/ui/style.css` (proměnné v `:root`),
`ssh_wallet/ui/style.py` (`FORCE_DARK`, `Gtk.FontRendering.MANUAL` kvůli
useknutým glyfům FantasqueSansM ve 14pt) a `data/ssh-wallet.rasi`.

- Pozadí `#0f1010`, plochy `#161818`, linky `#262a2a`, text `#dddddd`, tlumený
  text `#8a918f`, jediný akcent `#87d5a2`.
- Písmo FantasqueSansM Nerd Font Mono 14pt, záložní Fira Code a monospace.
- Prompt `>` místo lupy u vyhledávání, vybraný řádek má vlevo 3px zelený
  proužek, tlačítka na řádku se ukážou až po najetí nebo výběru, štítky
  (`.badge`), dole lišta se zkratkami (`.hints`), chyby a potvrzení jako toast.
- Formuláře jsou `Adw.Dialog` se Zrušit a Uložit v hlavičce, skupiny
  `Adw.PreferencesGroup`, „+ Přidat“ v záhlaví skupiny a 🗑 u řádku. Stejně
  jako `ssh_wallet/ui/host_dialog.py`.
- Texty v aplikaci a README jsou česky, komentáře v kódu anglicky (stejně
  jako ssh_wallet).

Ukázky z brainstormingu jsou v `.superpowers/brainstorm/59510-1793395966/content/`
(`layout-v2.html`, `edit.html`, `rofi.html`) a slouží jako předloha.

## GTK aplikace

### Hlavní okno (uživatel: varianta A)

Hlavička: vlevo nic (uživatel: bez názvu), uprostřed přepínač záložek
**Wi-Fi / Profily / Stav**, vpravo `● tailscale` (uživatel: celé slovo).
Puntík je zelený, když Tailscale běží, a šedý, když neběží. Na
`tailscale0` se nedá kliknout.

Zkratky (návrh):

| Klávesa | Akce |
|---|---|
| Ctrl+1/2/3 | přepnout záložku |
| psaní, ↑/↓, Esc | hledání a výběr jako v ssh_wallet (Wi-Fi, Profily) |
| Ctrl+R | Wi-Fi: znovu naskenovat; Stav: obnovit |
| Ctrl+E | upravit vybraný profil nebo rozhraní |
| Delete | Profily: smazat profil (po potvrzení); Stav: odebrat vybranou routu nebo DNS z profilu |
| Ctrl+Q | konec |

Aplikace běží jen v jedné instanci (`Adw.Application`). Druhé spuštění
přenese existující okno do popředí.

### Záložka Wi-Fi

- Sítě v dosahu (`nmcli device wifi list`). Nahoře je připojená síť, za ní
  ostatní podle síly signálu (návrh). U řádku je signál ▂▄▆█, zabezpečení
  (WPA2, WPA3, 802.1X, otevřená) a štítky „Připojeno“ a „Uloženo“.
- Enter nebo „Připojit“:
  - uložená a otevřená síť: připojí rovnou,
  - nová WPA2/WPA3 síť: dialog s heslem,
  - nová 802.1X síť: dialog 802.1X (viz níže).
- Připojená síť má „Upravit“ (otevře dialog profilu) a „Odpojit“.
- Ctrl+R naskenuje znovu (`nmcli device wifi rescan`).
- Když je wifi vypnutá nebo karta chybí, ukáže se status page
  s vysvětlením. Při vypnuté wifi je na ní tlačítko na zapnutí (návrh).

### Záložka Profily

- Uložená připojení přes wifi a ethernet. `lo`, `virbr0` a profily, které
  spravuje někdo jiný, se nezobrazují (návrh).
- Řádek ukazuje název, zařízení nebo stav („kabel nezapojen“), metodu
  (DHCP nebo ručně s adresou a DNS) a štítky Wi-Fi/Kabel, Aktivní, Ručně.
- Enter zapne nebo vypne profil, Ctrl+E otevře dialog profilu, Delete
  smaže profil po potvrzení.

### Kabelový profil a USB adaptér

Uživatel používá jeden kabelový profil a k počítači připojuje vždycky
externí USB RJ45 adaptér (Realtek USB LAN, MAC `f4:a8:0d:67:d0:a7`). Dnes
je „Wired connection 1“ navázaný na `connection.interface-name
enp197s0f4u1u1`. Ten název se odvozuje od USB portu
(`ID_NET_NAME_PATH`, `pci-0000:c5:00.4-usb-0:1.1`), takže v jiném portu
by NetworkManager založil nový profil a nastavení by se nepoužilo.

Profil se proto naváže na MAC adaptéru (uživatel). Při uložení kabelového
profilu fknm nastaví `802-3-ethernet.mac-address` na trvalou MAC adaptéru
a vymaže `connection.interface-name`. Když adaptér zrovna není zapojený
a MAC tedy není známá, nechá vazbu, jak je. Trvalá MAC je `permaddr` z
`ip -j link`, pokud je nastavená, jinak `address`. Builder ověří, že po
přepojení do jiného portu NetworkManager použije tenhle profil a nový
„Wired connection 2“ nezaloží.

### Záložka Stav (uživatel: má umět i upravovat)

Tři sekce. Dokud je záložka vidět, obnovují se zhruba každé 3 s,
Ctrl+R obnoví hned (návrh).

- **Adresy:** každé rozhraní kromě `lo` (návrh) se stavem (UP, DOWN,
  UNKNOWN), názvem profilu, IPv4 i IPv6 adresami. Rozhraní s profilem
  má „Upravit“ (Ctrl+E), které otevře dialog profilu, který na něm právě
  běží. Rozhraní bez profilu (`tailscale0`, `virbr0`) mají štítek
  „bez profilu“ a jsou jen pro čtení (uživatel).
- **Routy:** výpis podle `ip route` (IPv4 i IPv6, návrh). Každá routa má
  štítek, odkud pochází: `profil`, `DHCP`, `kernel` nebo `bez profilu`.
- **DNS:** servery u každého rozhraní a štítek `profil` nebo `DHCP`. Pod
  nimi řádek s tím, kam míří `/etc/resolv.conf`.

Úpravy ve Stavu se ukládají trvale do profilu, který na rozhraní běží,
a ten se pak znovu použije (uživatel). „+ Přidat“ u Rout a DNS se zeptá na
hodnotu a rozhraní, předvybrané podle vybraného řádku (návrh). ✕ a Delete
jde jen u položek s původem `profil`. DHCP a kernel položky jednotlivě
odebrat nejde, protože NetworkManager je jen přebírá. Vypnout je jde jen
všechny najednou přepínačem „Ignorovat z DHCP“ v dialogu profilu.

Původ položky musí builder spolehlivě určit, třeba porovnáním s
`ipv4.routes` a `ipv4.dns` profilu a s `proto` z `ip -j route`. Kde to
jistě nejde, ✕ se neukáže.

### Dialog profilu (Ctrl+E z Profilů, Stavu i Wi-Fi)

Jeden dialog pro všechny vstupy (uživatel odsouhlasil ukázku `edit.html`):

- **Obecné:** Název, Heslo (jen WPA2/WPA3 wifi; prázdné pole heslo
  nemění), Připojit automaticky (návrh).
- **802.1X** (jen 802.1X wifi): stejná pole jako dialog 802.1X níže.
- **IPv4:** metoda Automaticky (DHCP), Ručně nebo Vypnuto. Při Ručně jsou
  vidět Adresy (seznam `adresa/prefix`, + Přidat, 🗑) a Brána.
- **DNS:** seznam (+ Přidat, 🗑) a přepínač „Ignorovat DNS z DHCP“
  (`ipv4.ignore-auto-dns`). Je vidět i při DHCP.
- **Routy:** řádky `cíl/prefix → brána, metrika` (+ Přidat, 🗑) a přepínač
  „Ignorovat routy z DHCP“ (`ipv4.ignore-auto-routes`). Je vidět i při DHCP.
- Dole „Smazat profil“, po potvrzení.

Uložit zavolá `nmcli connection modify`. Když profil běží, změna se musí
hned projevit (uživatel). Jestli přes `nmcli device reapply` nebo
`nmcli connection up`, je na builderovi. Neplatný vstup (adresa, prefix,
metrika) se označí přímo u pole a Uložit zůstane zakázané. Chyba z nmcli
se ukáže v dialogu, dialog se nezavře a nic se neztratí.

### Dialog 802.1X (nová 802.1X síť)

Otevře ho Enter na nové 802.1X síti ve Wi-Fi záložce nebo v rofi. Tlačítko
v hlavičce je „Připojit“.

- **Přihlášení:** metoda EAP (PEAP, TTLS, TLS), vnitřní ověření (pro PEAP
  a TTLS: MSCHAPv2, PAP, GTC), uživatel (identita), anonymní identita
  (nepovinné), heslo.
- **Ověření serveru:** CA certifikát (výchozí jsou systémové certifikáty,
  jinak soubor) a doména serveru (`domain-suffix-match`). Bez CA nebo bez
  domény se ukáže varování, že falešná síť se stejným názvem může ukrást
  heslo. Připojit jde i tak.
- **Jen pro TLS:** klientský certifikát, soukromý klíč, heslo ke klíči
  (soubory přes výběr souboru).

## Rofi (`fknm-rofi`)

Uživatel odsouhlasil ukázku `rofi.html`. Stavba podle `ssh_wallet/rofi.py`:
`rofi -dmenu -markup-rows -format i`, filtruje se podle prostého textu, na
začátku `pkill -x rofi`, `--system-theme`, vlastní `data/fknm.rasi`.

- Zpráva nahoře: aktuální připojení (zařízení, síť, adresa) a stav
  Tailscale (návrh).
- Řádky: síť, signál, zabezpečení, „Připojeno“ nebo „Uloženo“. Pořadí je
  připojená, uložené, pak ostatní podle signálu. Ukáže se poslední sken,
  takže se na nic nečeká.
- Na konci položky „↻ Skenovat znovu“ (naskenuje a menu otevře znovu,
  návrh) a „Otevřít fknm“.
- Enter:
  - uložená nebo otevřená síť: připojí,
  - nová WPA2/WPA3: druhé rofi s `-password` a promptem „Heslo>“,
  - nová 802.1X: otevře dialog 802.1X v GTK aplikaci (návrh); běží-li
    aplikace, otevře se v jejím okně,
  - síť, která už je připojená: nic se nestane (návrh).
- Chyba se ukáže přes `rofi -e` jako v ssh_wallet. Profil vzniklý při
  nepovedeném připojení k nové síti se smaže. Úspěch se nehlásí, je vidět
  ve waybaru (návrh).

## Instalace a struktura (návrh)

- Kód v `/home/kuba/fknm`, rozvržení jako ssh_wallet: balíček `fknm/`
  (UI v `fknm/ui/`), `bin/fknm` a `bin/fknm-rofi` spouští aplikaci přímo
  z checkoutu, `data/` (rasi, `.desktop.in`), `tests/`, `install.sh`, README.
- App ID `io.github.krupis294.Fknm`.
- `install.sh` udělá symlinky `~/.local/bin/fknm` a `~/.local/bin/fknm-rofi`
  a položku v nabídce aplikací. README ukáže zkratku pro Hyprland, kterou
  si uživatel nastaví sám.
- Testy v `unittest` (`python -m unittest discover -s tests -t .`) jako
  v ssh_wallet. Volání `nmcli` a `ip` jdou přes jednu vrstvu, kterou testy
  nahradí falešnou, takže testy na síti nic nezmění. UI testy se bez
  displeje přeskočí.
- Všechna volání nmcli a ip běží asynchronně (třeba `Gio.Subprocess`),
  aby okno nezamrzlo.

## Na builderovi

- Jak parsovat výstup nmcli (`-t`, escapování `:`), jak sledovat změny
  (polling nebo `nmcli monitor`).
- Jak přesně se projeví změna u běžícího profilu (`reapply` nebo `up`).
- Jak spolehlivě určit původ rout a DNS.
- Který profil se vezme, když má jedna síť víc uložených profilů.
- Rozdělení do modulů a podoba falešného nmcli v testech.
