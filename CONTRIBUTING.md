# 开发与测试

本仓库的测试不调用模型；它们在隔离目录中检查 profile 生成、命令安装、路由参数、MCP 配置和文档链接。

## 本地检查

运行 Python 测试需要 3.11 或更新版本（`test-docs.py` 使用 `tomllib`）；镜像检查需要 Docker Buildx。

```bash
python3 -B build/test-profiles.py
python3 -B build/test-docs.py
docker buildx build --check --file build/Dockerfile .
```

`test-profiles.py` 在临时目录中生成 profile，不读取或修改本机的 `~/.claude`。

## 完整镜像验证

```bash
docker buildx build --target smoke --file build/Dockerfile .
```

smoke 阶段在 BuildKit 内运行镜像检查；CI 用它验证 `linux/amd64` 和 `linux/arm64`。

## 镜像与生成物

每个 profile 的 settings、prompt、mcp 和 router agent 由 `ccr refresh` 从 [build/profiles](build/profiles) 生成；改动 prompt 或 [profiles.json](build/profiles/profiles.json) 后，运行 `CCR_SOURCE_DIR=build/profiles ccr refresh`。

- [Dockerfile](build/Dockerfile)：镜像安装内容和版本的来源。
- [镜像工作流](.github/workflows/build.yml)：构建并验证 `linux/amd64`、`linux/arm64`，按工作流中的标签规则发布。

## 文档

改动 README、安装手册、本文或链接目标后，运行 `build/test-docs.py`。它检查这三份文档的相对链接和标题锚点。

相关文档：[README](README.md)、[安装手册](claude-plugins-setup.md)。
