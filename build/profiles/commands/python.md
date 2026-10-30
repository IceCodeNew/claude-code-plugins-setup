---
description: Python conventions for this repository
argument-hint: "[path]"
disable-model-invocation: true
---
Work on the Python code in $ARGUMENTS using this repository's conventions.

Use `uv` for environments and dependencies; do not run `pip install` or create a
bare venv unless the repository already does. Use `ruff` for lint/format and
`ty`/`pyright` for types when available. Prefer the standard library and the
project's existing patterns over new dependencies. Add tests with `pytest` that
assert behavior, not implementation details.

Check the repository's `pyproject.toml` for the supported Python version, lint
rules, and test command before editing. Run the narrowest test and lint command,
then report the exact commands and results.
