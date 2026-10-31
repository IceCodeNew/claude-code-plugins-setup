# claude-code-plugins-setup

预装开发工具、Claude Code 插件与技能的 Linux 开发镜像，附带使用 mise 和 uv 的[手动安装手册](claude-plugins-setup.md)。镜像包含 Claude Code、Codex、Chromium、fff MCP、Entire CLI 和可选安全 hooks；各服务的登录凭据需自行配置。

它适合想要一台**开箱即用、可按角色隔离插件与 hooks** 的 Claude Code 开发机的用户。日常只进入一个路由配置 `ccr`，由它把任务分给 `quick`、`dev`、`rust`、`go`、`python`、`frontend`、`review`、`librarian`、`oracle`、`finder` 等后台子会话，并维护每个子会话的上下文。

## 快速使用

前置条件：Docker Buildx、SSH 客户端和可用的 SSH 公钥。

```bash
docker buildx build --load -t claude-dev --file build/Dockerfile .
docker run -d --name claude-dev -p 8964:8964 \
  -e SSH_AUTHORIZED_KEYS="$(cat ~/.ssh/id_ed25519.pub)" \
  claude-dev
ssh -p 8964 nonroot@localhost
```

容器只接受公钥登录，以 nonroot（UID 65532）运行 sshd。nonroot 有免密 sudo，适合作为可信开发环境，不应作为多租户安全隔离。

首次登录后完成[认证](claude-plugins-setup.md#5-登录与认证)，再按[验证步骤](claude-plugins-setup.md#6-验证)检查工具。无需容器时，从[手动安装](claude-plugins-setup.md#1-系统包和-mise)开始。

## 日常入口

```bash
ccr                 # 启动路由（唯一日常入口）
ccr profiles        # 查看配置和插件归属
ccr doctor --strict # 检查配置隔离和生成物
ccr spawn --profile rust --tier easy --name small --prompt-file - <<'PROMPT'
Fix the clippy warning in src/lib.rs. Do not change unrelated code.
PROMPT
ccr summary         # 汇总各子会话进度
```

路由自己只加载记忆、运维和会话编排插件，不加载实现类领域插件；`fp-check` 这类带全局 hooks 的插件只在 `review` 配置启用。路由和子会话统一用 `--setting-sources user` 加载 `~/.local/state/cc-router/claude/`（由 `ccr refresh` 生成）：其中 `settings.json` 只保留 `theme` 等少量偏好、不复制用户设置，`skills`、`commands`、`agents`、`plugins`、`.credentials.json` 指向真实 `~/.claude`，`.claude.json` 只保留 project trust 并清空 user MCP。各自的 `--settings`、`--append-system-prompt-file`、`--mcp-config` 和 `--model` 继续按 profile 覆盖，所以用户 `settings.json` 和 user MCP 不会进入会话，而命令和 standalone skills 可用；`ccr-router` 通过 `agents` 符号链接加载，`--agents` 内联定义作为兜底。

模型档位通过环境变量覆盖：

| 档位 | 默认 | 典型角色 |
|---|---|---|
| `CCR_ROUTER_MODEL` | `haiku` | 路由本身 |
| `CCR_EASY_MODEL` | `haiku` | `quick`、`librarian` |
| `CCR_MEDIUM_MODEL` | `sonnet` | `finder` |
| `CCR_HARD_MODEL` | `opus` | `oracle`、`dev`、`review` 等 |

## 使用范围

| 功能 | 默认行为与说明 |
|---|---|
| 路由配置 | `ccr` 是唯一用户入口；负责意图判断、后台子会话分发、上下文 ledger、进度汇总，以及 nmem/ops 集成；[配置清单](build/profiles/profiles.json) |
| 角色命令 | `/plan`、`/research`、`/feature`、`/review`、`/security-check`；模型和用户都可调用；[命令来源](build/profiles/commands) |
| 审查页面 | `review` 角色启用 [code-review-page](https://github.com/IceCodeNew/code-review-page-kit)，可生成块级 HTML 评审页、diff 注释、复杂度热点和英文实现提示 |
| 工具与技能 | mise 管理命令行工具，uv 管理共享 Python 环境；独立技能按配置用 `skillOverrides` 隐藏；前端角色默认使用 [oxc](https://oxc.rs/) 的 `oxlint`/`oxfmt` |
| Claude 插件 | 只安装一次到 user scope，由各配置的 `enabledPlugins` 启用；[清单](claude-plugins.tsv)的最后一列是归属 |
| fff MCP | 所有角色和 router 都通过 `--mcp-config` 加载；不注册到 user scope；[作用域与搜索技能](claude-plugins-setup.md#44-fff-mcp-与搜索技能) |
| Entire | 通过 mise 安装 CLI 和官方插件，不自动启用会话记录；[启用与上传范围](claude-plugins-setup.md#45-entire-cli-与官方技能) |
| 安全 hooks | 独立 Python hooks 限制 `rm`、受保护分支写入和 dev server，提供编辑后检查；按配置注册，`ccr refresh` 尊重用户启停选择；[按需启停与跨 harness 使用](claude-plugins-setup.md#46-安全-hooks) |
| 文件回收 | 安装 trash-cli；交互式 `rm` 仅提醒使用 `trash-put` 并返回失败，不把 `rm` 参数自动改写为回收操作 |

重建容器前可将 `/home/nonroot` 挂载为卷保留状态。持久卷也会遮住新镜像中的工具、插件和技能；升级方法见[持久化 home](claude-plugins-setup.md#持久化-home-的注册修复)。MCP 注册补齐不等于整体升级该卷。启动脚本会运行 `ccr refresh`，让持久化 home 里的配置跟随已安装插件重新生成。

## 文档

- [安装手册](claude-plugins-setup.md)：工具、插件、技能、MCP、hooks、认证和验证。
- [插件清单](claude-plugins.tsv)：安装状态和配置归属快照，不是版本锁文件。
- [配置清单](build/profiles/profiles.json)：插件、技能、MCP、关键词、模型和 prompt 的单一来源。
- [Dockerfile](build/Dockerfile)：镜像安装内容和版本的来源。
- [镜像工作流](.github/workflows/build.yml)：构建并验证 `linux/amd64`、`linux/arm64`，按工作流中的标签规则发布。

## 开发与验证

本仓库的测试不调用模型；它们在隔离目录中检查 profile 生成、命令安装、路由参数、MCP 配置和文档链接。

```bash
python3 -B build/test-profiles.py
python3 -B build/test-docs.py
docker buildx build --check --file build/Dockerfile .
```

完整镜像验证：

```bash
docker buildx build --target smoke --file build/Dockerfile .
```
