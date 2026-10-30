---
description: Go conventions for this repository
argument-hint: "[path]"
disable-model-invocation: true
---
Work on the Go code in $ARGUMENTS using this repository's conventions.

Check `go.mod` for the module and Go version. Prefer the standard library and the
project's existing package layout. Run `gofmt` (or `goimports` if the repo uses
it), `go vet`, and the package tests; use `staticcheck` when it is available.
For errors, wrap with `%w` and keep context; do not use `panic` for expected
failures. For concurrency, check goroutine lifetime, cancellation, and channel
ownership.

Run the narrowest `go test ./path/...` first, then the broader suite if needed.
Report the commands and results.
