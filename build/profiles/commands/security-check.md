---
description: Security review of the current diff or path
argument-hint: "[path or diff range]"
disable-model-invocation: true
---
Perform a security review of $ARGUMENTS (or the current diff).

Build a trust-boundary map first: sources of attacker-controlled data, the paths
they take, the sinks, and the validation in between. Check injection (SQL, shell,
template, header), authz and tenant isolation, SSRF, deserialization, path
traversal, secrets, unsafe defaults, and dependency/supply-chain risk.

For each candidate finding, try to disprove it: check the framework's built-in
protection, the environment, and whether the attacker controls the input. Report
only findings with a concrete scenario and file:line; mark unverified items as
suspicions. If the review profile has the `fp-check` skill, use it for a security
finding that needs formal false-positive verification.

Do not patch unless asked. End with severity, evidence, and residual risk.
