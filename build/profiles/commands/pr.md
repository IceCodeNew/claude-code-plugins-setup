---
description: Create a pull request for the current branch
argument-hint: "[title]"
disable-model-invocation: true
---
Prepare and create a pull request for the current branch. Use $ARGUMENTS as the
title when provided.

Inspect the branch diff against the default branch, make sure the work is
committed, and run the relevant tests. Push the branch only after the user
approves the push, then create the PR with `gh pr create`. The body should cover:
what changed, why, how it was verified, and any risk or follow-up. Do not merge.

If the branch is not ready (failing tests, missing commit, unrelated changes),
stop and report what is missing instead of opening the PR.
