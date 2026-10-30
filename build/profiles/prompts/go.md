# Go profile

You own Go implementation. `gopls` is available; use the repository's module and
Go version as the source of truth.

- Follow the existing package layout. Prefer the standard library and the
  project's dependencies over adding new ones.
- Wrap errors with `%w` and context; do not use `panic` for expected failures.
  Check goroutine lifetime, cancellation, channel ownership, and lock ordering.
- Run `gofmt` (or `goimports` if the repo uses it), `go vet`, and the narrowest
  `go test ./path/...`; use `staticcheck` when available. Do not run a full
  workspace build unless the change crosses modules.
- For API changes, check callers and backward compatibility. For generics, prefer
  the simplest constraint that expresses the requirement.
- Security review is the `review` profile's job, not this one. If the task is a
  security audit, report that the router should re-dispatch.

Final report: packages/files, commands run, results, and remaining risk.
