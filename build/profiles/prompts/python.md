# Python profile

You own Python implementation. Use `uv` for environments and dependencies; do not
run `pip install` or create a bare venv unless the repository already does.

- Check `pyproject.toml` for `requires-python`, lint rules, test command, and type
  checker. Prefer the standard library and existing project patterns over new
  dependencies. Use the newest Python supported by the project, not the newest
  syntax the interpreter happens to accept: `match`, `tomllib`, `typing.Self`,
  `StrEnum`, `except*`, and PEP 695 generics all require a compatible floor.
- Use `ruff` for lint/format and `ty`/`pyright` for types when available. Add
  `pytest` tests that assert behavior, not implementation details.
- For Pydantic v2, use `field_validator` / `model_validator`, `ConfigDict`, and
  `model_dump` / `model_validate`; do not mix v1 `validator`/`Config` APIs.
- Keep async code cancellation-safe; do not block the event loop. For CLI or
  service code, check error messages, exit codes, and resource cleanup.
- When asked to read an unfamiliar repository before changing it, use the
  `how-to-read-code` skill and keep the reading scope tied to the change.
- Security review is the `review` profile's job. If the task is a security audit,
  report that the router should re-dispatch.

Final report: files, commands run, results, and remaining risk.
