"""Provision the personal web account without secrets in arguments or environment.

This synchronous installer helper never starts the bridge or contacts hardware.
Existing accounts are preserved. The three prompts share one 180-second deadline.
"""

from __future__ import annotations

import argparse
import codecs
import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

SETUP_TIMEOUT_SECONDS = 180.0


class InputDeadlineExpired(Exception):
    """The shared setup deadline elapsed or interactive input is unavailable."""


@contextmanager
def _terminal_input(stream: TextIO) -> Iterator[None]:
    """Restore POSIX terminal settings even when setup is interrupted."""
    if sys.platform == "win32":
        yield
        return
    import termios
    import tty

    descriptor = stream.fileno()
    previous = termios.tcgetattr(descriptor)
    try:
        tty.setcbreak(descriptor)
        yield
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)


def _read_character(stream: TextIO, deadline: float) -> str:
    """Wait at most the remaining shared deadline for a terminal character."""
    if sys.platform == "win32":
        import msvcrt

        while time.monotonic() < deadline:
            if msvcrt.kbhit():
                character = msvcrt.getwch()
                if character in {"\x00", "\xe0"}:
                    # Discard the second character of a Windows navigation key.
                    msvcrt.getwch()
                    continue
                return character
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        raise InputDeadlineExpired

    import select

    remaining = deadline - time.monotonic()
    if remaining <= 0 or not select.select([stream], [], [], remaining)[0]:
        raise InputDeadlineExpired
    raw = os.read(stream.fileno(), 1)
    if not raw:
        raise InputDeadlineExpired
    # Preserve UTF-8 byte sequences until the complete input is available.
    return raw.decode("latin-1")


def _read_value(stream: TextIO, prompt: str, deadline: float, *, hidden: bool) -> str:
    sys.stdout.write(prompt)
    sys.stdout.flush()
    characters: list[str] = []
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    while True:
        character = _read_character(stream, deadline)
        if sys.platform != "win32":
            character = decoder.decode(character.encode("latin-1"))
            if not character:
                continue
        if character == "\x03":
            raise KeyboardInterrupt
        if character == "\x04":
            raise InputDeadlineExpired
        if character in {"\r", "\n"}:
            sys.stdout.write("\n")
            sys.stdout.flush()
            return "".join(characters)
        if character in {"\x08", "\x7f"}:
            if characters:
                characters.pop()
                if not hidden:
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            continue
        if ord(character) < 32:
            continue
        # Bound memory while still rejecting oversized input in backend validation.
        if len(characters) >= 2048:
            continue
        characters.append(character)
        if not hidden:
            sys.stdout.write(character)
            sys.stdout.flush()


def _prompt_credentials() -> tuple[str, str] | None:
    from src.web.auth_store import validate_credentials

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("Interactive input is unavailable; use the default account.")
        return None
    print("Create your personal web account. You have 3 minutes for all prompts.")
    print("Password: 15-128 characters. Password input is hidden.")
    deadline = time.monotonic() + SETUP_TIMEOUT_SECONDS
    try:
        with _terminal_input(sys.stdin):
            while time.monotonic() < deadline:
                username = _read_value(sys.stdin, "Username: ", deadline, hidden=False)
                password = _read_value(sys.stdin, "Password: ", deadline, hidden=True)
                confirmation = _read_value(sys.stdin, "Confirm password: ", deadline, hidden=True)
                if password != confirmation:
                    print("Passwords do not match. Try again within the original deadline.")
                    continue
                try:
                    validate_credentials(username, password)
                except ValueError:
                    print(
                        "Use a username of 1-64 letters, digits, '.', '_' or '-' and a password of 15-128 characters."
                    )
                    continue
                return username, password
    except InputDeadlineExpired:
        print("\nCredential input was not completed; use the default account.")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Installed project directory containing config.py and src/",
    )
    arguments = parser.parse_args()
    project_dir = arguments.project_dir.resolve()
    if not (project_dir / "config.py").is_file() or not (project_dir / "src").is_dir():
        parser.error("The project directory must contain config.py and src/.")
    os.chdir(project_dir)
    sys.path.insert(0, str(project_dir))
    # Resolve the same .env, DATA_DIR and DATABASE_PATH used by the installed bridge.
    import config
    from src.web.auth_store import AuthStore

    store = AuthStore(Path(config.DATABASE_PATH))
    store.initialize()
    if store.has_account():
        print("Existing web account preserved. Change credentials in the web account view.")
        return 0
    credentials = _prompt_credentials()
    if credentials is None:
        created = store.bootstrap_default()
        if created:
            print(
                "Default account admin:admin created. Change credentials after first login before station access."
            )
    else:
        created = store.bootstrap(*credentials)
        if created:
            print("Personal web account created. Credentials are stored only as a password hash.")
    if not created:
        print("An account was created concurrently; its credentials were preserved.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nAccount setup cancelled.", file=sys.stderr)
        raise SystemExit(130) from None
    except Exception:
        # Do not reveal configuration or credential data in installer error output.
        print(
            "Account setup failed. Check database permissions and configuration.", file=sys.stderr
        )
        raise SystemExit(1) from None
