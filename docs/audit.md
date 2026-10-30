# 配置审计：不必要、重复与失修项

审计日期：2026-10-31。范围：`claude-plugins.tsv` 中的 50 个插件，以及
`~/.claude/skills` 下由 ninehills、openskills、ripwire、fff 安装的技能。

方法：用 GitHub API 查每个插件/技能的**实际源码仓库**，记录默认分支最近提交、
最近一次非批量提交、`archived` 状态和仓库活跃度。单仓库插件按插件目录查提交；
外部仓库按仓库查。批量提交（例如给所有插件加 LICENSE、给十个插件补 version、
统一修 skill metadata）会掩盖真正的最后修改时间，所以表中同时给出“最后实质提交”。
官方 marketplace 的 `external_plugins/*` 是薄封装，真正的服务由外部仓库维护；这类
条目会单独标注，不能只看封装目录的日期。

结论先说：**没有发现已被归档（archived）的仓库**；问题主要是三类：

1. **能力已被顶级模型覆盖**：简化、提交、评审、文档审计等，更适合做成命令。
2. **插件 hooks 或 skill 常驻造成的成本**：fp-check（已隔离到 review）、
   security-guidance、double-shot-latte、ralph-loop、modern-python 等；后四者已不再
   预启用。
3. **个人仓库里的低频技能开始失修**：ninehills/public-skills、PsiACE/skills、
   minimax-ai/skills、tw93/Waza 的旧路径等。

环境仍然全量安装（这是有意的，便于临时启用和回退）；下面这些只是**不再预启用**。
需要真正卸载时，按每节的命令操作。

## 一、已从所有配置移除的插件

这些插件仍在镜像/环境里，但 `enabledPlugins` 在所有配置中为 `false`
（`claude-plugins.tsv` 最后一列为 `-`）。其中 14 个由命令替代，`ralph-loop` 由路由
替代，其余由 hooks/维护性原因移除。

| 插件 | 最后实质提交 | 处理 | 理由 |
|---|---|---|---|
| `code-simplifier` | 2026-01-09 | 移除；`/simplify` | 唯一能力是“简化最近修改的代码”。顶级模型已经能做；命令保留了不改变行为、最小 diff、跑测试的约束。插件 8 个月没有实质更新。 |
| `commit-commands` | 2025-12-02 | 移除；`/commit`、`/pr` | git add/commit/push/PR 是提示词流程，不是需要常驻的插件能力。2026-10 的提交只是补 version。 |
| `feature-dev` | 2025-12-13 | 移除；`/feature` | 探索、计划、实现、测试的流程可由一条命令表达；多 agent 编排不是每次开发都需要。 |
| `claude-md-management` | 2026-01-20 | 移除；`/claude-md` | CLAUDE.md 审计是一次性、短流程；插件自 2026-01 没有实质更新。 |
| `claude-code-setup` | 2026-05-28 | 移除；`/setup-audit` | “分析仓库并推荐 Claude Code 配置”是审计命令的职责；插件 5 个月未更新。 |
| `hookify` | 2026-05-20 | 移除；`/hook` | 创建 hook 是短配方；命令会强制优先确定性 hook、避免 prompt hook 的常驻模型调用。 |
| `skill-creator` | 2026-04-23 | 移除；`/skill` | 写 SKILL.md 是短流程；插件半年未更新，且其“评估技能”能力可以用 `/skill` + 现有 eval 工具体现。 |
| `code-review` | 2026-10-26 | 移除；`/review` | 插件仍在维护，但核心是多 agent 评审 + 置信度评分；顶级模型 + `/review` 的固定输出结构已足够。`review` 配置保留 Trail of Bits 的安全专用审查。 |
| `pr-review-toolkit` | 2026-04-28 | 移除；`/review-pr` | 注释、测试、错误处理、类型设计的多 agent 评审可合并为一条结构化命令；插件 6 个月没有实质更新。 |
| `security-guidance` | 2026-10-27 | 移除；`/security-check` | 仍在维护，但会给每个会话装 PostToolUse/Stop hooks；审查应由 `review` 配置按需执行，而不是每个 dev 会话常驻。 |
| `modern-python` | 2026-09-15（元数据批量提交；内容更早） | 移除；`/python` | PATH shim + hook 会改写每个 dev 会话的 python/pip；uv/ruff/ty 约定已内化，命令足够。Trail of Bits 的这个插件不属于安全审查域。 |
| `modern-go-guidelines` | 2026-08-30 | 移除；`/go` | Go 规范是模型知识；仓库已有 gopls，命令保留 gofmt/vet/test 的验证要求。 |
| `pydantic` | 2026-09-11 | 移除；`/pydantic` | v2 常用 API 已内化；命令保留版本检查、validator/ConfigDict 和序列化稳定性的要点，版本细节以仓库为准。 |
| `superpowers` | 2026-10-20 | 移除；`/feature`、`/review` + 现有 `tdd`/`hunt`/`think` 技能 | 仍在积极维护，但技能库很大、默认进入每个 dev 会话。核心方法论已有更小的替代；保留其上游仓库，需要时可临时启用。 |
| `ralph-loop` | 2026-03-28 | 移除；路由的 CronCreate / `ccr` 续跑 | Stop hook 会让每个 dev 会话反复续跑；路由已经负责跨轮次推进和进度汇总，重复机制只会增加费用。 |
| `double-shot-latte` | 2026-02-25 | 移除；无需替代 | 8 个月未更新；Stop hook 每次停止都调用模型判断“是否继续”。路由自己决定何时继续，插件纯属重复成本。 |
| `claude-session-driver` | 2026-10-10 | 移除；原生 `claude --bg` | 仍在维护，但用 tmux 启动 worker 的做法绕过了配置边界；Claude Code 原生后台会话 + `claude agents` 已覆盖。 |
| `remember` | 2026-10-19 | 移除；`ccr` ledger | 仍在维护，但会在每个会话注入记忆 hooks；路由的每会话 ledger 是显式、可审计的上下文来源。 |
| `session-report` | 2026-04-10 | 可选移除 | 半年未更新，且只生成历史使用报告；保留不影响其他会话，但不是日常能力。 |
| `modern-web-guidance` | 2026-09-17 | 已禁用；建议卸载 | 仍活跃，但当前配置从未启用；如果不需要 Web 最佳实践，直接卸载减少体积。 |
| `redis-development` | 2026-10-30（monorepo 路径日期） | 已禁用；建议卸载 | 当前配置从未启用；Redis 任务可按需安装，避免常驻。 |

