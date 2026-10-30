# 配置审计：移除、保留与维护边界

审计日期：2026-10-31。范围：`claude-plugins.tsv` 中的 50 个插件，以及
`~/.claude/skills` 下的技能来源。方法：用 GitHub API 查源码仓库的默认分支最近
提交、最近一次非批量提交、`archived` 状态；插件按目录查，外部服务按真实仓库查。
批量 metadata/LICENSE 提交会掩盖最后修改时间，因此同时看“最后实质提交”。

结论：没有发现 archived 仓库。真正的判断标准不是“多久没更新”，而是：

1. **插件是否有 prompt 之外的资产**：hooks、脚本、CLI、领域资料、专用 agent；
2. **同样的能力是否已经在另一个保留的角色/技能里**；
3. **常驻 hooks 的成本是否大于它带来的确定性收益**。

命令替代的逐项证据、覆盖范围和丢失项见
[命令替代插件的证据](command-replacements.md)。这份审计只记录移除/保留决策。

## 一、不再预启用的插件

这些插件仍可全量安装，但 `enabledPlugins` 在所有配置中为 `false`。

| 插件 | 最后实质提交 | 处理 | 理由 |
|---|---|---|---|
| `code-simplifier` | 2026-01-09 | `/simplify` | 52 行纯 prompt；命令保留行为不变、项目规范、最小 diff、测试验证。 |
| `commit-commands` | 2025-12-02 | `/commit`、`/pr`、`/clean-gone` | 三个 git/gh 流程；命令覆盖提交、PR、`[gone]` 分支清理。 |
| `feature-dev` | 2025-12-13 | router 多子会话 + `/feature` | 多 agent 编排上移到 router；单会话 `/feature` 只用于小功能。 |
| `code-review` | 2026-10-26 | `/review` + thermos/Trail of Bits | 多 agent/置信度由 review 配置的专用技能承担；命令只定输出契约。 |
| `pr-review-toolkit` | 2026-04-28 | `/review` + thermos/Trail of Bits | 6 个专用 agent 被 review 技能合并；若要求完全等价并行度应恢复插件。 |
| `claude-code-setup` | 2026-05-28 | `/setup-audit` | 配置审计是仓库特定流程，命令更直接。 |
| `hookify` | 2026-05-20 | `/create-claude-hook` | 只保留“创建确定性 hook”的流程；插件规则 DSL 运行时不需要。 |
| `skill-creator` | 2026-04-23 | `/create-claude-skill` | SKILL.md 创建是短流程；命令保留触发描述和验证要求。 |
| `ralph-loop` | 2026-03-28 | router CronCreate/ledger | Stop hook 反复续跑；router 已经负责跨轮推进，重复机制增加费用。 |
| `double-shot-latte` | 2026-02-25 | 无 | 8 个月未更新；每次 Stop 调模型判断是否继续，router 自己决定。 |

`redis-development` 保持**全局禁用**（`unassignedPlugins`，最后一列 `-`），但保留
安装；需要 Redis 时再临时启用，不进入任何默认角色。

## 二、之前移除、现在明确保留的插件

这些项曾被过度概括为“模型已内化”，但插件包含 prompt 之外的资料、hooks 或
独立工具。按你的反馈恢复：

| 插件 | 位置 | 保留理由 |
|---|---|---|
| `security-guidance` | dev | 11,756 行 Python hooks + tests，做 diff 级安全提示和 Stop 检查；不能由命令复制。按你的要求把检查前移到 dev，减少 review 来回。 |
| `modern-go-guidelines` | go、review | Go 新版本特性/规范是版本化领域资料；实际开发中模型确实会退回旧写法。命令只做入口，不再声称替代。 |
| `modern-python` | python、review | Python 工具链/版本规范 + PATH shims；领域资料不能靠模型记忆保证。 |
| `pydantic` | python、review | Pydantic v2 的版本差异/迁移细节是插件资料；命令只做快捷入口。 |
| `superpowers` | dev | 大型技能/方法论库，仍在维护；按你的要求保留，router 吸收 feature-dev 的编排职责。 |
| `remember` | router、长会话角色 | SessionStart/End hooks、Haiku 压缩、`/remember` handoff；是跨会话记忆，不是 ccr ledger 的替代。 |
| `claude-session-driver` | router | `csd` CLI + tmux + 事件流 + handoff；`claude --bg` 不能提供随时 attach。 |
| `claude-md-management` | dev | 179 行 skill + 3 个 references（质量标准/模板/更新规则）；`/claude-md` 只是入口，不复制资料。 |
| `modern-web-guidance` | frontend | 现代 Web 平台资料更新快；按你的要求保留并移入新的前端角色。 |

`remember` 与 `ccr` ledger 的分工：remember 在会话边界做压缩历史并注入下一次
SessionStart；ledger 是 router 在任务进行中同步维护、随 `ccr send` 发送的
must-retain 包。只用 remember 时，恢复会话拿不到“这次任务必须保留的约束”这一份
精确上下文；两者不是同一个东西。

## 三、技能：ninehills Common 改为按上游直装

