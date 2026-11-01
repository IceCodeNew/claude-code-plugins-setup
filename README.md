# claude-code-plugins-setup

预装 Claude Code、Codex、Chromium、fff MCP、Entire CLI 和可选安全 hooks 的 Linux 开发镜像。按角色隔离插件、技能和 hooks，适合单人使用的 Claude Code 开发机。

## 快速开始

前置条件：Docker Buildx、SSH 客户端和可用的 SSH 公钥。

```bash
docker buildx build --load -t claude-dev --file build/Dockerfile .
docker run -d --name claude-dev -p 8964:8964 \
  -e SSH_AUTHORIZED_KEYS="$(cat ~/.ssh/id_ed25519.pub)" \
  claude-dev
ssh -p 8964 nonroot@localhost
```

容器以 nonroot（UID 65532）运行 sshd，只接受公钥登录。nonroot 有免密 sudo，适合可信开发环境，不用于多租户隔离。

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

路由和子会话默认以 Claude Code 的 `auto` 权限模式运行；`ccr yolo` 把本次路由和它派生的子会话切到 `bypassPermissions`。`ccr spawn --permission-mode <mode>` 可对单次派发覆盖。`auto` 是否可用取决于账号、提供商和模型；不可用时 Claude Code 回退到 Manual。细节见[路由配置](claude-plugins-setup.md#48-路由配置与-ccr)。

本地只读搜索用 `ccr spawn --profile quick --tier medium --read-only`；子会话会禁用 Edit、Write 和 NotebookEdit。

路由每 10 分钟汇总一次进度。不确定的自主决定、卡点的重试顺序、8 分钟等待规则和提问格式统一写在[路由 prompt](build/profiles/prompts/router.md) 的 “Progress, blockers, and questions” 一节。

路由只加载记忆、运维和会话编排插件。`quick` 保留 fff 搜索、ripwire、单文件编辑和命令执行能力，其余角色按需启用实现、审查或写作插件。模型档位见[路由配置](claude-plugins-setup.md#48-路由配置与-ccr)，插件与写作组合见[插件归属](claude-plugins-setup.md#31-插件归属)。

## 功能范围

| 功能 | 说明 |
|---|---|
| 路由与角色 | `ccr` 分发 `quick`、`dev`、`rust`、`go`、`python`、`frontend`、`review`、`librarian`、`oracle`；[配置清单](build/profiles/profiles.json) |
| 角色命令 | `/plan`、`/research`、`/feature`、`/review`、`/security-check`；[命令来源](build/profiles/commands) |
| 审查页面 | `review` 启用 [code-review-page](https://github.com/IceCodeNew/code-review-page-kit)，生成块级 HTML 评审页、diff 注释和复杂度热点 |
| 写作技能 | `writing-*` 按角色启用，技术角色与 `librarian` 使用不同的 genre 和语言组合；[组合](claude-plugins-setup.md#32-写作技能组合) |
| 工具与技能 | mise 管理 CLI，uv 管理共享 Python 环境；独立技能按配置用 `skillOverrides` 隐藏；前端默认使用 [oxc](https://oxc.rs/) 的 `oxlint`/`oxfmt` |
| fff MCP | 所有角色和 router 通过 `--mcp-config` 加载；[作用域与搜索技能](claude-plugins-setup.md#44-fff-mcp-与搜索技能) |
| Entire | 安装 CLI 和官方插件，不自动启用会话记录；[启用与上传范围](claude-plugins-setup.md#45-entire-cli-与官方技能) |
| 安全 hooks | 限制 `rm`、受保护分支写入和 dev server，提供编辑后检查；[按需启停](claude-plugins-setup.md#46-安全-hooks) |
| 文件回收 | 安装 trash-cli；交互式 `rm` 只提示 `trash-put` 并返回失败 |

容器可把 `/home/nonroot` 挂载为卷保留状态。持久卷会遮住新镜像中的工具、插件和技能；升级方法见[持久化 home](claude-plugins-setup.md#49-持久化-home)。

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
