---
description: Remove local branches whose remote was deleted
disable-model-invocation: true
---
Remove local branches marked `[gone]`.

1. Run `git branch -v` and `git worktree list`. Treat a `+` prefix as a branch
   checked out in a worktree.
2. For each `[gone]` branch, remove its worktree first with
   `git worktree remove --force <path>`, but never remove the current worktree.
3. Delete the branch with `git branch -D <name>`.
4. Report the worktrees and branches removed; if nothing is `[gone]`, say so.

Do not touch branches that still have a remote, the current branch, or a worktree
whose path is the repository root.
