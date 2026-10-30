---
description: Run the mandatory review stages and report findings
argument-hint: "[diff range, path, or PR number/URL]"
disable-model-invocation: true
---
Review $ARGUMENTS (or the current diff when no argument is given).

If the argument is a PR number or URL, fetch metadata and diff with `gh pr view`
and `gh pr diff`. Otherwise read the changed code, its callers, and the tests.

## Mandatory stages

Invoke `/security-check` and `/simplify` as mandatory sub-commands. If this session
cannot nest slash commands, read their command files and execute the bodies; do
not skip them or merely mention them.

1. **Security check.** Read `~/.claude/commands/security-check.md` and follow it
   as a required stage. It is read-only.
2. **Standard review checks.** Run the review profile's remaining checks:
   `test-audit`, `reclaim-code-entropy`, and `ripwire` where they apply. Do not
   skip one silently; if it does not apply, say why.
3. **False-positive verification.** Use `fp-check` on every security finding
   that needs confirmation.
4. **Simplify.** Read `~/.claude/commands/simplify.md` and follow it as a
   required stage. This is the only stage allowed to edit code. Run it after the
   read-only stages, then re-run the tests and re-check the diff.

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
missing. After `simplify`, report what changed and which tests were re-run.
Finish with a verdict: approve, changes needed, or blocked.
