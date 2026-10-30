---
description: Run the mandatory review stages and report findings
argument-hint: "[diff range, path, or PR number/URL]"
disable-model-invocation: true
---
Review $ARGUMENTS (or the current diff when no argument is given).

If the argument is a PR number or URL, fetch metadata and diff with `gh pr view`
and `gh pr diff`. Otherwise read the changed code, its callers, and the tests.

Assume the code is already stable: simplification (`code-simplifier` plus
`reclaim-code-entropy`) belongs to the dev stabilization stage, before review.
Do not start a simplification pass here.

## Mandatory stages

1. **Standard review checks.** Run `test-audit` and `ripwire` where they apply.
   Do not skip one silently; if it does not apply, say why.
2. **Security check.** After the standard checks, read
   `~/.claude/commands/security-check.md` and follow it. It is read-only.
3. **False-positive verification.** Use `fp-check` on every security finding
   that needs confirmation.

## Optional / user-triggered

- `rust-review` is optional and only when the change is Rust.
- `code-review-page` is artifact-only; run it when the user asks for an HTML
  review page.
- `thermos` / `thermo-nuclear-*` are **not** part of this command. They are
  expensive and must be triggered by the user separately.

## Output

Report findings first, ordered by severity. Each finding needs file:line, the
concrete failure scenario, why the code allows it, and a minimal verification
step. Separate confirmed defects from suspicions and say what evidence is
missing. Finish with a verdict: approve, changes needed, or blocked.
