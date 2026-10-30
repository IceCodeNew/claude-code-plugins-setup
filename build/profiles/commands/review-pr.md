---
description: Review a pull request
argument-hint: "<PR number or URL>"
disable-model-invocation: true
---
Review pull request $ARGUMENTS.

Fetch the metadata and diff with `gh pr view` and `gh pr diff`. Read the changed
code, its tests, and the surrounding code. Check the PR description against what
the diff actually does.

Report findings ordered by severity with file:line and a concrete failure
scenario. Pay attention to tests that do not assert behavior, error handling,
type design, API compatibility, migrations, and security-sensitive changes.
Run the relevant tests locally when the repository allows it; otherwise say
exactly what you could not run.

Do not push, merge, or edit the PR unless the user asks. End with a verdict and
the checks you ran.
