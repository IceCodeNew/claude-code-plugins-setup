---
description: Audit and improve CLAUDE.md files
argument-hint: "[path]"
disable-model-invocation: true
---
Audit the CLAUDE.md files for $ARGUMENTS (or the repository root).

Read the existing CLAUDE.md and the code it describes. Remove content Claude can
derive from the codebase, duplicated instructions, stale commands, and rules that
no longer match the repository. Keep the commands, conventions, gotchas, and
verification steps that are not obvious from the code.

Keep the file short and scannable. Put task-specific procedures in skills, not in
CLAUDE.md. Show the proposed diff before applying it, then apply only after the
user agrees. Report what you removed and why.
