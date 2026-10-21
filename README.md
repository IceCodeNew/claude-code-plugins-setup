# claude-code-plugins-setup

预装开发工具、Claude Code 插件与技能的 Linux 开发镜像，也提供使用 mise 和 uv 的[手动安装手册](claude-plugins-setup.md)。镜像包含 Claude Code、Codex、Chromium、fff MCP、Entire CLI 和可选安全 hooks；各服务的登录凭据需自行配置。

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

## 使用范围

| 功能 | 默认行为与说明 |
|---|---|
| 工具与技能 | mise 管理命令行工具，uv 管理共享 Python 环境；独立技能链接给 Codex，Claude 插件不跨工具注册 |
| fff MCP | 为 Claude Code 注册本地搜索服务；[作用域、启停与持久化配置修复](claude-plugins-setup.md#44-fff-mcp-与搜索技能) |
| Entire | 通过 mise 安装 CLI 和官方插件，不自动启用会话记录；[启用与上传范围](claude-plugins-setup.md#45-entire-cli-与官方技能) |
| 安全 hooks | 独立 shell 脚本限制 `rm`、受保护分支写入和 dev server，提供编辑后检查；[按需启停与跨 harness 使用](claude-plugins-setup.md#46-安全-hooks) |
| 文件回收 | 安装 trash-cli；交互式 `rm` 仅提醒使用 `trash-put` 并返回失败，不把 `rm` 参数自动改写为回收操作 |

重建容器前可将 `/home/nonroot` 挂载为卷保留状态。持久卷也会遮住新镜像中的工具、插件和技能；升级方法见[持久化 home](claude-plugins-setup.md#持久化-home-的注册修复)。MCP 注册补齐不等于整体升级该卷。

## 安装与构建资料

- [安装手册](claude-plugins-setup.md)：工具、插件、技能、MCP、hooks、认证和验证。
- [插件清单](claude-plugins.tsv)：安装状态快照，不是版本锁文件。
- [Dockerfile](build/Dockerfile)：镜像安装内容和版本的来源。
- [镜像工作流](.github/workflows/build.yml)：构建并验证 `linux/amd64`、`linux/arm64`，按工作流中的标签规则发布。
