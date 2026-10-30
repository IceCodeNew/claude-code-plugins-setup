---
description: Create a focused commit for the current changes
argument-hint: "[message]"
disable-model-invocation: true
---
Create a commit for the current changes. Use $ARGUMENTS as the message when it is
provided; otherwise write one.

First inspect `git status` and `git diff` (including staged and untracked files).
Group the changes into one logical commit; if the worktree contains unrelated
changes, stage only the files that belong to this change and say what you left
out. Follow the repository's commit style. Do not push.

Run the repository's pre-commit hook if it has one. If a hook changes files, rerun
it until it passes. Report the commit hash, the files included, and the
verification you ran.
