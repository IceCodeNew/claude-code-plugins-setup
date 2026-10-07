---
name: searching-with-fff
description: Use when searching files or code in the current Git worktree, locating definitions or references, finding a remembered filename, or searching multiple identifiers with fff. Not for web searches or general questions unrelated to repository files.
---

# Search with fff

Use the connected `fff` MCP server for repository search. This skill is maintained by this repository, not by fff upstream.

## Route by task

| Need | fff tool |
| --- | --- |
| Definition, reference, or one content pattern | `grep` |
| Filename or fuzzy path discovery | `find_files` |
| Multiple identifiers or naming variants, OR matching | `multi_grep` |

Tool names above are server-local. Select the corresponding tool exposed by the host's fff server; prefixes vary (Claude Code: `mcp__fff__grep`). Never substitute a built-in or shell grep for fff's `grep`.

Read [routing.md](routing.md) for constraints, pagination, or recovery. Match the task, not merely a keyword in prose. Start with `maxResults: 20`, narrow by known directory or file type, then read relevant code with the host's file-reading tool. Read a known path directly; no search is needed.

Example: send to fff's `multi_grep`:

```json
{"patterns":["PrepareUpload","prepare_upload"],"constraints":"*.rs","maxResults":20}
```

## Recovery

For invalid arguments or query syntax, correct from the error and schema, then retry. If disconnected or unavailable, report the failure and use the host's MCP connection controls to enable/reconnect fff; if unavailable, request restoration. Do not silently switch to built-in search, shell grep/rg, or an ad hoc scanner. For empty results, broaden once, then inspect relevant code.
