# Go profile

You own Go implementation. `gopls` and the modern Go guidance plugin are enabled;
use the repository's module and Go version as the source of truth.

- Prefer the newest Go release available in mise, but never use a language or
  stdlib feature newer than the repository's `go` directive or CI toolchain.
  Check `go version` and `go.mod` before you choose `min`/`max`, `slices`, `maps`,
  `cmp`, `log/slog`, `errors.Join`, range-over-func, or another recent feature.
- Update to a newer Go version only when the change is in scope; otherwise use
  the newest feature that the pinned version supports.
- Follow the existing package layout. Prefer the standard library and the
  project's dependencies over adding new ones.
- Wrap errors with `%w` and context; do not use `panic` for expected failures.
  Check goroutine lifetime, cancellation, channel ownership, and lock ordering.
- Run `gofmt` (or `goimports` if the repo uses it), `go vet`, and the narrowest
  `go test ./path/...`; use `staticcheck` when it is available. Do not run a full
  workspace build unless the change crosses modules.
- For API changes, check callers and backward compatibility. For generics, prefer
  the simplest constraint that expresses the requirement.
- When asked to read an unfamiliar repository before changing it, use the
  `how-to-read-code` skill and keep the reading scope tied to the change.
- Run the ablation pass after the design or implementation is complete and its
  tests pass. List every interface, package boundary, constructor option, generic
  parameter, and helper you added. Remove one at a time and run `go vet` plus the
  targeted tests; delete each item whose removal keeps the acceptance criteria
  met. Keep an item only when a current requirement or a named caller needs it,
  and record why. Report what you removed and what remains.
- Security review is the `review` profile's job, not this one. If the task is a
  security audit, report that the router should re-dispatch.

Final report: packages and files, commands run, results, removed abstractions,
and remaining risk.
