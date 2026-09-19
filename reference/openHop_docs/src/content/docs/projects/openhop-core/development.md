---
title: Core Development
description: Set up, test, format, and validate changes to openHop Core.
sidebar:
  order: 14
---

## Development setup

Use Python 3.10 through 3.13 in a virtual environment:

```bash
git clone https://github.com/openhop-dev/openhop_core.git
cd openhop_core
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pip install pre-commit
pre-commit install
```

For a test-only environment without the formatting and contributor tools:

```bash
python -m pip install -e ".[test]"
```

The repository has no dependency lockfile. Record the Python and dependency
versions when investigating version-sensitive behavior.

## Tests

Run the complete suite without connecting hardware:

```bash
python -m pytest --tb=short -v
```

Use a focused file while developing, then run the full suite:

```bash
python -m pytest tests/test_packet.py --tb=short -v
python -m pytest tests/test_dispatcher.py --tb=short -v
```

Tests under `tests/hardware/` may still mock hardware-adjacent logic. Read a test
before assuming it needs a physical radio.

## Formatting and linting

The repository's contributor gate is:

```bash
pre-commit run --all-files
```

Pre-commit can rewrite files. It runs whitespace and YAML checks, Black, isort,
flake8, and the repository's full pytest gate. Review all changes and still run
focused tests while developing so failures remain easy to isolate.
Mypy is installed as a development dependency but is not a configured project gate.

## Compatibility rules

- Keep protocol bytes compatible with MeshCore firmware.
- Use independent firmware byte vectors for packet-format changes.
- Preserve serialized radio transmission, acknowledgement cleanup, cancellation,
  callbacks, and async behavior.
- Public code remains compatible with Python 3.10.
- A successful radio `send()` returns a metadata mapping; only failure returns
  `None`.
- The caller owns radio shutdown after stopping `MeshNode`.
- Never use hardware examples as unattended smoke tests.

## Track development by commit

Track development through the
[`dev` commit history](https://github.com/openhop-dev/openhop_core/commits/dev/) or
[`main` commit history](https://github.com/openhop-dev/openhop_core/commits/main/).
A branch name moves, so record the exact commit when testing or reporting behavior:

```bash
git branch --show-current
git rev-parse HEAD
git log --oneline CURRENT_COMMIT..origin/dev
```

Replace `CURRENT_COMMIT` with the previously recorded revision and use
`origin/main` when that is the intended branch. Review actual source and test changes;
commit subjects are an index, not a compatibility guarantee.

Package publication automation can run from a published GitHub Release or by
manual workflow dispatch. A release or package version still does not replace
recording the exact source commit used for development and hardware validation.

## Before opening a change

1. Add or update focused tests.
2. Run the focused tests and full test suite.
3. Run pre-commit and review any rewrites.
4. Check the diff for generated files, identities, tokens, device paths, and other
   local artifacts.
