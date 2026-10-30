---
description: Create a Claude Code hook for a stated rule
argument-hint: "<rule or behavior to enforce>"
disable-model-invocation: true
---
Create a Claude Code hook for this rule: $ARGUMENTS

Decide the correct event and matcher. Prefer a deterministic command hook over a
prompt hook; a prompt hook costs a model call on every matching event. Write the
hook to read JSON from stdin and emit the documented `hookSpecificOutput` shape.
Fail closed only when the operation cannot be checked safely; otherwise let the
operation proceed.

Add the hook to the appropriate settings file, test it with a realistic payload,
and show the user the exact command and the event it runs on. Avoid adding a hook
to the user's global settings when the rule is project-specific.
