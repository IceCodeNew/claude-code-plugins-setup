# 配置审计：删除、保留与维护边界

审计日期：2026-10-31。范围：`claude-plugins.tsv` 中的 44 个插件，以及
`~/.claude/skills` 下的技能来源。方法：用 GitHub API 查源码仓库的默认分支最近
提交、最近一次非批量提交、`archived` 状态；插件按目录查，外部服务按真实仓库查。
批量 metadata/LICENSE 提交会掩盖最后修改时间，因此同时看「最后实质提交」。

结论：没有发现 archived 仓库。判断标准：

1. **插件是否有 prompt 之外的资产**：hooks、脚本、CLI、领域资料、专用 agent；
2. **同样的能力是否已经在另一个保留的角色/技能里**；
3. **删除/替代的 ROI 是否为正**：纯 prompt 插件能自动更新，转成用户命令通常
   没有收益；带 stop hooks 或维护中的领域资料则优先保留或隔离。

命令替代的逐项证据、覆盖范围和丢失项见
[命令替代插件的证据](command-replacements.md)。下线的插件/技能**直接删除**，镜像
不再安装，`profiles.json` 和 `claude-plugins.tsv` 不再记录，不保留「安装但禁用」。

## 一、删除的插件

| 插件 | 最后实质提交 | 替代 | 理由 |
|---|---|---|---|
| `feature-dev` | 2025-12-13 | router 多子会话 + `/feature` | 多 agent 编排上移到 router；单会话 `/feature` 只用于小功能。 |
| `code-review` | 2026-10-26 | `/review` + thermos/Trail of Bits | 多 agent/置信度由 review 配置的专用技能承担；命令只定输出契约。 |
| `pr-review-toolkit` | 2026-04-28 | `/review` + thermos/Trail of Bits | 6 个专用 agent 被 review 技能合并；若要求完全等价并行度，应恢复插件（当前不恢复）。 |
| `ralph-loop` | 2026-03-28 | router CronCreate/ledger | Stop hook 反复续跑；router 已经负责跨轮推进。 |
| `double-shot-latte` | 2026-02-25 | 无 | 8 个月未更新；每次 Stop 调模型判断是否继续，router 自己决定。 |
| `session-report` | 2026-04-10 | 无 | 只生成历史使用报告，不参与日常开发；删除以减少常驻插件。 |

`skill-creator`、`redis-development` 仍安装，但保持原本的禁用状态
（`unassignedPlugins`，任何配置都不启用）。`hookify` 在所有角色启用；
`japanese-tech-writing` 保留在 librarian。`session-report` 已删除。

### 真正卸载这些插件

```bash
for p in feature-dev code-review pr-review-toolkit ralph-loop session-report; do
  claude plugin uninstall "$p@claude-plugins-official" 2>/dev/null || true
done
claude plugin uninstall double-shot-latte@superpowers-marketplace 2>/dev/null || true
ccr refresh --strict
```

## 二、保留的纯 prompt 插件

`code-simplifier`、`commit-commands`、`claude-code-setup` 是纯 prompt/命令式插件，
没有需要复制的脚本或 hooks。继续以插件形式安装在 dev：它们能自动更新，转成命令
没有收益。`code-simplifier` 的 52 行 agent prompt 和 `commit-commands` 的三个流程
仍由插件维护；`code-simplifier` 与 `reclaim-code-entropy` 在 dev 的同一稳定阶段执行。
`/commit`、`/pr`、`/clean-gone`、`/setup-audit` 已移除；review 不做简化。

## 三、明确保留的插件

这些项包含 prompt 之外的资料、hooks 或独立工具，保留理由如下：