### 真正卸载这些插件

```bash
# 按需选择；先看 ccr doctor 的当前状态
for p in \
  code-simplifier commit-commands feature-dev claude-md-management claude-code-setup \
  hookify skill-creator code-review pr-review-toolkit security-guidance \
  modern-python modern-go-guidelines pydantic superpowers ralph-loop \
  double-shot-latte claude-session-driver remember
do
  claude plugin uninstall "$p@claude-plugins-official" 2>/dev/null || \
  claude plugin uninstall "$p@trailofbits" 2>/dev/null || \
  claude plugin uninstall "$p@goland-claude-marketplace" 2>/dev/null || \
  claude plugin uninstall "$p@superpowers-marketplace" 2>/dev/null || true
done
ccr refresh --strict
```

镜像场景要从构建中删除，需要同时改
[Dockerfile](build/Dockerfile) 的安装循环和
[profiles.json](build/profiles/profiles.json) 的 `unassignedPlugins`，否则
`ccr refresh --strict` 会把“已安装但未归类”当成错误。上面的卸载命令不会动
`profiles.json`；如果卸载后仍保留在 `unassignedPlugins`，清单只是记录，不会要求安装。

## 二、已从配置移除的技能

这些技能仍在磁盘上（环境全量安装），但被 `skillOverrides` 设为 `"off"`，
在所有配置都不可见。`unassignedSkills` 记录了原因。

