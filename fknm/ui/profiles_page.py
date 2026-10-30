"""Profily tab: saved wifi and ethernet profiles; switch on and off, edit, delete."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from fknm.model import Profile, ProfileSettings  # noqa: E402
from fknm.profiles import (  # noqa: E402
    activate, deactivate, delete, ethernet_state, list_profiles, profile_subtitle, read_settings,
)
from fknm.ui.list_page import ListPage, badge, row_button  # noqa: E402


class ProfileRow(Adw.ActionRow):
    def __init__(self, profile: Profile, settings: ProfileSettings, eth_state: str | None, page: "ProfilesPage"):
        super().__init__(title=profile.name, subtitle=profile_subtitle(profile, settings, eth_state),
                         use_markup=False, activatable=True)
        self.item = profile
        self.settings = settings
        self.add_suffix(badge("Wi-Fi" if profile.kind == "wifi" else "Kabel"))
        if profile.active:
            self.add_suffix(badge("Aktivní", ok=True))
        if settings.ipv4.method == "manual":
            self.add_suffix(badge("Ručně", tooltip="Ruční IP adresa"))
        self.add_suffix(row_button("Upravit", lambda: page.edit(profile), "Ctrl+E"))
        self.add_suffix(row_button("Vypnout" if profile.active else "Zapnout", lambda: page.toggle(profile), "Enter",
                                   connect=not profile.active))


class ProfilesPage(ListPage):
    def __init__(self, window):
        self.window = window
        self._settings: dict[str, ProfileSettings] = {}
        pages = {
            "empty": Adw.StatusPage(title="Žádné profily", description="Profil vznikne připojením k síti."),
            "no-results": Adw.StatusPage(title="Nic nenalezeno", description="Esc vymaže hledání."),
        }
        super().__init__("Hledat profil", lambda p, q: q.lower() in p.name.lower(), self.toggle, pages,
                         on_delete=self.confirm_delete)

    # -- page interface ---------------------------------------------------------

    def refresh(self) -> None:
        runner = self.window.runner

        def load():
            profiles = list_profiles(runner)
            settings = {p.uuid: read_settings(runner, p.uuid) for p in profiles}
            return profiles, settings, ethernet_state(runner)

        def loaded(result, error):
            if error:
                self.window.toast(f"Profily nejde načíst: {error}", timeout=6)
                return
            profiles, self._settings, eth_state = result
            profiles.sort(key=lambda p: (not p.active, -p.timestamp))
            selected = self.selected_item()
            self.set_rows([ProfileRow(p, self._settings[p.uuid], eth_state, self) for p in profiles],
                          select=lambda p: selected is not None and p.uuid == selected.uuid)

        self.window.background(load, loaded)

    def set_live(self, visible: bool) -> None:
        if visible:
            self.refresh()

    def refresh_shortcut(self) -> None:
        self.refresh()

    def hints(self) -> list[tuple[str, str]]:
        return [("Enter", "Zapnout/Vypnout"), ("Ctrl+E", "Upravit"), ("Delete", "Smazat"), ("Ctrl+1/2/3", "Záložky")]

    def visible_profiles(self) -> list[Profile]:
        return self.visible_items()

    def toggle_selected(self) -> None:
        self.activate_selected()

    def edit_selected(self) -> None:
        if profile := self.selected_item():
            self.edit(profile)

    def delete_selected(self) -> None:
        if profile := self.selected_item():
            self.confirm_delete(profile)

    # -- actions ----------------------------------------------------------------

    def toggle(self, profile: Profile) -> None:
        runner = self.window.runner
        if profile.active:
            self.window.run_action(lambda: deactivate(runner, profile.uuid), f"{profile.name} vypnut.",
                                   error_prefix=f"Nejde vypnout {profile.name}: ")
        else:
            self.window.toast(f"Připojuji k {profile.name}…")
            self.window.run_action(lambda: activate(runner, profile.uuid), f"{profile.name} zapnut.",
                                   error_prefix=f"Nepřipojeno k {profile.name}: ")

    def edit(self, profile: Profile) -> None:
        settings = self._settings.get(profile.uuid)
        self.window.open_profile(profile.uuid, profile.device or (settings.interface_name if settings else ""))

    def confirm_delete(self, profile: Profile) -> None:
        dialog = Adw.AlertDialog(heading=f"Smazat {profile.name}?", body="Profil bude odstraněn z NetworkManageru.")
        dialog.add_response("cancel", "Zrušit")
        dialog.add_response("delete", "Smazat")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, response: response == "delete" and self._delete(profile))
        dialog.present(self.window)

    def _delete(self, profile: Profile) -> None:
        self.window.run_action(lambda: delete(self.window.runner, profile.uuid), f"{profile.name} smazán.")