| 插件 | 位置 | 保留理由 |
|---|---|---|
| `security-guidance` | dev | 11,756 行 Python hooks + tests，做 diff 级安全提示和 Stop 检查；不能由命令复制。安全检查因此前移到 dev。 |
| `modern-go-guidelines` | go | Go 新版本特性/规范是版本化领域资料；review 不重复启用，避免占用审查上下文。 |
| `modern-python` | python | Python 工具链/版本规范 + PATH shims；review 不重复启用。 |
| `pydantic` | python | Pydantic v2 的版本差异/迁移细节是插件资料；review 不重复启用。 |
| `superpowers` | dev | 大型技能/方法论库；router 吸收 feature-dev 的编排职责。 |
| `remember` | router、长会话角色 | SessionStart/End hooks、Haiku 压缩、`/remember` handoff；是跨会话记忆，不是 ccr ledger 的替代。 |
| `claude-session-driver` | router | `csd` CLI + tmux + 事件流 + handoff；`claude --bg` 不能提供随时 attach。 |
| `claude-md-management` | dev | 179 行 skill + 3 个 references；不提供额外 ccr 命令。 |
| `modern-web-guidance` | frontend | 现代 Web 平台资料；保留在专门前端角色。 |

`remember` 与 `ccr` ledger 的分工：remember 在会话边界做压缩历史并注入下一次
SessionStart；ledger 是 router 在任务进行中同步维护、随 `ccr send` 发送的
must-retain 包。只用 remember 时，恢复会话拿不到「当前任务必须保留的约束」这一份
精确上下文；两者不是同一个东西。

## 四、技能来源与安装范围

`ninehills/skills` Common 已从 Dockerfile 移除，不再整组安装 34 个 vendored 技能。
Waza、tdd、karpathy-guidelines 等不再从 ninehills 安装，改为直接上游：

| 技能 | 直接上游 | 位置 |
|---|---|---|
| `think`、`hunt`、`read`、`write`、`learn` | tw93/Waza | dev / librarian / oracle |
| `check` | tw93/Waza | review |
| `health` | tw93/Waza | dev |
| `ui` | tw93/Waza | frontend |
| `tdd` | mattpocock/skills | dev |
| `karpathy-guidelines` | forrestchang/andrej-karpathy-skills | dev / oracle |
| `tech-doc-style-chinese` | ninehills/skills（自有，vendor） | librarian |
| `japanese-tech-writing` | 上游 gist | librarian |
| `fast-rust`、`piglet`、`modular-go`、`friendly-python` | PsiACE/skills | 开发角色：rust / python / go / python；review 不重复 |
| `reclaim-code-entropy` | Yevanchen/reclaim-code-entropy | dev，与 code-simplifier 同阶段 |
| `gh-stack`、`scoped-change`、`worktree-pr`、`ux-writing` | 各自上游 | dev / librarian |
| `thermos*`、`test-audit`、`better-readme`、`searching-with-fff`、`ripwire*`、`code-review-page` | 各自上游 | review / dev / librarian |

不再安装/删除的技能包括：`design`（旧 vendored 名称）、`diagram-design`、`drawio-skill`、
`improve-codebase-architecture`、`to-issues`、`to-prd`、`grill-with-docs`、`triage`、
`fireworks-tech-graph`、`review-code`、`deslop-*`、
`jupytext`、`jupyter-notebook`、`minimax-*`、`pptx-generator`、
`bggg-creator-image2ppt`、`gpt-image-gen`、`pua`、`brainstorming-cn`、
`better-goal`、`skill-creator`（独立技能）、`xurl`。

删除理由：可被角色/命令替代、低频/依赖外部 key、或旧 vendored/坏布局；不再保留
单独的「禁用记录」。

## 五、安装范围与卸载边界

- 配置遵循「全量安装、按配置启用」。镜像安装 44 个插件（42 启用、2 禁用）；
  配置层只决定启用集合。
- 删除项已经不在镜像里，不占上下文、不会被误启用。保留项仍然全量安装，便于临时
  启用、排障和切换角色。
- 对确定不用的已删除插件，上面已经给出真正卸载命令；其余保留项无需卸载。

## 六、配置检查

`ccr doctor --strict` 检查：

- 已安装但未归类的插件/技能（新装的东西不会被静默启用）；
- 配置声称启用但未安装的插件；
- fp-check 是否只在 review；
- 生成物、router agent、命令是否最新；
- user settings 里仍会作用于 plain `claude` 的插件，以及旧 user-scope fff 注册；
- router 的 nmem/remember/ops/session-driver 是否按预期启用。
