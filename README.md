# claude-code-plugins-setup
Claude Code 插件清单，以及用 mise/uv 管理依赖的安装手册

- `claude-plugins-setup.md`：在一台全新机器上手动安装的步骤
- `build/Dockerfile`：同一套环境的 Docker 镜像 `claude-dev`

## claude-dev 镜像

镜像按 `claude-plugins-setup.md` 第 1 到第 4 节构建：mise 工具、共享 Python venv、Claude Code 插件和第三方技能都已装好。插件只装给 Claude Code；技能装在 `~/.claude/skills`，并逐个软链接到 Codex 读取的 `~/.agents/skills`。

容器以 nonroot（uid 65532）运行 sshd，端口 8964，只允许公钥登录。主机密钥在首次启动时生成，保存在 `~/.ssh`。公钥可以通过环境变量 `SSH_AUTHORIZED_KEYS` 传入，也可以直接挂载 `/home/nonroot/.ssh/authorized_keys`。

本地构建：

```bash
docker buildx build --load -t claude-dev --file build/Dockerfile build
```

运行并登录：

```bash
docker run -d --name claude-dev -p 8964:8964 \
  -e SSH_AUTHORIZED_KEYS="$(cat ~/.ssh/id_ed25519.pub)" \
  claude-dev
ssh -p 8964 nonroot@localhost
```

登录 shell 会执行 `mise activate`，所以工具、共享 venv 和 `GITHUB_PERSONAL_ACCESS_TOKEN` 都可用。各插件的登录与认证仍需在容器里手动完成，见 `claude-plugins-setup.md` 第 5 节。要在重建容器后保留登录状态，把 `/home/nonroot` 挂载为卷。

`.github/workflows/build.yml` 在 master 分支上构建 `linux/amd64` 和 `linux/arm64` 镜像，并以 `CLAUDE_CODE_VERSION` 为标签推送到 Docker Hub。版本号由 Renovate 按 `renovate.json` 更新。
