# claude-code-plugins-setup

预装开发工具、Claude Code 插件与技能的 Linux 开发镜像，也提供使用 mise 和 uv 的[手动安装手册](claude-plugins-setup.md)。镜像包含 Claude Code、Codex、Chromium、fff MCP、Entire CLI 和可选安全 hooks；各服务的登录凭据需自行配置。

插件和技能不再全部挂在同一个会话上。日常入口是**路由配置** `ccr`：它判断意图，把任务分发给 `quick`、`dev`、`rust`、`go`、`python`、`review`、`librarian`、`oracle` 中合适的后台子会话，并维护每个子会话的上下文；nmem 记忆和 Cloudflare/Linear/Telegram 等 ops 集成留在路由。完整说明见[路由配置与专业配置](docs/profiles.md)。

## 快速使用

需要 Docker Buildx、SSH 客户端和可用的 SSH 公钥。在仓库根目录构建并启动：

```bash
docker buildx build --load -t claude-dev --file build/Dockerfile .
docker run -d --name claude-dev -p 8964:8964 \
  -e SSH_AUTHORIZED_KEYS="$(cat ~/.ssh/id_ed25519.pub)" \
  claude-dev
ssh -p 8964 nonroot@localhost
```

容器只接受公钥登录，以 nonroot（UID 65532）运行 sshd。nonroot 有免密 sudo，适合作为可信开发环境，不应当作多租户安全隔离。

首次登录后，完成[认证](claude-plugins-setup.md#5-登录与认证)，再按[验证步骤](claude-plugins-setup.md#6-验证)检查工具。无需容器时，从[手动安装](claude-plugins-setup.md#1-系统包和-mise)开始。

## 入口：路由配置

```bash
ccr                 # 启动路由（唯一日常入口）
ccr profiles        # 查看配置和插件归属
ccr doctor --strict # 检查配置隔离和生成物
ccr spawn --profile rust --tier easy --name small --prompt-file - <<'PROMPT'
Fix the clippy warning in src/lib.rs. Do not change unrelated code.
PROMPT
ccr summary         # 汇总各子会话进度
```

路由自己只加载编排工具，不加载领域插件；`fp-check` 这类带全局 hooks 的插件只在
`review` 配置启用。子会话通过 `--setting-sources ""`、各自的 `--settings`、
`--append-system-prompt-file`、`--mcp-config` 和 `--model` 启动，互不继承插件、
技能或 hooks；插件自带的 MCP 随插件启用，路由则用 `--strict-mcp-config` 空配置。模型档位用 `CCR_ROUTER_MODEL` / `CCR_HARD_MODEL` /
`CCR_EASY_MODEL` 覆盖，默认分别是 `haiku`、`opus`、`haiku`。

## 使用范围

| 功能 | 默认行为与说明 |
|---|---|
| 路由配置 | `ccr` 是唯一用户入口；意图判断、后台子会话分发、上下文 ledger、进度汇总，以及 nmem/ops 集成；[配置与命令](docs/profiles.md) |
| 快捷命令 | `/plan`、`/research`、`/simplify`、`/commit`、`/pr`、`/review`、`/security-check` 等 17 个用户命令；替代常驻插件，`disable-model-invocation` 不占模型上下文；[命令表](docs/profiles.md#命令把内化能力做成一次点击) |
| 工具与技能 | mise 管理命令行工具，uv 管理共享 Python 环境；独立技能按配置用 `skillOverrides` 隐藏，不再全部出现在每个会话 |
| Claude 插件 | 只安装一次到 user scope，由各配置的 `enabledPlugins` 启用；[清单](claude-plugins.tsv)最后一列是归属 |
| fff MCP | 只由 `dev` / `rust` / `review` 通过 `--mcp-config` 加载，不再注册到 user scope；[作用域与搜索技能](claude-plugins-setup.md#44-fff-mcp-与搜索技能) |
| Entire | 通过 mise 安装 CLI 和官方插件，不自动启用会话记录；[启用与上传范围](claude-plugins-setup.md#45-entire-cli-与官方技能) |
| 安全 hooks | 独立 Python hooks 限制 `rm`、受保护分支写入和 dev server，提供编辑后检查；按配置注册，`ccr refresh` 尊重用户启停选择；[按需启停与跨 harness 使用](claude-plugins-setup.md#46-安全-hooks) |
| 文件回收 | 安装 trash-cli；交互式 `rm` 仅提醒使用 `trash-put` 并返回失败，不把 `rm` 参数自动改写为回收操作 |

重建容器前可将 `/home/nonroot` 挂载为卷保留状态。持久卷也会遮住新镜像中的工具、插件和技能；升级方法见[持久化 home](claude-plugins-setup.md#持久化-home-的注册修复)。MCP 注册补齐不等于整体升级该卷。启动脚本会运行 `ccr refresh`，让持久化 home 里的配置跟随已安装插件重新生成。

## 安装与构建资料

- [路由配置与专业配置](docs/profiles.md)：隔离原理、配置表、路由协议、上下文管理、迁移和验证。
- [配置审计](docs/audit.md)：不必要/重复/失修插件与技能的详细理由、最后维护日期和卸载命令。
- [安装手册](claude-plugins-setup.md)：工具、插件、技能、MCP、hooks、认证和验证。
- [插件清单](claude-plugins.tsv)：安装状态和配置归属快照，不是版本锁文件。
- [配置清单](build/profiles/profiles.json)：插件、技能、MCP、关键词、模型和 prompt 的单一来源。
- [Dockerfile](build/Dockerfile)：镜像安装内容和版本的来源。
- [镜像工作流](.github/workflows/build.yml)：构建并验证 `linux/amd64`、`linux/arm64`，按工作流中的标签规则发布。
