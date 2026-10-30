"""Test doubles for running commands and for running work in the background."""

from fknm.nmcli import Result


class FakeRunner:
    """Answers commands by argv prefix and records every call.

    The longest matching prefix wins; a later ``respond`` with the same prefix
    replaces the earlier one. A command without an answer fails the test.
    """

    def __init__(self):
        self.calls: list[tuple[list[str], str | None]] = []
        self._responses: dict[tuple[str, ...], Result] = {}

    def respond(self, prefix: list[str], stdout: str = "", returncode: int = 0, stderr: str = "") -> None:
        self._responses[tuple(prefix)] = Result(returncode, stdout, stderr)

    def __call__(self, argv: list[str], stdin: str | None = None) -> Result:
        self.calls.append((list(argv), stdin))
        matches = [p for p in self._responses if tuple(argv[:len(p)]) == p]
        if not matches:
            raise AssertionError(f"unexpected command: {argv}")
        return self._responses[max(matches, key=len)]

    def argvs(self) -> list[list[str]]:
        return [argv for argv, _stdin in self.calls]


def sync_background(fn, on_done) -> None:
    """Background stand-in that runs ``fn`` right away."""
    try:
        result = fn()
    except Exception as e:  # noqa: BLE001 - handed to on_done like the real one
        on_done(None, e)
        return
    on_done(result, None)
