# fff task routing

Use this reference after `searching-with-fff` applies to a repository search. General explanations, web research, and filtering command output do not need fff. These routes guide tool choice; they do not register hooks or enforce a tool ban.

## Choose one entry point

All search entries below refer to tools from the fff MCP server, not similarly named built-in tools. Resolve the host's exposed names before calling: for example, fff's `multi_grep` may appear as `mcp__fff__multi_grep` or `fff_multi_grep`. Preserve the server's argument names and types.

| Task or next action | Entry point | Arguments |
| --- | --- | --- |
| Find a definition, usages, or a literal in source | fff `grep` | `{"query":"*.rs ActorAuth","maxResults":20}` |
| Find a vaguely remembered filename | fff `find_files` | `{"query":"typescropt","maxResults":20}` |
| Locate files under a known directory | fff `find_files` | `{"query":"src/ config","maxResults":20}` |
| Search two or more names or naming variants | fff `multi_grep` | `{"patterns":["PrepareUpload","prepare_upload"],"constraints":"*.rs","maxResults":20}` |
| Need only paths, not matching text | fff `grep` | `{"query":"src/ ActorAuth","output_mode":"files","maxResults":20}` |
| Read a file whose path is already known | Host's file-reading tool | Read the relevant range directly |

fff content matches are textual references, not a semantic call graph. Read the code before claiming that a match is a caller or definition. `multi_grep` matches ANY pattern, not every pattern.

## Query constraints

For `grep`, prefix constraints inside `query`. For `multi_grep`, put them in the separate string `constraints`, not an object.

- File type: `*.rs` or `*.{ts,tsx}`.
- Directory: `src/` (include the trailing slash).
- Filename: `schema.rs` or `src/main.rs`.
- Exclude: `!test/` or `!*.spec.ts`.

A bare word is not a directory constraint. `quote TODO` searches text rather than limiting results to a directory. Keep filename queries short; multiple terms narrow results, not OR them. Prefer plain identifiers over escaped code syntax.

## Keep results bounded

Start with `maxResults: 20` and little or no extra `context`. Use `output_mode: "files"` when only paths matter. After finding locations, read the code instead of repeatedly trying spelling variants.

If the response supplies a cursor and more results are needed, call the same tool with the same query or patterns, constraints, and output mode, plus `cursor`. A limited first page is not exhaustive evidence of all references.

## Availability and scope

The stdio server searches its startup directory, resolving Git subdirectories to their worktree root. These tools have no argument for switching to another repository. Ensure the host launches fff in the intended worktree; restart or reconnect with the correct working directory if the root is wrong.

If disabled or unavailable, report that condition and use the host's MCP connection controls to enable or reconnect fff. If the host offers no such controls, request that the connection be restored. Do not replace a failed fff search with built-in search, grep/rg, or a custom scanner. A known file can still be read directly without claiming repository-wide search coverage.

MCP registration, skill discovery, and tool-definition loading are separate. This reference does not activate a disabled server or defer its schemas. For Claude Code installation and context controls, see the [installation guide](https://github.com/IceCodeNew/claude-code-plugins-setup/blob/master/claude-plugins-setup.md#44-fff-mcp-与本仓库搜索技能).
