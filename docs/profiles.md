# 路由配置与专业配置

这套 setup 不再把所有插件、技能和 hooks 都挂在同一个会话上。日常只进入一个
**路由配置（router）**；它把任务分发给按领域拆开的子会话。每个子会话只加载自己
那一套插件、技能、MCP 和 hooks。

## 为什么拆分

问题不只是上下文变长。插件的 hooks 会作用到**所有**会话，和当前任务无关时也一样：

- `fp-check` 在 `Stop` 和 `SubagentStop` 上注册了 `matcher: "*"` 的 prompt hook。
  它每次结束都会发一次模型请求，检查 fp-check 的验证流程是否完整；即使当前
  对话与安全审查无关，也会先花一次调用。[插件源码](https://github.com/trailofbits/skills/tree/main/plugins/fp-check)
- `double-shot-latte` 的 Stop hook 会在每次停止时调用模型判断是否继续。
- `security-guidance`、`modern-python`、`gh-cli` 等也会注入 hooks 或 PATH shim。
- 50 个插件的技能描述、MCP 工具、agent 描述都会进入系统和工具上下文。

把这些东西按领域隔离后，路由会话只保留编排所需的最小上下文；专业会话只在被
路由到时才付出对应成本。

## 架构

只使用一个 Claude 配置目录（默认 `~/.claude`），不为每个配置复制一套
`CLAUDE_CONFIG_DIR`。原因：

- 登录凭据、插件缓存、后台会话管理器和跨会话消息都在同一份配置里，不需要登录
  多次，也不会出现“路由看不到子会话”的问题。
- 隔离通过**每次启动的 settings 覆盖**完成，而不是靠目录隔离。

子会话的启动参数：

```bash
claude --bg \
  --setting-sources "" \
  --settings ~/.local/state/cc-router/profiles/<profile>/settings.json \
  --append-system-prompt-file ~/.local/state/cc-router/profiles/<profile>/prompt.md \
  --mcp-config ~/.local/state/cc-router/profiles/<profile>/mcp.json \
  --model <hard|easy 模型> \
  -- <任务>
```

关键点：

| 参数 | 作用 |
|---|---|
| `--setting-sources ""` | 不加载用户的 `settings.json`、项目 settings 和 local settings。父会话的 hooks、插件开关和权限不会泄漏到子会话。 |
| `--settings <profile>` | 只启用该配置的 `enabledPlugins` / `skillOverrides` / `hooks` / `permissions`。未列出的插件全部显式设为 `false`。 |
| `--append-system-prompt-file` | 在 Claude Code 默认工程提示词后追加该配置的 SYSTEM prompt。路由本身用 `--agent` 替换系统提示词。 |
| `--mcp-config` | 加载该配置的独立 MCP（dev/rust/go/python/review/librarian 的 fff）；插件自带的 MCP 随插件加载。router 用 `deniedMcpServers` 屏蔽 fff，但保留 nmem/ops 的插件 MCP。 |
| `--bg` | 子会话是原生后台会话，可用 `claude agents` / `claude attach` / `claude logs` 管理，并支持跨会话消息。 |

用户 settings 里的 `env` 不会随 `--setting-sources ""` 加载。启动器会把
`~/.claude/settings.json` 的 `env` 合并进子进程环境（不写盘，shell 已导出的值优先），
所以网关地址、模型别名等配置仍然有效。`apiKeyHelper`、`awsAuthRefresh`、
`gcpAuthRefresh`、`forceLoginMethod` 和 `pluginConfigs` 会复制到生成的 settings。

## 配置一览

| 配置 | 用途 | 默认档位 | 插件 / 技能 / MCP |
|---|---|---|---|
| `router` | 唯一用户入口：意图判断、分发、上下文管理、进度汇总；也负责 nmem 记忆和 ops 集成。 | 便宜快、上下文大 | nowledge-mem、cloudflare、linear、telegram；0 技能；无 fff |
| `quick` | 快速问答、单文件小改、查位置、跑命令。 | easy | 0 / 0 |
| `dev` | 通用多语言实现：功能、重构、调试、多文件修改、测试。 | hard | context7、github、typescript-lsp、typesafe、session-report；14 技能；fff |
| `rust` | Rust 实现；安全审查交给 `review`。 | hard | rust-analyzer-lsp；searching-with-fff；fff |
| `go` | Go 实现：包、并发、错误、gopls、gofmt/vet/test。 | hard | gopls-lsp；searching-with-fff；fff |
| `python` | Python 实现：uv、ruff、ty/pyright、pytest、Pydantic。 | hard | pyright-lsp；friendly-python、searching-with-fff；fff |
| `review` | 代码审查、PR 审查、安全审计、误报验证，含 Rust 安全审查。 | hard | 19 个：coderabbit、claude-security、github、entire、rust-analyzer、rust-review、13 个 Trail of Bits 审查插件（含 fp-check）；8 技能；fff |
| `librarian` | Librarian：跨 GitHub/依赖/文档的只读代码与资料研究，写文档/图表。 | hard | firecrawl、github、context7；10 技能；fff |
| `oracle` | Oracle：只读的架构、计划、深度分析、调试假设和第二意见。 | hard | 0 插件；think、karpathy-guidelines；无 MCP |

`dev`/`review`/`librarian` 的具体技能列表以 `profiles.json` 为准，这里不重复枚举，
避免文档和清单漂移。`librarian` 和 `oracle` 的分工参考 Amp 的
[The Librarian](https://ampcode.com/news/librarian)（远程代码搜索）和
[Oracle](https://ampcode.com/news/oracle)（只读分析/评审/计划）。

具体技能列表以 `profiles.json` 为准；这里不重复枚举，避免文档和清单漂移。

完整清单以 [`build/profiles/profiles.json`](../build/profiles/profiles.json) 为准；
[`claude-plugins.tsv`](../claude-plugins.tsv) 的最后一列是每个插件的归属。
`-` 表示安装但不在任何配置启用。每个被移除项的维护日期、理由和卸载命令见
[配置审计](audit.md)。

刻意不启用的插件与技能：

- `fp-check`：只在 `review`。
- `double-shot-latte`、`claude-session-driver`、`ralph-loop`、`remember`：和路由的
  续跑/后台会话/ledger 职责重复，且都带 hooks。
- `code-simplifier`、`commit-commands`、`feature-dev`、`claude-md-management`、
  `claude-code-setup`、`hookify`、`skill-creator`、`code-review`、`pr-review-toolkit`、
  `security-guidance`、`modern-python`、`modern-go-guidelines`、`pydantic`、
  `superpowers`：由上面的命令或已有技能替代。
- 失修/低价值/坏安装技能：`design`/`ui`（vendored 旧副本/上游改名）、`diagram-design`（安装布局
  缺顶层 SKILL.md）、`review-code`、`deslop-*`、`minimax-*`、`jupyter*`、`fast-rust`、
  `piglet`、`modular-go`、`pua`、`xurl` 等；逐项日期和理由见[配置审计](audit.md)。
- `redis-development`、`modern-web-guidance`：当前就是 disabled；需要时再归类。

## 命令：把内化能力做成一次点击

顶级模型已经能做的事，不再装一个常驻插件。这些命令放在
`~/.claude/commands/`，正文是精简后的流程和验证要求，用户输入 `/name` 即可调用。
它们都设置 `disable-model-invocation: true`，所以不会进入模型的技能列表；路由用
`--disable-slash-commands` 启动，命令只在子会话可用。

| 命令 | 替代/用途 |
|---|---|
| `/plan` | 交给 `oracle`：决策、选项、验收标准、风险，不写实现。 |
| `/research` | 交给 `librarian`：跨仓库/依赖/文档搜索，带引用。 |
| `/simplify` | 替代 `code-simplifier`：最小 diff、不改行为、跑测试。 |
| `/commit` | 替代 `commit-commands` 的提交部分。 |
| `/pr` | 替代 `commit-commands` 的 push/PR 部分；推送前需要确认。 |
| `/feature` | 替代 `feature-dev`：探索、计划、实现、测试。 |
| `/review` | 替代 `code-review` 和 `review-code`：按严重度输出文件:行、失败场景、验证。 |
| `/review-pr` | 替代 `pr-review-toolkit`：读 PR diff、测试、错误处理、类型、兼容性。 |
| `/security-check` | 替代 `security-guidance`：信任边界、注入、authz、SSRF、secrets、供应链。 |
| `/claude-md` | 替代 `claude-md-management`。 |
| `/setup-audit` | 替代 `claude-code-setup` 和 `health`。 |
| `/hook` | 替代 `hookify`；强制优先确定性 hook。 |
| `/skill` | 替代 `skill-creator`。 |
| `/python` | 在 `python` 角色使用；替代 `modern-python`、`piglet` 的常驻部分；`friendly-python` 保留在 python 角色。 |
| `/go` | 在 `go` 角色使用；替代 `modern-go-guidelines`、`modular-go`。 |
| `/pydantic` | 在 `python` 角色使用；替代 `pydantic` 插件。 |
| `/ui` | 替代 stale 的 vendored `design` 技能（Waza 已改名为 `ui`）。 |

命令是全局安装的：不同配置共享同一组快捷命令；配置差异体现在插件、技能、MCP、
hooks 和 SYSTEM prompt，而不是再把命令复制多份。新增/修改命令改
[`build/profiles/commands`](../build/profiles/commands)，然后 `ccr refresh`。

## 路由做什么

路由本身是一个只读的编排会话，工具限制为 `Bash`、`Read`、`Glob`、`Grep`、
`TodoWrite`、`ListAgents`、`SendMessage`、`CronCreate`、`CronDelete`、
`CronList`、`AskUserQuestion`。它不编辑仓库文件；`disallowedTools` 明确移除 Edit/Write/NotebookEdit/Agent/Workflow。
它启用了 nmem 和三个 ops 插件，因此会使用它们的 MCP 工具；但 slash commands 被
`--disable-slash-commands` 关闭，需要用户命令时仍在子会话执行。

### 意图判断

每个新任务按两个维度判断：

- **领域**：`quick` / `dev` / `rust` / `go` / `python` / `review` / `librarian` / `oracle`。
- **档位**：`hard`（设计、调试、跨文件修改、规划、审查、安全）或 `easy`
  （快速问答、单文件小改、查资料、跑命令）。

`UserPromptSubmit` 上有一个确定性的关键词 hook（`route-hint.py`），它不调用模型，
只把候选配置和档位信号作为 `<ccr-route-hint>` 注入。它只是提示，最终判断仍由路由
模型做。关键词表也在 `profiles.json` 里，和配置一起维护。

### 模型

| 环境变量 | 默认 | 用途 |
|---|---|---|
| `CCR_ROUTER_MODEL` | `haiku` | 路由会话本身 |
| `CCR_HARD_MODEL` | `opus` | hard 子会话 |
| `CCR_EASY_MODEL` | `haiku` | easy 子会话 |

默认值只是保守的官方别名。路由要“最便宜、最快、上下文最大”时，应把它设成你的
提供商里符合这个条件的模型。例如网关把 `fable` 映射到 1M 上下文的便宜模型时：

```bash
export CCR_ROUTER_MODEL=fable
export CCR_HARD_MODEL=opus
export CCR_EASY_MODEL=haiku
ccr refresh
```

`--tier easy` 只换模型，不换配置：小的 Rust 改动仍然走 `rust`，但用 easy 模型；
大的跨文件改动走 `dev` + hard。

### 上下文管理

每个子会话有一个 ledger：

```text
~/.local/state/cc-router/sessions/<local-id>/context.md
```

包含 objective、must-retain context 和状态日志。子会话被要求在每轮结束前运行
`ccr checkpoint`，把 `done / files / verification / open` 追加进去。路由在每次
`ccr send` 时自动把 ledger 前置到消息里，所以会话被压缩或换轮次后仍能看到必须
保留的约束。

路由可以：

```bash
ccr context <id>                  # 查看
ccr context <id> --append -       # 追加一条决策/约束
ccr context <id> --replace -      # 在漂移或压缩后重写一份紧凑 ledger
```

### 进度汇总

长任务由路由用 `CronCreate` 建一个 10 分钟左右的会话内 cron，提示固定为“运行
`ccr summary --json`，只报告变化：完成、阻塞、下一步”。所有子会话结束后用
`CronDelete` 取消。长任务也可以让路由用 `SendMessage` 的 `notify_when_idle` 订阅
完成通知，而不是轮询。

## 命令

```bash
ccr                         # 启动路由（同 ccr router）
ccr refresh                 # 从 profiles.json 重新生成所有配置
ccr profiles                # 查看配置和归属
ccr spawn --profile rust --tier easy --name small \
  --prompt-file - <<'PROMPT'
Fix the clippy warning in src/lib.rs. Do not change unrelated code.
PROMPT
ccr send deadbeef --stdin   # 附上 ledger 继续
ccr list                    # 会话列表
ccr status deadbeef --logs  # 状态 + 最近输出
ccr summary                 # 给用户看的汇总
ccr context deadbeef
ccr checkpoint              # 子会话内使用
ccr attach deadbeef         # 打开子会话
ccr stop deadbeef
ccr rm deadbeef             # 删除会话，ledger 移到 archive/
ccr doctor --strict         # 检查隔离、归属、生成物和插件启用状态
```

`ccr spawn --dry-run --json` 会打印完整 argv，不启动会话，适合核对隔离参数。

## 验证

```bash
ccr doctor --strict
ccr profiles
ccr spawn --profile rust --tier easy --name check --prompt 'noop' --dry-run --json
```

`ccr doctor` 会做这些检查：

- 所有已安装插件都被归类，或者明确列在 `unassignedPlugins`。
- 每个配置的插件都已安装，且 `--settings` 真的能启用它们（通过
  `claude --setting-sources "" --settings ... plugin list --json` 预检，不调用模型）。
- `fp-check` 只在 `review`；router 只启用 nmem + Cloudflare/Linear/Telegram，且 fff 被 `deniedMcpServers` 屏蔽。
- 生成物、router agent、MCP 配置存在。
- 用户 settings 里仍然启用的插件（`ccr` 会忽略，但 plain `claude` 会加载）和
  user-scope fff 注册会给出警告和修复命令。

进入路由后可以进一步核对：

```text
/context     # 系统提示词、技能、MCP、hooks 的来源
/hooks       # 只应看到路由的 UserPromptSubmit hint
/plugin      # 所有 marketplace 插件应为 disabled
/skills      # 不应看到专业配置的个人技能
```

在子会话里：

```text
/context     # 应看到该配置的插件技能和 hooks
/mcp         # 只有该配置声明的 server（dev/rust/review 有 fff）
/hooks       # 应有 block-rm、protected-branches、require-tmux、post-edit-check
```

## 隔离边界

- **插件 hooks**：由 `enabledPlugins` 控制；禁用插件的 hooks 不加载。fp-check 的
  Stop/SubagentStop 不会进入路由、dev、rust、go、python、librarian、oracle。
- **个人技能**：`skillOverrides` 把未归属技能设为 `"off"`。插件自带的技能不受
  `skillOverrides` 影响，跟随插件开关。
- **MCP**：子会话用 `--mcp-config` 添加 fff，插件自带的 MCP 随插件启用。router 用
  `deniedMcpServers: [{serverName: fff}]` 屏蔽 fff，保留 nmem/Cloudflare/Linear/Telegram
  的插件 MCP；子会话和 router 都不会强制排除 user/project MCP，fff 已从 user scope 移除，
  迁移说明见下，`ccr doctor` 会警告旧注册。
- **用户/项目 settings**：`--setting-sources ""` 全部忽略。项目 `CLAUDE.md` 和用户
  `CLAUDE.md` 仍然通过消息流程加载，这是有意的。
- **用户 hooks**：不进入任何 `ccr` 会话。需要全局执行的策略应放进配置生成器或
  项目 hooks，而不是用户 settings。
- **auto memory**：`ccr` 会话默认关闭 Claude Code 的自动记忆，避免另一条隐式上下文
  和路由的 ledger 冲突。需要时在 `profiles.json` 的配置里设
  `"autoMemoryEnabled": true`。
- **plain `claude`**：仍然读取用户 settings，可能加载全部插件。日常入口是 `ccr`；
  不要把 `claude` 当作路由的替代品。

## 从旧配置迁移

1. 安装新的 `ccr` 和 profile 源（镜像已包含；手动安装见
   [安装手册](../claude-plugins-setup.md#48-路由配置与-ccr)）。
2. 运行 `ccr refresh --strict`。如果报告“installed plugin not classified”，把新插件
   加进某个配置或 `unassignedPlugins`。
3. 移除旧的 user-scope fff 注册（现在由 dev/rust/review 的 `--mcp-config` 提供）：

   ```bash
   claude mcp remove --scope user fff
   ```

4. 如果你有持久化 home，重新在容器里运行 `ccr refresh`；镜像启动脚本也会自动执行。
5. 用 `ccr doctor --strict` 和 `ccr spawn --dry-run` 核对参数后再实际分发。

旧的 user settings 仍然保留，便于回退；`ccr` 不会修改它（只会写
`~/.claude/agents/ccr-router.md`，已有文件会先备份为 `.bak`）。

## 限制

- `claude --bg` 要求目标目录已被信任。第一次在某个仓库使用前，先在目标仓库运行
  一次 `claude` 并接受信任；脚本环境会直接报 `Workspace not trusted`。
- 子会话会消耗独立的订阅额度；路由默认最多 3 个活跃子会话。
- 后台会话需要 Claude Code 支持 `claude agents` / `--bg`（当前镜像 2.1.311+）。
- 插件更新后运行 `ccr refresh`；`ccr` 不会自动更新插件版本。
- 路由模型和子会话模型都依赖你的提供商实际提供的别名；用 `ccr doctor` 看
  `model` 检查行的生效值。
