---
description: Simplify recently changed code without changing behavior
argument-hint: "[files or diff range]"
disable-model-invocation: true
---
Simplify the recently changed code in $ARGUMENTS (or the current diff).

Preserve behavior exactly. Follow the repository's CLAUDE.md and existing style,
not generic preferences. Reduce nesting and redundant abstraction; improve names;
consolidate related logic; remove comments that only restate the code. Prefer
explicit, readable code over clever one-liners. Avoid nested ternaries; use a
switch or early returns for multiple conditions. Do not combine unrelated
concerns, remove useful abstractions, or trade clarity for fewer lines.

Read the diff first, make the smallest coherent edit, then run the relevant tests
and typecheck. If the simplification would change behavior or public API, stop and
report instead. Do not reformat untouched files.
