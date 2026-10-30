---
description: Review a diff, path, or pull request and report findings
argument-hint: "[diff range, path, or PR number/URL]"
disable-model-invocation: true
---
Review $ARGUMENTS (or the current diff when no argument is given).

If the argument is a PR number or URL, fetch metadata and diff with `gh pr view`
and `gh pr diff`. Otherwise read the changed code, its callers, and the tests.

Use the review profile's specialized skills instead of re-implementing their
multi-agent or confidence logic: `thermos` for a combined bug/security and
code-quality pass, `rust-review` for Rust, `/security-check` for a security-only
review, and `fp-check` when a security finding needs false-positive verification.
This command owns the output contract, not another review engine.

Report findings first, ordered by severity. Each finding needs file:line, the
concrete failure scenario, why the code allows it, and a minimal verification
step. Separate confirmed defects from suspicions and say what evidence is
missing. Do not rewrite the code unless the user asks. Finish with a verdict:
approve, changes needed, or blocked.