原来的 `ninehills/skills` Common 场景安装 34 个 vendored 技能，存在两个问题：

- 多个技能是上游的旧副本（`design` 已改名 `ui`；`diagram-design` 的父目录软链接
  导致顶层没有 `SKILL.md`，实际不会加载）；
- Common 把不需要的技能也装进 `~/.claude/skills`，增加扫描和误触发面。

现在 Dockerfile **不再安装 Common**，只从上游直装保留下来的技能；ninehills 只保留
其自有的 `tech-doc-style-chinese`（vendor 维护）。

### 保留（直装上游）

| 技能 | 上游 | 用途 |
|---|---|---|
| `think`、`hunt`、`read`、`write`、`learn` | tw93/Waza | 规划、调试、读写/学习；Waza 活跃。 |
| `tdd` | mattpocock/skills | 测试驱动实现；上游活跃。 |
| `karpathy-guidelines` | forrestchang/andrej-karpathy-skills | 你明确在用的行为准则。 |
| `drawio-skill` | agents365-ai/drawio-skill | 图表；替代已坏的 `diagram-design`。 |
| `tech-doc-style-chinese` | ninehills/skills | 中文技术文档；ninehills 自有，vendor 维护。 |
| `fast-rust`、`piglet`、`modular-go`、`friendly-python` | PsiACE/skills | 按你的要求保留，并放入 `review` 作为语言检查视角；`friendly-python` 同时留在 `python`。 |
| `gh-stack`、`reclaim-code-entropy`、`scoped-change`、`worktree-pr`、`ux-writing` | 各自上游 | 你的工作流明确在用。 |
| `thermos` / `thermo-nuclear-*` | cursor/plugins | review 的多轮审查。 |
| `test-audit`、`better-readme`、`searching-with-fff`、`ripwire*` | 各自上游 | 审查、README、fff、定位；保留。 |
| `code-review-page` | IceCodeNew/code-review-page-kit | 块级 HTML 评审页、diff 注释、复杂度热点和英文实现提示；只在 review 启用。 |

### 不再安装（原 ninehills Common 或旧安装）

`design`、`diagram-design`、`improve-codebase-architecture`、`to-issues`、`to-prd`、
`grill-with-docs`、`setup-matt-pocock-skills`、`triage`、`fireworks-tech-graph`、
`japanese-tech-writing`、`review-code`、`deslop-en`、`deslop-zh`、`jupytext`、
`jupyter-notebook`、`minimax-docx`、`minimax-pdf`、`minimax-xlsx`、
`pptx-generator`、`bggg-creator-image2ppt`、`gpt-image-gen`、`pua`、
`brainstorming-cn`、`health`、`better-goal`、`skill-creator`（独立技能）、`xurl`。

理由分三类：

- **可被角色/命令替代**：`improve-codebase-architecture`、`to-issues`、`to-prd`、
  `grill-with-docs`、`triage`、`health`、`brainstorming-cn`、`review-code`；
- **低频或依赖外部 key**：`jupyter*`、`minimax-*`、`pptx-generator`、
  `bggg-creator-image2ppt`、`gpt-image-gen`、`xurl`；
- **陈旧的 vendored 副本/布局损坏**：`design`、`diagram-design`、
  `fireworks-tech-graph`、`japanese-tech-writing`、`setup-matt-pocock-skills`。

`unassignedSkills` 里仍保留这些名字和原因，作为“不预启用”的记录；它们不再由镜像
安装，所以 `ccr refresh --strict` 不会要求它们存在。

## 四、为什么不全量卸载

- 你的要求是“环境可以全量安装，但不同配置预启用不同集合”。镜像继续安装 50 个
  插件；配置层只负责启用集合，临时排障/切换角色不需要重新联网。
- 真正卸载会改变 `claude plugin list`、镜像层和持久化 home；在确认“半年不用”之前
  默认保留更稳。
- 需要真正卸载时，只对上面“不再预启用”的 10 个插件操作，**不要**卸载
  `security-guidance`、`modern-go-guidelines`、`modern-python`、`pydantic`、
  `superpowers`、`remember`、`claude-session-driver`、`claude-md-management`、
  `modern-web-guidance`。完整命令见
  [命令替代插件的证据](command-replacements.md#结论) 上方的安装清单，或直接：

  ```bash
  for p in code-simplifier commit-commands feature-dev code-review \
           pr-review-toolkit claude-code-setup hookify skill-creator \
           ralph-loop double-shot-latte; do
    claude plugin uninstall "$p@claude-plugins-official" 2>/dev/null || \
    claude plugin uninstall "$p@superpowers-marketplace" 2>/dev/null || true
  done
  ccr refresh --strict
  ```

## 五、持续发现

`ccr doctor --strict` 检查：

- 已安装但未归类的插件/技能；
- 配置声称启用但未安装的插件；
- fp-check 是否只在 review；
- 生成物、router agent、命令是否最新；
- user settings 里仍会作用于 plain `claude` 的插件，以及旧 user-scope fff 注册；
- router 的 nmem/remember/ops/session-driver 是否按预期启用。
