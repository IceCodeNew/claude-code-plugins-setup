# claude-code-plugins-setup

预装 Claude Code、Codex、Chromium、fff MCP、Entire CLI 和默认启用的安全 hooks 的 Linux 开发镜像。每个角色只启用需要的插件和技能，面向可信的单人 Claude Code 开发环境，不用于多租户隔离。

## 快速开始

前置条件：Docker（含 Buildx）、SSH 客户端和 SSH 公钥。

```bash
docker buildx build --load -t claude-dev --file build/Dockerfile .
docker run -d --name claude-dev -p 8964:8964 \
  -e SSH_AUTHORIZED_KEYS="$(cat ~/.ssh/id_ed25519.pub)" \
  claude-dev
ssh -p 8964 nonroot@localhost
```

容器以 nonroot（UID 65532）运行 sshd，只接受公钥登录；nonroot 有免密 sudo。

首次登录后完成[认证](claude-plugins-setup.md#5-登录与认证)，再按[验证](claude-plugins-setup.md#6-验证)检查工具。不使用容器时，从[手动安装](claude-plugins-setup.md#1-系统包和-mise)开始。

## 日常使用

`ccr` 是唯一日常入口，负责意图判断、后台子会话分发和上下文维护。

```bash
ccr                 # 启动路由，默认 auto 权限模式
ccr yolo            # 启动路由，权限模式改为 bypassPermissions
ccr profiles        # 查看配置和插件归属
ccr doctor --strict # 检查配置隔离和生成物
ccr spawn --profile rust --tier easy --name small --prompt-file - <<'PROMPT'
Fix the clippy warning in src/lib.rs. Do not change unrelated code.
PROMPT
ccr summary         # 汇总各子会话进度
```

路由和子会话默认以 `auto` 权限模式运行；`ccr yolo` 切到 `bypassPermissions`，`ccr spawn --permission-mode <mode>` 可单次覆盖。`auto` 不可用时 Claude Code 回退 Manual。细节见[路由配置](claude-plugins-setup.md#48-路由配置与-ccr)。

本地只读搜索用 `ccr spawn --profile quick --tier medium --read-only`；子会话禁用 Edit、Write 和 NotebookEdit。

## 功能范围

| 功能 | 说明 |
|---|---|
| 路由与角色 | `ccr` 分发 `quick`、`dev`、`rust`、`go`、`python`、`frontend`、`review`、`librarian`、`oracle`；[配置清单](build/profiles/profiles.json) |
| 角色命令 | `/plan`、`/research`、`/feature`、`/review`、`/security-check`；[命令来源](build/profiles/commands) |
| 审查页面 | `review` 启用 [code-review-page](https://github.com/IceCodeNew/code-review-page-kit)，生成块级 HTML 评审页、逐块评审备注和复杂度热点 |
| 写作技能 | `writing-tech`、`writing-en`、`writing-zh` 按角色启用；[组合](claude-plugins-setup.md#32-写作技能组合) |
| 工具与技能 | mise 管理 CLI，uv 管理共享 Python 环境；前端默认使用 [oxc](https://oxc.rs/) 的 `oxlint` 和 `oxfmt` |
| fff MCP | 所有角色和 router 都加载，配合 `searching-with-fff` 技能使用；[作用域与搜索技能](claude-plugins-setup.md#44-fff-mcp-与搜索技能) |
| Entire | 安装 CLI 和官方插件，不自动启用会话记录；[启用与上传范围](claude-plugins-setup.md#45-entire-cli-与官方技能) |
| 安全 hooks | 拦截 shell `rm`，阻止直接推送受保护分支，要求 dev server 在 tmux 中运行，并在编辑后检查；[按需启停](claude-plugins-setup.md#46-安全-hooks) |
| 文件回收 | 安装 trash-cli；交互式 `rm` 只提示 `trash-put` 并返回失败 |

把 `/home/nonroot` 挂载为卷可保留状态。持久卷会遮住新镜像中的工具、插件和技能；升级方法见[持久化 home](claude-plugins-setup.md#49-持久化-home)。

## 路由行为

路由为子会话设置任务超时和停滞超时两个软限制，并以 JSONL、ledger 和后台输出作为干预依据。实现角色在完成后做消融，删除不需要的抽象和设计；所有交付物按最终状态写，不提草稿和评审轮次。规则见[路由 prompt](build/profiles/prompts/router.md)。

## 文档

- [安装手册](claude-plugins-setup.md)：工具、插件、技能、MCP、hooks、认证和验证。
- [插件清单](claude-plugins.tsv)：安装状态和配置归属快照，不是版本锁文件。
- [配置清单](build/profiles/profiles.json)：插件、技能、MCP、关键词、模型和 prompt 的单一来源。

## 开发与测试

构建、profile 生成和镜像验证的步骤见 [CONTRIBUTING.md](CONTRIBUTING.md)。
