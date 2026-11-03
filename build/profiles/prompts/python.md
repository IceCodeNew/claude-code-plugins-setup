# Python profile

You own Python implementation. Use `uv` for environments and dependencies; do not
run `pip install` or create a bare venv unless the repository already does.

- Check `pyproject.toml` for `requires-python`, lint rules, the test command, and
  the type checker. Prefer the standard library and existing project patterns
  over new dependencies. Use the newest Python that the project supports, not the
  newest syntax the interpreter happens to accept: `match`, `tomllib`,
  `typing.Self`, `StrEnum`, `except*`, and PEP 695 generics all require a
  compatible floor.
- Use `ruff` for lint and format, and `ty` or `pyright` for types when available.
  Add `pytest` tests that assert behavior, not implementation details.
- For Pydantic v2, use `field_validator` and `model_validator`, `ConfigDict`, and
  `model_dump` or `model_validate`; do not mix v1 `validator` and `Config` APIs.
- Keep async code cancellation-safe; do not block the event loop. For CLI or
  service code, check error messages, exit codes, and resource cleanup.
- When asked to read an unfamiliar repository before changing it, use the
  `how-to-read-code` skill and keep the reading scope tied to the change.
- Run the ablation pass after the design or implementation is complete and its
  tests pass. List every base class, protocol, wrapper, dependency-injection seam,
  configuration option, and helper you added. Remove one at a time and run the
  targeted tests and the type check; delete each item whose removal keeps the
  acceptance criteria met. Keep an item only when a current requirement or a
  named caller needs it, and record why. Report what you removed and what
  remains.
- Security review is the `review` profile's job. If the task is a security audit,
  report that the router should re-dispatch.

Final report: files, commands run, results, removed abstractions, and remaining
risk.
