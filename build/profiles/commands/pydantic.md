---
description: Pydantic v2 patterns for this repository
argument-hint: "[path]"
disable-model-invocation: true
---
Work on the Pydantic models in $ARGUMENTS.

Check the installed Pydantic version first. For v2, use `field_validator` /
`model_validator`, `ConfigDict`, `Field`, and `model_dump` / `model_validate`;
do not mix v1 `validator`/`Config` APIs into v2 code. Prefer explicit types and
constraints over validators that reimplement them. For settings, use
`pydantic-settings` only when the repository already depends on it. Keep
serialization stable for API models and add tests for invalid input.

Run the repository's type checker and the narrowest test; report the exact
commands and any compatibility risk.
