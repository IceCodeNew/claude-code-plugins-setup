---
description: Simplify the current change without changing behavior
argument-hint: "[path or diff range]"
disable-model-invocation: true
---
Simplify the code in $ARGUMENTS (or the current diff when no argument is given).

Work from the actual diff and the surrounding code. Look for duplicated logic,
unnecessary abstraction, dead branches, over-general types, and names that do not
match the behavior. Keep the public behavior and the existing tests intact.

Make the smallest coherent edit. Do not reformat unrelated code, rename public
APIs, or add dependencies. Run the narrowest test that proves the behavior, then
report: what you removed or merged, why it is safe, the verification command, and
anything you deliberately left alone.
