"""Running nmcli off the GTK main thread, so the window never freezes."""

import threading
from collections.abc import Callable
from typing import Any

from gi.repository import GLib

# background(fn, on_done): runs fn() elsewhere, then on_done(result, None) or on_done(None, error)
# back on the main thread. Tests swap in a synchronous one.
Background = Callable[[Callable[[], Any], Callable[[Any, Exception | None], None]], None]


def run_in_background(fn: Callable[[], Any], on_done: Callable[[Any, Exception | None], None]) -> None:
    def work():
        try:
            result, error = fn(), None
        except Exception as e:  # noqa: BLE001 - every failure is reported to on_done
            result, error = None, e
        GLib.idle_add(lambda: on_done(result, error) and False)

    threading.Thread(target=work, daemon=True).start()