| 技能 | 上游 / 最后更新 | 处理 | 理由 |
|---|---|---|---|
| `design` | ninehills vendored copy，最后同步 2026-06-22；Waza 上游 2026-06-27 改名 `ui` | 移除；`/ui` | ninehills Common 安装的是本地 vendored 副本，仍叫 `design`，会和 Claude Code 的 `/design` 名称冲突；Waza 已把上游改名为 `ui`。副本已落后于上游，`/ui` 命令保留设计要点。如果 ninehills 场景更新后安装新的 `ui` 名字，也一并隐藏。 |
| `diagram-design` | ninehills Common 引用 `cathrynlavery/diagram-design`（上游 2026-10-27 活跃） | 移除；可选重装 | **安装布局坏了**：Common 场景把 `diagram-design` 父目录软链接进 `~/.claude/skills`，真正的 `SKILL.md` 在 `diagram-design/diagram-design/`，Claude Code 在顶层找不到，技能实际不会加载。需要时用 openskills 从上游按正确目录重装，或继续用 `drawio-skill`。 |
| `review-code` | ninehills/public-skills，2026-05-24 | 移除；`/review` | 通用代码审查已被 `/review` 覆盖；仓库只有 86 star，5 个月未更新。 |
| `deslop-en` / `deslop-zh` | ninehills/public-skills，2026-05-24 | 移除；`write` 技能 | 去 AI 味的散文润色已由活跃的 `write` 技能覆盖；两个旧技能 5 个月未更新。 |
| `jupytext` | ninehills/public-skills，2026-05-13 | 移除 | 笔记本格式转换是低频工具；模型可以写 notebook，转换命令需要时再装。 |
| `jupyter-notebook` | openai/skills，2026-02-02 | 移除 | 9 个月未更新；笔记本创作不是常驻能力。 |
| `minimax-docx` | minimax-ai/skills，2026-03-23 | 移除 | 7 个月未更新；Office 文档按需使用专用技能/工具，不值得进入 librarian 配置的常驻列表，已隐藏。 |
| `minimax-pdf` | minimax-ai/skills，2026-03-21 | 移除 | 同上。 |
| `minimax-xlsx` | minimax-ai/skills，2026-03-22 | 移除 | 同上。 |
| `pptx-generator` | minimax-ai/skills，2026-03-21 | 移除 | 同上。 |
| `bggg-creator-image2ppt` | binggandata/bggg-skills，2026-05-05 | 移除 | 图片转幻灯片的窄流程；仓库 612 star，5 个月未更新。 |
| `gpt-image-gen` | ninehills/public-skills，2026-05-31 | 隐藏 | 依赖外部 OpenAI key，属于按需能力；保留在磁盘，需要时单独启用。 |
| `fast-rust` | PsiACE/skills，2026-02-05 | 移除；rust 配置 prompt | 9 个月未更新；Rust 惯用法已内化，rust-review 插件负责安全审查。 |
| `piglet` | PsiACE/skills，2026-02-05 | 移除；`/python` | Python 工艺是模型知识；`/python` 保留 uv/ruff/ty 的仓库约束。 |
| `modular-go` | PsiACE/skills，2026-03-07 | 移除；`/go` | Go 模块布局是模型知识；仓库已有 gopls。 |
| `pua` | tanweai/pua，2026-09-09 | 移除 | 仍在维护，但它是“ productivity coaching”类话术，不是工程能力；对日常开发是噪音。 |
| `xurl` | Xuanwo/xurl，2026-03-23 | 移除 | 7 个月未更新，359 star；X API 操作低频，需要时再装。 |
| `brainstorming-cn` | ninehills/public-skills，2026-05-13 | 移除 | 5 个月未更新；活跃的 `think` 技能覆盖“先设计再实现”。 |
| `health` | tw93/Waza，2026-10-29 | 移除；`/setup-audit` | 仍在维护，但与配置审计命令重叠；`/setup-audit` 更聚焦、成本更低。 |
| `better-goal` | ninehills/public-skills（路径存在但无独立提交） | 可选移除 | 目标格式指南与 `think` 和路由 prompt 重叠；保留价值取决于你是否使用 goal 工作流。 |
| `skill-creator`（独立技能） | ninehills Common；插件副本已移除 | 隐藏 | 与 `/skill` 重复；如果保留独立技能，会和插件/命令形成三份。 |

### 真正删除这些技能

openskills 管理的技能（`fast-rust`、`piglet`、`modular-go`、`xurl`）：

```bash
for s in fast-rust piglet modular-go xurl; do
  openskills remove "$s"
done
```

ninehills Common 安装的是 `~/.claude/skills` 下的软链接，`openskills remove` 管不到。
逐项删除时同时处理 `~/.agents/skills` 的链接：

```bash
for s in review-code deslop-en deslop-zh jupytext gpt-image-gen pua \
         brainstorming-cn health design better-goal diagram-design \
         minimax-docx minimax-pdf minimax-xlsx pptx-generator \
         bggg-creator-image2ppt jupyter-notebook skill-creator; do
  rm -rf "$HOME/.claude/skills/$s" "$HOME/.agents/skills/$s"
done
ccr refresh
```

