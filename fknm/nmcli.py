"""Running nmcli and ip, and parsing nmcli's terse output.

Every command goes through a ``Runner`` so tests can replace it. The real one
forces ``LC_ALL=C``: the parsers and error mapping expect English output.
"""

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str], str | None], Result]


class NmcliError(Exception):
    """A failed command; ``str()`` is a Czech message for the user."""


def run_command(argv: list[str], stdin: str | None = None) -> Result:
    try:
        done = subprocess.run(argv, input=stdin, capture_output=True, text=True,
                              env={**os.environ, "LC_ALL": "C"})
    except OSError as e:
        return Result(127, "", str(e))
    return Result(done.returncode, done.stdout, done.stderr)


def nmcli(runner: Runner, args: list[str], stdin: str | None = None) -> str:
    result = runner(["nmcli", *args], stdin)
    if result.returncode != 0:
        raise NmcliError(friendly_error(result.stderr))
    return result.stdout


# Substrings of nmcli errors that have a shorter Czech explanation.
_KNOWN_ERRORS = [
    ("Secrets were required", "špatné heslo"),
    ("No network with SSID", "síť není v dosahu"),
    ("No suitable device", "zařízení není k dispozici (kabel nebo adaptér nezapojen?)"),
]


def friendly_error(stderr: str) -> str:
    message = stderr.strip()
    for prefix in ("Error: ", "Connection activation failed: "):
        message = message.removeprefix(prefix)
    for needle, explanation in _KNOWN_ERRORS:
        if needle in message:
            return explanation
    return message or "nmcli selhal"


def split_terse(line: str) -> list[str]:
    """Split a ``nmcli -t`` line on ``:``, honouring the ``\\:`` and ``\\\\`` escapes."""
    fields, current, chars = [], [], iter(line)
    for char in chars:
        if char == "\\":
            current.append(next(chars, ""))
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    fields.append("".join(current))
    return fields


def parse_fields(text: str) -> dict[str, str]:
    """``key:value`` lines of ``nmcli -t -f ... connection show``; values are not escaped there."""
    fields = {}
    for line in text.splitlines():
        if line:
            key, _, value = line.partition(":")
            fields[key] = value
    return fields
