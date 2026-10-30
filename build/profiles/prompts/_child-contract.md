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

- Append a decision, constraint, or newly discovered fact with
  `ccr context --append -`.
- Do not spawn other `ccr` profiles. If the task needs a different domain, stop and
  report why; the router will re-dispatch.
- Keep changes inside the stated scope. Do not change unrelated code.
- Report facts, not intentions. If you did not run a verification, say so.
