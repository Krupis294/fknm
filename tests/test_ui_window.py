"""Smoke tests of the main window. They need a display, so they skip without one."""

import unittest

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from tests import fixtures  # noqa: E402
from tests.fakes import sync_background  # noqa: E402

HAS_DISPLAY = Gtk.init_check()
if HAS_DISPLAY:
    Adw.init()


@unittest.skipUnless(HAS_DISPLAY, "needs a display")
class MainWindowTest(unittest.TestCase):
    def setUp(self):
        from fknm.ui.window import MainWindow

        self.runner = fixtures.standard_runner()
        self.window = MainWindow(runner=self.runner, background=sync_background, pages=False)
        self.addCleanup(self.window.destroy)

    def test_tabs_and_titles(self):
        pages = self.window.view_stack.get_pages()
        titles = [pages.get_item(i).get_title() for i in range(pages.get_n_items())]
        names = [pages.get_item(i).get_name() for i in range(pages.get_n_items())]

        self.assertEqual(titles, ["Wi-Fi", "Profily", "Stav"])
        self.assertEqual(names, ["wifi", "profiles", "status"])

    def test_tab_actions_switch_pages(self):
        self.window.activate_action("win.tab-3", None)
        self.assertEqual(self.window.view_stack.get_visible_child_name(), "status")

    def test_tailscale_indicator(self):
        self.runner.respond(["ip", "-j", "addr"], fixtures.ADDR_TAILSCALE_WITH_INET)
        self.window.refresh_tailscale()

        label = self.window.tailscale_label
        self.assertEqual(label.get_text(), "● tailscale")
        self.assertTrue(label.has_css_class("on"))
        self.assertEqual(label.get_tooltip_text(), "Tailscale běží")

        self.runner.respond(["ip", "-j", "addr"], "[]")
        self.window.refresh_tailscale()
        self.assertTrue(label.has_css_class("off"))
        self.assertFalse(label.has_css_class("on"))
        self.assertEqual(label.get_tooltip_text(), "Tailscale neběží")

    def test_background_error_does_not_crash_indicator(self):
        self.runner.respond(["ip", "-j", "addr"], returncode=1, stderr="boom")

        self.window.refresh_tailscale()

        self.assertTrue(self.window.tailscale_label.has_css_class("off"))
        self.assertIsNone(self.window.last_toast)

    def test_app_style_wins_over_user_theme(self):
        # ~/.config/gtk-4.0/gtk.css loads at USER priority with its own @define-color palette.
        from fknm.ui.style import apply_style

        apply_style()
        window = Gtk.Window()
        self.addCleanup(window.destroy)
        color = window.get_color()

        self.assertEqual([round(c * 255) for c in (color.red, color.green, color.blue)], [0xdd, 0xdd, 0xdd])

    def test_view_switcher_shows_labels_only(self):
        switcher = self.window.view_switcher
        self.assertIsInstance(switcher, Adw.InlineViewSwitcher)
        self.assertEqual(switcher.get_display_mode(), Adw.InlineViewSwitcherDisplayMode.LABELS)

    def test_toast_is_remembered(self):
        self.window.toast("Uloženo.")
        self.assertEqual(self.window.last_toast, "Uloženo.")
