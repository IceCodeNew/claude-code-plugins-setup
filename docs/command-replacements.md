# 命令替代插件的证据与边界

这份文档回答一个问题：**为什么某个插件可以由命令替代，而另一个不能？**
判断标准不是“命令看起来也能做”，而是逐项对照插件的实际组件：

- 如果插件主体是一段自然语言 prompt，没有脚本、hooks、数据文件、专用
  agent 或外部服务，那么命令可以把同样的决策规则写成一次可调用的流程；
- 如果插件包含确定性代码（hooks、规则引擎、索引、CLI）、需要专门工具权限的
  agent，或维护着模型不可能凭记忆重建的领域资料，那么命令不能替代，插件保留；
- 多 agent 编排只有在 **另一个已启用的技能/角色已经提供同等能力** 时才移除，
  而不是因为命令里写了一句“多角度审查”。

“模型已内化”不是可证明的定理。这里能证明的是：**被移除的插件没有超出
prompt 的额外资产**；不能证明的是模型每次都会自发执行同样的流程。因此命令
保留流程和验证要求，但命令是用户触发的策略入口，不冒充插件的运行时。

## 逐项对照

源码行数来自 2026-10-31 的插件仓库；命令行数来自
`build/profiles/commands`。

| 插件 | 插件实际内容 | 替代 | 覆盖 | 丢失/边界 | 结论 |
|---|---|---|---|---|---|
| `code-simplifier` | 52 行 agent prompt，`model: opus`，无脚本/hooks | 无（插件保留） | — | 插件能自动更新并在编辑后触发；命令没有 ROI | **保留在 dev**，与 `reclaim-code-entropy` 同阶段 |
| `commit-commands` | 3 个命令：`commit`、`commit-push-pr`、`clean_gone`；全部是 git/gh 指令 | 无（插件保留） | — | 插件能自动更新；命令重复维护 | **保留在 dev**，不转命令 |
| `feature-dev` | 125 行命令 + 3 个 agent（explorer/architect/reviewer） | router 多子会话 + `/feature` | 探索、计划、实现、评审的拆分；router 限制 3 个并行子会话 | 插件在一个会话内用专用 agent；router 用后台会话，协调成本更高 | 移除插件，编排上移到 router |
| `code-review` | 110 行命令，多 agent 审查 + 置信度评分 | `/review` + `review` 配置的 thermos/Trail of Bits | 发现分级、证据、置信度；`fp-check` 负责误报复核 | 命令不重新实现评分引擎，依赖 review 配置的专用技能 | 移除插件；不是命令独力替代 |
| `pr-review-toolkit` | 189 行命令 + 6 个专用 agent（测试、类型、注释、静默失败等） | `/review` + thermos/Trail of Bits | 测试覆盖、类型设计、错误处理、注释等审查视角 | 6 个 agent 的并行分工被合并；若需要同等并行度，保留插件更稳 | 移除；如追求完全等价应恢复插件 |
| `claude-md-management` | 179 行 skill + 3 个 references + 命令 | 无（插件保留） | — | 保留插件即可，不提供额外入口 | **保留在 dev** |
| `claude-code-setup` | 配置推荐命令/技能 | 无（插件保留） | — | 纯 prompt 插件能自动更新；命令没有 ROI | **保留在 dev** |
| `hookify` | 231 行创建命令 + Python 规则引擎 + 4 个 hooks | 无（插件启用） | — | 所有角色启用原插件，不提供替代命令 | **所有角色启用** |
| `skill-creator` | 技能创建流程/评估 | 无（插件保留禁用） | — | 保留原插件和禁用状态，不提供替代命令 | **保留安装但禁用** |
| `security-guidance` | 11,756 行 Python hooks + tests；PostToolUse/Stop 审查 | 无 | — | 模式匹配、diff 状态、LLM 审查、误报处理无法用命令复制 | **保留在 dev** |
| `modern-go-guidelines` | Go 版本特性/规范资料 + 检查规则 | 无（插件保留） | — | 版本化资料保留在 go | **保留在 go** |
| `modern-python` | Python 规范/工具链 + PATH shims | 无（插件保留） | — | 版本化规范与 shim 是插件资产 | **保留在 python** |
| `pydantic` | Pydantic v2 版本化资料 | 无（插件保留） | — | 版本差异和迁移细节是领域资料 | **保留在 python** |
| `superpowers` | 大量技能/方法论，持续维护 | `/feature`、router 编排 | 只用其中一部分 | 技能库和专用流程不是命令能完整复制的 | **保留在 dev** |
| `remember` | SessionStart/End hooks、Haiku 压缩、`/remember` handoff | ccr ledger | 跨会话记忆由 remember 承担 | remember 是异步压缩的全局历史，不是当前任务可同步更新的 must-retain 包 | **保留；与 ledger 分工** |
| `claude-session-driver` | `csd` CLI、tmux、事件流、handoff | `ccr spawn --bg` | 后台自动化由 ccr 承担 | tmux attach/handoff 是插件独有能力 | **保留在 router** |
| `modern-web-guidance` | 现代 Web 平台资料/技能 | 无 | — | 平台特性更新快，资料有价值 | **保留在 frontend** |
| `code-review-page` | skill + renderer + QA 脚本 + schema/references | 无（review 技能） | 块级 HTML 评审页、diff 注释、复杂度热点、英文实现提示 | 需要真实 metrics/QA；不能凭空生成数据 | **保留在 review** |

## 结论

- **命令只提供角色入口/输出契约**：`/plan`、`/research`、`/feature`、`/review`、
  `/security-check`。纯 prompt 插件（simplifier、commit、claude-code-setup、
  claude-md-management、hookify、skill-creator）保留原插件，不提供替代命令。
- **插件保留**的是“有运行时/领域资料/独立工具”的插件：security-guidance、
  modern-go/python、pydantic、superpowers、remember、session-driver、
  modern-web-guidance、claude-md-management。
- `code-review` / `pr-review-toolkit` 的移除理由不是“命令更强”，而是
  `review` 配置已经有 thermos/Trail of Bits 的专用审查技能；如果要求与
  6 个 agent 完全等价的并行度，应恢复 `pr-review-toolkit`。
- `/review` 不自动执行 `thermos`/`thermo-nuclear-*`：它们必须由用户单独触发，
  成本高。`/review` 先跑 `test-audit`/`ripwire`，再在代码稳定后跑 `/security-check`，
  最后用 `fp-check` 复核安全发现；不做简化。`rust-review` 只在 Rust 改动时可选。
  `code-simplifier` + `reclaim-code-entropy` 在 dev 的同一阶段执行，位于 review 之前。
- `remember` 与 `ccr` ledger **不是同一层**：remember 在会话边界做压缩历史，
  ledger 是 router 在任务进行中同步维护、随消息发送的 must-retain 包。保留
  ledger 不是重造 remember；如果只用 remember，恢复会话时拿不到“这次任务
  必须保留的约束”这一份精确上下文。
