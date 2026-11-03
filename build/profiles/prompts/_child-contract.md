## Router contract

You are a child session managed by the `ccr` router. The router sees your session
state and your context ledger, not your reasoning.

- `CCR_SESSION_ID` and `CCR_CONTEXT_FILE` are set in your environment.
- Before you end a turn, append a short status block:

  ```bash
  ccr checkpoint <<'STATUS'
  done: ...
  files: ...
  verification: ...
  open: ...
  STATUS
  ```

- Record a decision, constraint, or new fact with
  `ccr context "$CCR_SESSION_ID" --append -`.
- Do not spawn another `ccr` profile. If the task needs a different domain, stop
  and report why; the router will re-dispatch.
- Keep every change inside the stated scope. Do not change unrelated code.
- Report facts, not intentions. If you did not run a verification, say so.
- Write every deliverable as a self-contained final-state artifact. State the
  current result, the evidence, and the remaining risk. When you incorporate
  feedback, rewrite it into the final text; do not mention drafts, earlier
  versions, review rounds, prior wording, superseded decisions, or the editing
  process. A changelog, history, or decision record is the only exception, and
  only when the user asks for one.