`ninehills/skills` 仓库本身不要删；下次 `scenarios install Common` 会重新建立这些链接。
如果希望镜像层面永久精简，需要改 [Dockerfile](build/Dockerfile) 的 ninehills/openskills
安装步骤，或者在安装后加一个受审计的删除列表。

不要删除 `searching-with-fff`（fff 路由）、`ripwire*`（审查定位）、
`karpathy-guidelines`、`reclaim-code-entropy`、`scoped-change`、`ux-writing`
这些你明确在用的技能。

## 三、建议保留但标注风险的项

| 项 | 日期 | 结论 |
|---|---|---|
| `rust-review` / Trail of Bits 审查插件 | 2026-09-15（批量 metadata）；`static-analysis` 2026-10-23、`regression-hunt` 2026-10-20、`gh-cli` 2026-10-15 有实质更新 | 保留。安全域的工作流/规则不是模型默认知识；已隔离到 `review`；`rust` 只做实现。fp-check 的 Stop hook 只在 review 生效。 |
| `gh-cli` | 2026-10-15 | 保留在 review。它仍会拦截 curl/wget/WebFetch，但只在审查配置；如果不需要，可随 review 配置一起移除。 |
| LSP 插件（gopls/pyright/typescript/rust-analyzer） | 2025-12-19（README/launcher） | 保留。它们是简单 launcher，低 churn；不要用“仓库日期”判断 LSP 本身。 |
| `github` / `linear` 封装 | 2025-12-02 / 2025-12-16 | 保留。封装目录旧，但真正的 MCP 服务由外部维护；如果不用 GitHub/Linear，可直接卸载。 |
| `telegram` | 2026-08-13 | 保留在 router 的 ops 集成；2 个月无更新，但仍是可用的集成。 |
| `session-report` | 2026-04-10 | 可选。只生成报告，不注入 hooks；如果你不看报告就删。 |
| `karpathy-guidelines` | 2026-01-28 | 保留。9 个月未更新，但它是稳定的行为准则，且你明确在用。 |
| `thermos` / `thermo-nuclear-*` | 2026-05-28 | 保留。你的本地审计流程在用；5 个月未更新但仓库仍活跃。 |
| `tdd` / `think` / `hunt` / `read` / `write` / `learn` | 2026-09/10 | 保留。Waza 和 mattpocock/skills 活跃；它们现在是 dev/librarian 的主力技能。 |
| `gh-stack` / `reclaim-code-entropy` / `scoped-change` / `worktree-pr` / `ux-writing` | 2026-08~10 | 保留；你的开发流程明确使用。 |
| `nowledge-mem` / `entire` / `typesafe` | 2026-09~10 | 保留（外部工具/服务）；按需启用，不在路由常驻。 |

## 四、为什么不全量卸载

- 你的要求是“环境可以全量安装，但不同配置预启用不同集合”。因此仓库继续安装全部
  插件/技能，配置层只负责启用集合；这样临时排障、切换配置和回退都不需要重新联网。
- 真正卸载会改变 `claude plugin list`、镜像层和持久化 home 的状态；在没有确认
  “这个插件我半年没用过”之前，默认保留更稳。审计表给出了明确的候选和命令。
- 对真正确定不用的项，建议按 P0 顺序卸载：先移除带 hooks 的（double-shot-latte、
  security-guidance、ralph-loop、remember、modern-python），再移除被命令替代且失修的
  （code-simplifier、claude-md-management、claude-code-setup、skill-creator、
  commit-commands、feature-dev、hookify），最后处理活跃但冗余的
  （code-review、pr-review-toolkit、superpowers）。

## 五、如何持续发现新问题

```bash
ccr doctor --strict
```

它会检查：

- 已安装但未归类的插件/技能（新装的东西不会被静默启用）。
- 配置声称启用但实际未安装的插件。
- fp-check 是否只在 review。
- 生成物是否过期、命令是否安装。
- 用户 settings 中仍会作用于 plain `claude` 的插件，以及旧 user-scope fff 注册。

定期复查上游时，建议只对“当前启用”的 30 个插件看最近实质提交，不要把批量 LICENSE
或 metadata 提交当成活跃信号。本文的方法可以直接复用：`gh api
repos/<owner>/<repo>/commits?path=<path>&per_page=20`，跳过批量提交后取第一条。
