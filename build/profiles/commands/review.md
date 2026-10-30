---
description: Review the current diff or a path and report findings
argument-hint: "[path or diff range]"
disable-model-invocation: true
---
Review $ARGUMENTS (or the current diff when no argument is given). Read the
changed code, its callers, and the tests before reporting.

Report findings first, ordered by severity. Each finding needs file:line, the
concrete failure scenario, why the code allows it, and a minimal verification
step. Separate confirmed defects from suspicions and say what evidence is
missing. Cover error paths, empty inputs, concurrency, resource cleanup,
injection, authz, secrets, and dependency risk where relevant.

Do not rewrite the code unless the user asks for a fix. Do not invent a finding
to fill the report. Finish with a verdict: approve, changes needed, or blocked.
