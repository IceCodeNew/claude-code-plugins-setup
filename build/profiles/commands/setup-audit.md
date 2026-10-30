---
description: Audit this repository's Claude Code setup
argument-hint: ""
disable-model-invocation: true
---
Audit the Claude Code setup for this repository: hooks, skills, MCP servers,
subagents, permissions, and CLAUDE.md.

Look for customizations that are unused, duplicated, too broad, or that run on
every prompt/tool call without earning their cost. Check whether hooks block
unrelated work, whether MCP servers are always loaded, and whether skills
duplicate model knowledge.

Report a short list of concrete removals or changes, each with the evidence
(file path, hook event, usage) and the risk of removing it. Do not change the
configuration unless the user asks. Prefer deleting a low-value customization
over adding another one.
