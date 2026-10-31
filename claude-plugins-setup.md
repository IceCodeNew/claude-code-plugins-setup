# Claude Code 插件与依赖安装手册

本手册面向 Linux 手动安装；镜像用户可直接查看[登录与认证](#5-登录与认证)、[验证](#6-验证)和[安全 hooks](#46-安全-hooks)。容器构建与启动命令见 [README](README.md#快速使用)。

| 安装内容 | 管理方式 |
|---|---|
| 命令行工具 | mise；手动步骤通常跟随上游最新版本，镜像版本以 [Dockerfile](build/Dockerfile) 为准 |
| Python 依赖 | uv 共享 venv；镜像的安全 hooks 复用系统 Python，仅补充 Bash 解析器，不依赖插件 venv |
| Claude 插件 | user-scope marketplace 安装一次，由 `ccr` 配置按需启用；[清单](claude-plugins.tsv)最后一列是归属，非版本锁文件 |
| 独立技能 | 安装到 `~/.claude/skills`，镜像逐个链接到 Codex 使用的 `~/.agents/skills` |

新机器按第 1 至第 6 节执行。已有配置需合并而非覆盖；代码块可能依赖前面的环境、当前目录和认证。从仓库引用脚本时，先定位到 checkout 根目录。

- [系统包与 mise](#1-系统包和-mise)
- [工具及 Python 环境](#2-mise-配置)
- [Claude 插件](#3-添加-marketplace-并安装插件)
- [技能、MCP、Entire 与 hooks](#4-第三方技能)
- [路由配置与 ccr](#48-路由配置与-ccr)
- [认证](#5-登录与认证)与[验证](#6-验证)

---

## 1. 系统包和 mise

mise registry 里没有 git 和 lsof。curl 用来装 mise 本身。Debian、Ubuntu、Fedora 都自带 perl，不用另装。

```bash
# Debian / Ubuntu
sudo apt update && sudo apt install -y git curl lsof tmux trash-cli
# Fedora
# sudo dnf install -y git curl lsof tmux trash-cli
```

### 1.1 文件回收与交互式别名

trash-cli 的正式回收命令为 `trash-put`，恢复使用 `trash-restore`。[官方 FAQ](https://github.com/andreafrancia/trash-cli#can-i-alias-rm-to-trash-put) 不建议将 `rm` 直接指向 `trash-put`：二者语义不同，例如回收目录不要求 `-r`。这里采用提醒式别名，交互式输入 `rm` 会显示替代命令并返回失败。

将下面一行加入 `~/.bashrc`；使用 Zsh 时加入 `~/.zshrc`：

```bash
alias rm='printf "%s\n" "Use trash-put -- <path>; trash-restore recovers files." >&2; false'
```

重新打开交互 shell 后生效。非交互脚本不依赖该别名；agent 的 `rm` 限制由[安全 hook](#46-安全-hooks)执行。回收和恢复使用：

```bash
trash-put -- path/to/file
trash-list
trash-restore
```

不要把 `trash-empty` 或 `trash-rm` 当成回收命令，它们会从回收站永久删除内容。本配置不自动清空回收站。

### 1.2 安装 mise

安装 mise 并在 shell 里激活：

```bash
curl https://mise.run | sh
echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bashrc
exec bash
```

> Claude Code 执行 hook 和 LSP 时靠 PATH 找命令。启动 `claude` 的那个 shell 必须已经激活 mise，否则会找不到工具。

---

## 2. mise 配置

分两步写配置：先写 `[tools]` 并安装，再追加 `[env]`。`[env]` 里的 venv 由 mise 调用 uv 创建，要等 uv 装好之后再加。

如果 `~/.config/mise/config.toml` 已经存在，不要直接覆盖，把下面的条目合并进去。

### 2.1 工具

| 条目 | 用途 |
|---|---|
| `node = "26"` | firecrawl 的 npx 兜底、superpowers、claude-session-driver、pyright 运行时、modern-web-guidance |
| `bun` | telegram 的 stdio MCP |
| `uv` | 创建和管理共享 Python venv（2.2 节） |
| `gh`、`jq` | commit-commands、coderabbit、remember |
| `claude-code` | Claude Code 本身；remember、security-guidance 也会调用 `claude` |
| `go`、`"go:golang.org/x/tools/gopls"` | gopls-lsp |
| `rust`（带 `rust-src`、`rust-analyzer` 组件） | rust-analyzer-lsp。mise 按 minimal profile 装的 rust 没有 rust-src，rust-analyzer 无法分析标准库；rust-analyzer 用 rustup 组件，版本和工具链一致 |
| `"npm:typescript" = "6"` | typescript 7 是 Go 原生版，包里没有 `tsserver.js`，typescript-language-server 6.0.0 用不了 |
| `"npm:typescript-language-server"` | typescript-lsp。见下方说明 |
| `"npm:firecrawl-cli"` | firecrawl |
| `"npm:cf"` | Cloudflare cf CLI，调用 Cloudflare API、开发和部署 Workers（公开测试版） |
| `"pypi:nmem-cli"` | nowledge-mem 的 hook 和命令 |
| `"npm:openskills"` | 第 4 节安装第三方技能 |
| `"npm:oxlint"` / `"npm:oxfmt"` | 前端角色默认的 oxc lint/format 工具链 |
| `"github:redhat-et/ripwire"` | ripwire CLI，压缩包里带有第 4 节安装的 ripwire 技能 |
| `pnpm` | 可选，modern-web-guidance 有 pnpm 时用 `pnpx` |
| `http:coderabbit` | coderabbit CLI（下面的 URL 为 linux-x64 包） |

typescript-language-server 先找项目里的 `node_modules/typescript`，找不到时从自己的安装目录解析 typescript。mise 的 npm 工具各自独立安装，因此用 `postinstall` 在它的 `node_modules` 里建立指向 typescript 6 的软链接，`depends` 保证 typescript 先装好。

```bash
mkdir -p ~/.config/mise
cat > ~/.config/mise/config.toml <<'EOF'
[tools]
node = "26"
bun = "latest"
uv = "latest"
gh = "latest"
jq = "latest"
pnpm = "latest"
claude-code = "latest"
go = "latest"
"go:golang.org/x/tools/gopls" = "latest"
rust = { version = "latest", components = ["rust-src", "rust-analyzer"] }
"npm:typescript" = "6"
"npm:typescript-language-server" = { version = "latest", depends = ["npm:typescript"], postinstall = 'ln -sfn "$HOME/.local/share/mise/installs/npm-typescript/6/node_modules/typescript" "$MISE_TOOL_INSTALL_PATH/node_modules/typescript"' }
"npm:firecrawl-cli" = "latest"
"npm:cf" = "latest"
"pypi:nmem-cli" = "latest"
"npm:openskills" = "latest"
"npm:oxlint" = "latest"
"npm:oxfmt" = "latest"
"github:redhat-et/ripwire" = "latest"

[tools."http:coderabbit"]
version = "latest"
url = "https://cli.coderabbit.ai/releases/{{ version }}/coderabbit-linux-x64.zip"
version_list_url = "https://cli.coderabbit.ai/releases/latest/VERSION"
EOF

mise install
```

Cloudflare 在 [cf 发布文章](https://blog.cloudflare.com/cloudflare-cf-cli-launch/)中介绍了面向 Agent 的命令搜索 `cf cli search`、默认 JSON 输出和 `cloudflare.config.ts` 配置。[官方仓库](https://github.com/cloudflare/cf)的安装命令是 `npm i -g cf`；这里用 mise 的 `npm:cf` 管理同一个包，要求 Node.js 22 或更高版本。Dockerfile 固定 cf 版本并由 Renovate 更新。

Wrangler 仍按下面的方式按需安装；现有 wrangler skill 和尚未迁移的项目仍可能使用它。

可选工具（按需添加）：

```bash
mise use -g wrangler@latest        # cloudflare 插件的 wrangler skill；skill 优先用项目本地的 wrangler
mise use -g cloudflared@latest     # 只在 cloudflare 的 tunnel 参考文档里出现
mise use -g conda:graphviz@latest  # superpowers 的 render-graphs.js 生成 SVG 用
```

coderabbit 的 skill 示例里用了 `cr` 命令，但 mise 装的 zip 里只有 `coderabbit`。主流程不受影响，想要的话在 shell 里加一行：

```bash
echo "alias cr=coderabbit" >> ~/.bashrc
```

### 2.2 环境变量和共享 Python venv

三个插件和一个技能需要第三方 Python 包，全部装进同一个 uv venv：

| 插件 | 包 | 怎么用到这个 venv |
|---|---|---|
| security-guidance | claude-agent-sdk | hook 用 `sg-python.sh` 按 python3.13 → 3.10 → python3 的顺序找解释器。venv 激活后找到的是 venv 里的 python3.13，SDK 可以直接 import。另外把 `~/.claude/security/agent-sdk-venv` 软链接到这个 venv，claude 不在激活了 mise 的 shell 里启动时也能用 |
| pyright-lsp | pyright | venv 的 `bin/` 里有 `pyright-langserver`，运行时用 mise 的 node |
| read 技能（第 4 节） | readability-lxml、html2text | 本地网页正文提取；缺少时退回标准库解析，输出质量较差 |

venv 的 Python 固定为 3.13：`sg-python.sh` 只探测 python3.13 到 3.10 这几个带版本号的名字，3.14 会被跳过。`create = true` 时 mise 调用 uv 建 venv，系统里没有 3.13 的话 uv 会自己下载。

`GITHUB_PERSONAL_ACCESS_TOKEN` 给 github MCP 用，从 gh 的登录 token 读取；gh 未安装或未登录时取值为空，不影响 mise 正常工作。也可以在 shell 配置里 `export GITHUB_PERSONAL_ACCESS_TOKEN="$(gh auth token)"`，两处只保留一处。

```bash
cat >> ~/.config/mise/config.toml <<'EOF'

[env]
# Claude 插件共用的 uv venv（security-guidance、pyright-lsp），mise 激活时自动创建并加入 PATH
_.python.venv = { path = "{{ env.HOME }}/.local/share/claude-plugins-venv", create = true, python = "3.13" }
# github MCP 用；从 mise 装的 gh 读取登录 token，gh 未安装或未登录时为空
GITHUB_PERSONAL_ACCESS_TOKEN = "{{ exec(command='for g in $HOME/.local/share/mise/installs/gh/latest/*/bin/gh; do $g auth token 2>/dev/null || true; done') }}"
# 可选：提高 context7 的速率限制
# CONTEXT7_API_KEY = "ctx7sk-..."
EOF

exec bash   # 重新激活 mise，venv 在这一步创建

V=~/.local/share/claude-plugins-venv
uv pip install --python "$V/bin/python" claude-agent-sdk pyyaml pyright readability-lxml html2text

# security-guidance 的回退路径指向共享 venv
mkdir -p ~/.claude/security
[ -L ~/.claude/security/agent-sdk-venv ] || rm -rf ~/.claude/security/agent-sdk-venv
ln -sfn "$V" ~/.claude/security/agent-sdk-venv
```

以后升级这几个包：

```bash
uv pip install --python ~/.local/share/claude-plugins-venv/bin/python -U claude-agent-sdk pyyaml pyright readability-lxml html2text
```

副作用：`_.python.venv` 写在全局配置里，所有激活了 mise 的 shell 都会激活这个 venv。`python`、`python3` 都指向它，`VIRTUAL_ENV` 也会被设置。在别的 uv 项目里跑 `uv` 时，它会提示 `VIRTUAL_ENV` 和项目的 `.venv` 不一致并忽略它，不影响结果。venv 的 `bin/` 里还有 SDK 依赖带进来的 `mcp`、`uvicorn`、`httpx2` 等命令，也会出现在 PATH 上。

由 IDE 等不经过 `mise activate` 的方式启动 claude 时，venv 不在 PATH 上：security-guidance 通过软链接仍可使用，pyright-lsp 的 `python` 则找不到。

---

## 3. 添加 marketplace 并安装插件

scope 默认是 user。

```bash
claude plugin marketplace add anthropics/claude-plugins-official
claude plugin marketplace add https://github.com/nowledge-co/community.git
claude plugin marketplace add pydantic/skills
claude plugin marketplace add JetBrains/go-modern-guidelines
claude plugin marketplace add obra/superpowers-marketplace
claude plugin marketplace add typesafe-ai/skills
claude plugin marketplace add trailofbits/skills
claude plugin marketplace update
```

安装以下插件，Entire 官方插件在 [4.5 节](#45-entire-cli-与官方技能)安装：

```bash
for p in \
  claude-code-setup claude-md-management claude-security cloudflare code-simplifier \
  coderabbit commit-commands context7 firecrawl github gopls-lsp hookify linear \
  modern-web-guidance pyright-lsp redis-development remember rust-analyzer-lsp \
  security-guidance skill-creator superpowers telegram typescript-lsp
do
  claude plugin install "$p@claude-plugins-official" --scope user
done
claude plugin install nowledge-mem@nowledge-community --scope user
claude plugin install pydantic@pydantic-skills --scope user
claude plugin install modern-go-guidelines@goland-claude-marketplace --scope user
claude plugin install claude-session-driver@superpowers-marketplace --scope user
claude plugin install typesafe@typesafe-ai --scope user
```

安装 [Trail of Bits 插件](https://github.com/trailofbits/skills)：

```bash
for p in \
    agentic-actions-auditor audit-context-building differential-review fp-check gh-cli \
    insecure-defaults modern-python regression-hunt review-walkthrough rust-review \
    sharp-edges static-analysis supply-chain-risk-auditor variant-analysis vulnerability-triage-brocards
do
    claude plugin install "$p@trailofbits" --scope user
done
```

插件保留上游名称，通过完整 ID 中的 `@trailofbits` 区分来源，例如 `differential-review@trailofbits`，技能用 `/differential-review:differential-review` 调用。更新时运行 `claude plugin marketplace update trailofbits` 和 `claude plugin update <插件名>@trailofbits`；在 `/plugin` 的 Marketplaces 中为 `trailofbits` 开启 auto-update 后可自动更新，无需本地转换。

`fp-check` 包含 Stop 和 SubagentStop prompt hooks，可能增加模型调用费用；本仓库只在
`review` 配置启用它，路由和其他配置不会加载。`gh-cli` 的 hooks 会拦截 GitHub 网页抓取及
curl/wget 请求，改用 `gh`，并通过 PATH shim 限制部分 `gh` 用法；它只在 `review` 配置启用。
认证见[登录与认证](#5-登录与认证)。会话结束时会删除该会话的 `gh-clones-<session_id>`
临时克隆目录，其中的修改也会丢失，需保留的工作应放在其他目录。

`modern-python` 会添加 PATH shims，拦截直接运行的 python/pip/pipx/uv-pip 命令并提示改用 uv；它只在 `python` 角色启用，review 不重复启用。CodeQL、Semgrep 等分析工具按任务需要另行安装，安装插件不会安装这些工具。

`claude-session-driver` 使用 tmux 启动 worker；首次启动前需从其 `driving-claude-code-sessions` 技能目录运行 `scripts/csd grant-consent`，其 worker 会跳过权限确认。安装并启用插件本身不会启动 worker。

`typesafe` 来自 [TypeSafe 官方技能仓库](https://github.com/typesafe-ai/skills)，为 Claude Code 提供 TypeSafe API 的使用说明；可用 `/typesafe:typesafe-ai` 调用。更新时运行 `claude plugin marketplace update typesafe-ai` 和 `claude plugin update typesafe@typesafe-ai`。使用 TypeSafe API 时需另行配置 API key，安装插件无需 API key。

在脚本或管道里跑、stdin/stdout 不是终端时，给需要确认的安装加 `-y`。

`modern-web-guidance` 只由 frontend 配置启用；为 plain `claude` 保持禁用：

```bash
for p in redis-development modern-web-guidance; do
  claude plugin disable "$p@claude-plugins-official" --scope user
done
```

### 3.1 插件归属

插件只安装一次（user scope）。每个插件在
[profiles.json](build/profiles/profiles.json) 里归入一个或多个配置；运行
[4.8 的 `ccr refresh`](#48-路由配置与-ccr) 后，每个配置的 `settings.json` 会显式禁用
其他插件并启用自己的插件。44 个插件都有归属：42 个按角色启用，`skill-creator`、`redis-development` 保留原禁用状态。

插件与技能的维护状态、最后维护日期和卸载命令见[配置审计](docs/audit.md)和
[命令替代证据](docs/command-replacements.md)。

环境安装 44 个插件（42 启用、2 禁用）。这样临时启用、排障和切换配置都不需要重新联网；配置层只决定
`enabledPlugins` 和 `skillOverrides`。镜像只包含清单中的插件；未列出的插件不存在。

评审、计划、研究、hook/skill 创建等流程被做成 `~/.claude/commands/` 下的命令，
例如 `/plan`、`/research`、`/feature`、`/review`、`/security-check`。命令正文是流程和验证要求；它们是模型可调用的角色命令（例如 librarian 用
`/research`，oracle 用 `/plan`，review 用 `/review` 和 `/security-check`），
也可以由用户直接输入。router 需要使用 session-driver、remember 和 nmem 的技能，因此不启用 `--disable-slash-commands`。
session-driver/remember/nmem 的技能；实现类命令由 prompt 和 `disallowedTools` 限制。`ccr refresh` 会把
[build/profiles/commands](build/profiles/commands) 同步到 `~/.claude/commands/`；
同名但非 ccr 生成的文件会跳过并告警，不会覆盖用户自定义命令。

这不是简单的「按需 `/plugin` 开关」：`ccr` 启动子会话时用 `--setting-sources ""`
忽略用户 settings，再用 `--settings <profile>` 覆盖 `enabledPlugins`，所以专业配置的
hooks 不会泄漏到路由或其他配置。`fp-check` 只在 `review` 配置启用，路由、`dev`、
`rust` 等会话不会加载它的 `Stop` / `SubagentStop` prompt hook。

清单中的版本列只供核对，下面命令不据此锁定版本。使用清单批量安装前，应先添加对应 marketplace：

```bash
cut -f1 claude-plugins.tsv | xargs -n1 claude plugin install --scope user
```

核对：

```bash
claude plugin list
```

---

## 4. 第三方技能

除下文明确固定的 fff 安装器和搜索技能外，技能通常跟随上游默认分支。保留的技能都从各自上游直装；ripwire 的技能用 ripwire 发布包自带的安装脚本；其余用 openskills 装到 `~/.claude/skills`（`-g` 为全局，`-y` 跳过交互选择）。ninehills 只保留其自有的 `tech-doc-style-chinese`。pydantic 和 modern-go-guidelines 以插件形式提供，已在第 3 节安装。

Cloudflare CLI 与技能分开安装。Cloudflare 在 [cloudflare/skills](https://github.com/cloudflare/skills) 维护平台技能，第 3 节的 `cloudflare@claude-plugins-official` 已从该仓库安装，包含 cloudflare、wrangler、agents-sdk 等技能，本节不重复安装。该插件只供 Claude Code 使用，不会通过镜像的 `~/.agents/skills` 软链接提供给 Codex。使用 cf 时先运行 `cf --help`、`cf cli search "任务"` 发现命令。

### 4.1 上游直装

早期用 `ninehills/skills` 的 `skills-manager scenarios install Common` 整组安装 34 个
技能。Common 是 vendored 副本集合：`design` 已在上游改名 `ui`；`diagram-design`
的父目录软链接导致顶层没有 `SKILL.md`，实际不会加载；不需要的技能也会进入
`~/.claude/skills`。本仓库已移除 Common 安装，改为只从上游直装保留的技能（4.3）。

| 保留技能 | 上游 | 位置 |
|---|---|---|
| `check`、`health`、`hunt`、`learn`、`read`、`think`、`ui`、`write` | tw93/Waza | 完整安装；`ui` 在 frontend，`check` 在 review，`health` 在 dev，其余在 dev/librarian/oracle |
| `tdd` | mattpocock/skills | dev |
| `karpathy-guidelines` | forrestchang/andrej-karpathy-skills | dev / oracle |
| `tech-doc-style-chinese` | ninehills/skills（自有，vendor） | librarian |
| `japanese-tech-writing` | 上游 gist | librarian |
| `fast-rust`、`piglet`、`modular-go`、`friendly-python` | PsiACE/skills | 开发角色：rust / python / python / python；review 不重复 |
| `code-review-page` | IceCodeNew/code-review-page-kit | review |

`tw93/Waza` 以仓库为单位安装，包含该仓库全部 8 个技能；tdd、karpathy-guidelines 从各自上游安装；ninehills 只提供自有 `tech-doc-style-chinese`。更新使用 `openskills update`，不需要克隆 ninehills 仓库或运行 `skills-manager`。

### 4.2 ripwire 技能（官方 skills/install.sh）

mise 安装的 ripwire 压缩包里带有 `skills/` 目录和 `skills/install.sh`。脚本把每个 `ripwire*` 技能软链接进 `~/.claude/skills`，链接目标是脚本所在的目录。通过 mise 的 `latest` 路径执行，链接就指向 `latest`，`mise upgrade` 之后仍然有效。`ripwire-opt-remarks` 只用于开发 ripwire 本身，脚本默认跳过。

```bash
bash ~/.local/share/mise/installs/github-redhat-et-ripwire/latest/skills/install.sh
```

ripwire 升级后技能列表可能变化，重新执行同一条命令即可：新技能会建立链接，上游删掉的技能会被清理。

### 4.3 其余技能（openskills）

`code-review-page` 的仓库根目录直接有 `SKILL.md`，openskills 会按其中的 `name`
安装为 `code-review-page`；它只应在 review 角色启用。

```bash
cd ~
for s in \
  IceCodeNew/code-review-page-kit \
  tw93/Waza \
  mattpocock/skills/skills/engineering/tdd \
  forrestchang/andrej-karpathy-skills/skills/karpathy-guidelines \
  PsiACE/skills/skills/fast-rust \
  PsiACE/skills/skills/friendly-python \
  PsiACE/skills/skills/modular-go \
  PsiACE/skills/skills/piglet \
  github/gh-stack/skills/gh-stack \
  Yevanchen/reclaim-code-entropy/skills/reclaim-code-entropy \
  scarletkc/agents/skills/scoped-change \
  scarletkc/agents/skills/ux-writing \
  scarletkc/agents/skills/worktree-pr \
  cursor/plugins/thermos/skills/thermos \
  cursor/plugins/thermos/skills/thermo-nuclear-review \
  cursor/plugins/thermos/skills/thermo-nuclear-code-quality-review \
  ninehills/skills/tech-doc-style-chinese \
  openclaw/openclaw/.agents/skills/test-audit \
  tommy0103/better-readme-skill/skills/better-readme \
  https://gist.github.com/k16shikano/fd287c3133457c4fd8f5601d34aa817d.git
do
  openskills install "$s" -g -y
done
missing=0
for s in check health ui; do
  test -f ~/.claude/skills/"$s"/SKILL.md || {
    echo "missing Waza skill: $s" >&2
    missing=1
  }
done
if [ "$missing" = 0 ]; then
  ccr refresh --strict
else
  echo "install the missing Waza skills, then run: ccr refresh --strict" >&2
fi
```

更新全部 openskills 技能：

```bash
openskills update
```

技能依赖的命令：

| 技能 | 依赖 | 安装 |
|---|---|---|
| gh-stack | `gh stack` | gh 扩展，见下方命令 |
| read | readability-lxml、html2text | 共享 uv venv（2.2 节已包含） |

```bash
gh extension install github/gh-stack
```

### 4.4 fff MCP 与搜索技能

[fff](https://github.com/dmtrKovalenko/fff) 提供本地文件查找和内容搜索。这里采用 fff 官方 MCP；社区技能和 `routing.md` 统一在 [IceCodeNew/searching-with-fff](https://github.com/IceCodeNew/searching-with-fff) 维护，本仓库只负责安装。通用技能目录不含 Amp 专属说明或配置；Amp 的 adapter 单独位于独立仓库的 `amp/`，其他 harness 不安装它。Claude Code 的具体操作保留在本安装手册中。

官方安装脚本只安装二进制并打印注册建议，不会自动注册 MCP 或更改 Claude 的工具选择。下面固定已审查的官方脚本 commit 和 SHA256；脚本内固定 v0.11.0，并校验对应平台的二进制。Linux amd64/arm64 使用静态 musl 可执行文件，不需要再装 Rust 或 Python/Node 搜索绑定。升级时要重新审查脚本和内置版本、校验值，不能只替换 URL。

```bash
(
  set -euo pipefail
  installer=$(mktemp "${TMPDIR:-/tmp}/install-fff.XXXXXXXX.sh")
  trap 'rm -f "$installer"' EXIT
  curl -fsSL https://raw.githubusercontent.com/dmtrKovalenko/fff/c188e7a8f90e4ee4aabe18f93d5869dfb4289f12/install-mcp.sh -o "$installer"
  printf '%s  %s\n' 510ecb5a5151ded8f08efedfc73898464a8470ed8c256853db31a19216a25546 "$installer" | sha256sum -c -
  bash "$installer"
)
"$HOME/.local/bin/fff-mcp" --version
# fff 不注册到 user scope；4.8 的 ccr refresh 会把它写进每个角色和 router 的 mcp.json
```

技能与镜像均使用下面固定提交的安装步骤。镜像固定 `FFF_SKILL_REVISION=6c2e4675ffe7635e02f5d4f9c6b4793b4863b151`（已合入技能仓库 master），只复制通用子目录，不安装 Amp adapter。要手动复现镜像的技能版本：

```bash
(
  set -euo pipefail
  checkout=$(mktemp -d "${TMPDIR:-/tmp}/fff-skill.XXXXXXXX")
  trap 'rm -rf "$checkout"' EXIT
  git -C "$checkout" init -q
  git -C "$checkout" fetch --depth 1 https://github.com/IceCodeNew/searching-with-fff.git 6c2e4675ffe7635e02f5d4f9c6b4793b4863b151
  git -C "$checkout" checkout --detach -q FETCH_HEAD
  test "$(git -C "$checkout" rev-parse HEAD)" = 6c2e4675ffe7635e02f5d4f9c6b4793b4863b151
  openskills install "$checkout/searching-with-fff" -g -y
)
```

MCP 使用绝对二进制路径，所以不依赖 PATH。不要给服务传构建目录或某个固定仓库路径：fff 默认搜索启动目录，Git 子目录会解析到当前 worktree 根；工具参数不能切换到另一个仓库。通过 `ccr spawn --profile dev|rust|go|python|frontend|review|librarian|oracle|finder` 在目标 worktree 里启动子会话，用 `/mcp` 检查 `fff` 是否 connected，用 `/skills` 检查 `searching-with-fff`，也可以显式调用 `/searching-with-fff`。所有角色和 router 都加载 fff；它比反复 grep 更快，成本低于模型默认的多轮搜索。

技能 description 用于模型判断是否需要加载技能；正文选择 fff server 的 `find_files`、`grep` 或 `multi_grep`，并要求解析宿主暴露的工具名前缀（Claude Code 中为 `mcp__fff__*`），细节放在按需读取的 `routing.md`。这些都是引导，不是强制工具拦截，也不保证每次自动触发。连接失败时技能要求报告问题，不静默换成 grep/rg 或自制扫描器。本节不新增 hooks、不修改 `CLAUDE.md`、不设置全局 MCP 加载环境变量。

#### 减少无关会话的影响

Claude Code 没有像 skill description 那样按关键词或行为自动启用单个 MCP server 的官方机制。MCP 注册、连接和工具定义加载是不同阶段：

| 方法 | 能解决什么 | 限制 |
|---|---|---|
| local/project scope | 只在所选项目提供 fff，避免其他项目加载 | local 私有配置保存在 `~/.claude.json` 的项目记录；project 写入 `.mcp.json`，需要项目信任/审批 |
| `/mcp` 中 Disable/Enable | user-scope 服务按项目持久禁用，需要时重新启用 | skill 不会自行启用被禁用的 server |
| Tool Search | 按需加载完整工具定义 | 工具名称和 server instructions 仍会加载；自定义 API 地址默认回退到预加载，代理必须兼容 tool reference 才能开启 |
| `MCP_DISCOVERY_CACHE=1`（可选） | 缓存发现结果，允许延迟连接到首次使用 | 主要减少启动/连接工作，不等于省掉工具定义上下文；不是关键词触发 |

fff 不注册到 user scope，只写进每个角色和 router 的 `mcp.json`。存在旧 user-scope 注册时，先移除：

```bash
claude mcp remove --scope user fff
# 只想在单个项目使用 fff 时，改用项目 MCP 配置，不要改回 user scope
# 可参考 build/profiles/profiles.json 的 mcpServers，把 fff 写进项目的 .mcp.json
```

单次会话完全不加载已注册 MCP，可用 `claude --strict-mcp-config --mcp-config '{"mcpServers":{}}'`；这也会排除其他 MCP，不适合作为日常安装默认值。

当前官方文档的 `ENABLE_TOOL_SEARCH` 未设置时默认延迟 MCP 定义，但有模型/代理兼容性回退；`auto` 按上下文占比阈值决定是否延迟，`true` 强制延迟，`false` 预加载。这里不修改它，避免影响其他 server。Claude Code v2.1.280+ 默认把每个工具 description 和每个 server instructions 各截到 2,048 字符；这不是全部 MCP 的总上下文上限。`CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH` 是全局设置，不在本方案中调整。详情见 [Claude Code MCP 文档](https://code.claude.com/docs/en/mcp)。

也可用 `openskills install IceCodeNew/searching-with-fff/searching-with-fff -g -y` 跟随默认分支，并用 `openskills update searching-with-fff` 更新。上面固定提交的安装应审查新提交后重新执行 checkout/安装步骤，不能依赖临时 checkout 做更新。移除时先从 `profiles.json` 的 `mcpServers` / 各配置的 `mcp` 列表去掉 fff 并运行 `ccr refresh`，旧 user scope 再执行 `claude mcp remove --scope user fff`，最后用 `openskills remove searching-with-fff`；二进制和 fff 缓存由用户核对路径及使用状态后另行清理。镜像通过重建更新；已有 `/home/nonroot` 卷会遮住新镜像内的配置和技能，需要在卷中执行相同安装/更新步骤。

#### 持久化 home 的注册修复

新镜像的 `/usr/local/share/claude-dev/mcp.json` 默认为空；fff 由 `ccr refresh` 写进
`~/.local/state/cc-router/profiles/*/mcp.json` 和 `runtime/router-mcp.json`，启动会话时通过
`--mcp-config` 加载；插件自带的 MCP 仍随插件加载。持久化 home 里的旧 user-scope fff 不会自动删除，
但 `ccr` 会忽略它；按上面的 `claude mcp remove --scope user fff` 清理即可。`entrypoint.sh`
仍保留 `--init-mcp` 机制，供以后新增镜像级 MCP 默认项使用；损坏配置不会重置，入口脚本
输出警告后仍提供 SSH。

已有运行中的环境执行一次刷新即可，不会启动 SSH：

```bash
ccr refresh --strict
jq '.mcpServers' ~/.local/state/cc-router/profiles/dev/mcp.json
```

当前 checkout 的入口脚本也支持 `bash build/entrypoint.sh --init-mcp <defaults.json>`。默认清单不放在 home 内，因此不会被持久卷覆盖。Claude CLI 可能同时执行自身的配置迁移。

注册不会为已启动的会话热加载工具。在 `/mcp` 中重新连接，或重新启动 Claude。需要移除默认项时，设置容器环境变量 `CLAUDE_DEV_SKIP_MCP="fff"`（多个名称以空格分隔），避免下次启动补回；该变量不删除已有注册，也不改变项目禁用记录。

### 4.5 Entire CLI 与官方技能

[Entire CLI](https://entire.io/features/cli) 提供会话 checkpoint、历史检索与代码解释。[现行官方技能仓库](https://github.com/entireio/skills)通过 `entire@entire-skills` 插件提供技能；旧的 `entireio/claude-plugins` 已弃用。插件包含检索、解释、审查、会话交接等工作流，不需要为 Claude Code 重复安装独立技能。插件不自动软链接给 Codex。

Entire CLI 与其他命令行工具相同，通过 mise 的 GitHub backend 安装官方 release，下载、平台选择和安装由 mise 管理：

```bash
mise use -g github:entireio/cli@latest
entire version
```

同一 release 中的 `git-remote-entire` 一并提供。更新使用 `mise upgrade github:entireio/cli`；镜像不设置 `ENTIRE_NO_AUTO_UPDATE`，保留 Entire 自身的更新行为。

官方技能与其他插件相同，跟随上游默认分支安装：

```bash
claude plugin marketplace add entireio/skills
claude plugin install entire@entire-skills --scope user
```

已有持久化 home 会覆盖镜像中的工具与插件配置，需要在该 home 内执行上述 mise 和插件安装。

安装不会启用记录。不要用裸 `entire` 做安装检查，它可能启动设置流程。`entire enable` 会写入项目 `.claude/settings.json`、Git hooks 和 `.entire`，即使使用 `--local` 也会写入项目 hook 配置。启用后，后续 `git push` 默认推送会话 checkpoint，可能包含提示词、工具结果和图片；本地原始 transcript 不脱敏，提交中的秘密扫描也不等同于完整隐私保护。公开仓库尤其需要核对上传内容。

在明确决定为当前项目启用记录后，可运行：

```bash
ENTIRE_TELEMETRY_OPTOUT=1 entire enable --agent claude-code --local \
  --no-init-repo --telemetry=false --skip-push-sessions
```

该命令关闭自动推送 checkpoint，不保证完全不联网。镜像默认设置 `ENTIRE_TELEMETRY_OPTOUT=1`，不禁用自动更新。远程历史检索仍需单独登录；技能中的跨会话检索和提交关联操作也需按实际工作流确认。

### 4.6 安全 hooks

#### 脚本入口与安装

[build/hooks](build/hooks) 按职责提供可直接执行的 Python hook，JSON 从 stdin 读入，结果写到 stdout。每个 hook 只负责一项策略；`_hook_common.py` 仅复用 shell 解析和 hook 协议，不分发或组合策略。不需要安装本仓库的 Python 包，也没有仅转调 Python 的 shell 包装。复制使用时保留整个 hooks 目录，依赖为 Python 与 `bashlex`。

| 脚本 | 职责 | 使用事件 |
|---|---|---|
| `block-rm.py` | 各模式拒绝执行 shell `rm`，要求 `trash-put` | 工具执行前 |
| `protected-branches.py` | 统一检查 push、PR 合并和指定 PR 的会话授权 | 工具执行前、用户提交消息 |
| `require-tmux.py` | dev server 使用 tmux | 工具执行前 |
| `post-edit-check.py` | 编辑后文件级诊断 | 写入或编辑后 |
| `configure-claude.py` | 仅配置 Claude Code 的 hook 注册及启停 | 手动执行或镜像启动 |

镜像在 Dockerfile 的 `venv` 阶段统一安装 Python 依赖。hooks 复用 `/usr/bin/python3.13`，只向其本地依赖目录补充 `bashlex`；脚本放在 `/opt/claude-safety/hooks`，不创建 hooks 专用 venv。解释器、依赖和脚本都不受 home 卷覆盖，并自动注册 Claude Code hooks。手动安装在本仓库根目录执行，checkout 需长期保留：

```bash
uv venv --python 3.13 "$HOME/.local/share/claude-hooks-venv"
uv pip install --python "$HOME/.local/share/claude-hooks-venv/bin/python" 'bashlex==0.18'
"$HOME/.local/share/claude-hooks-venv/bin/python" -E -s build/hooks/configure-claude.py
```

注册器使用当前 Python 解释器的绝对路径注册各脚本，无需为 hook 增加 shell 启动层。`-E -s` 忽略 Python 环境变量和用户级 site-packages，并允许从同一可信 hooks 目录加载 `_hook_common.py`；不要把不可信文件放入该目录。Python 3.13 是镜像验证使用的版本。

其他 harness 可直接调用入口，不运行 `configure-claude.py`。例如：

```bash
printf '%s\n' '{"tool_name":"Bash","tool_input":{"command":"rm -- example"},"permission_mode":"default"}' \
  | "$HOME/.local/share/claude-hooks-venv/bin/python" -E -s build/hooks/block-rm.py
```

输入沿用 `tool_name`、`tool_input`、`cwd`、`session_id`、`permission_mode` 和 `hook_event_name` 等事件字段。输出采用 Claude Code 的 `hookSpecificOutput` 协议；其他 harness 必须映射事件字段，并将 `permissionDecision: deny` 转为真正的阻止执行。仅显示 JSON 不构成保护。跨 harness 的消息来源判定也由宿主负责，不保证即插即用。

#### 选择性启停

在镜像中配置所有默认 hooks：

```bash
/usr/bin/python3.13 -E -s /opt/claude-safety/hooks/configure-claude.py
```

仅关闭或重新启用编辑后检查：

```bash
/usr/bin/python3.13 -E -s /opt/claude-safety/hooks/configure-claude.py --disable post-edit-check
/usr/bin/python3.13 -E -s /opt/claude-safety/hooks/configure-claude.py --enable post-edit-check
```

手动安装使用已安装 `bashlex` 的 Python 解释器，并将脚本路径换成 checkout 中的 `build/hooks/configure-claude.py`。可列出多个职责名称：`block-rm`、`protected-branches`、`require-tmux`、`post-edit-check`。选择保存在用户 `settings.json`；初始化不重新启用已关闭项，并保留其他用户 hooks。`/hooks` 可查看独立注册，修改后重启会话。

`configure-claude.py` 只维护 plain `claude` 的 user-scope 注册。`ccr` 的专业配置不读取
用户 settings；`ccr refresh` 会读取同样的 `CLAUDE_DEV_HOOK_*` 选择，把启用中的 hook
写进每个配置的 `settings.json`。关闭 `post-edit-check` 后重新运行 `ccr refresh` 即可在
所有配置生效。

#### 分支保护与合并授权

各模式禁止直接 push 到受保护分支，普通功能分支 push 和 force push 不额外限制。默认分支、GitHub 标记的受保护分支与[常见分支策略](build/hooks/protected-branches.json)共用同一判断；策略不默认匹配 `dev*` 或 `staging`，但它们如果是默认分支或已受 GitHub 保护，仍会拦截。

push 需明确指定目标；不接受未知的变量展开、批量或通配 refspec。remote 配置 push 映射时，需写明 `source:refs/heads/destination`，避免源名称掩盖真实目标。直接 push 不能使用 PR 授权绕过，需改走 PR。

可用独立命令 `git -C /path/to/worktree push origin feature` 选择工作树。支持 `-C <目录>`、`-C<目录>`、相对路径和连续 `-C`；相对路径从前一个目录解析，空 `-C ''` 保持目录不变。remote、push 映射和 HEAD 均在最终目录中检查。此形式仅接受字面参数，不接受其他 Git 前置选项、shell 展开、重定向、wrapper 或复合命令；路径中的 `$`、反引号、`~`、`*`、`?`、方括号和花括号也会保守拒绝。`cd`、`pushd`、`export` 与 push 同句仍被拒绝。

`bypassPermissions` 模式合并受保护分支前，用户在当前仓库的对话中单独回复：

```text
允许合并 PR #123
```

授权绑定会话、GitHub host、仓库和 PR，不跨会话复用；同一会话在恢复或压缩后保留授权。`撤销合并 PR #123` 移除当前会话同编号 PR 的授权，不依赖网络；`撤销所有合并授权` 清除当前会话授权。引用、代码示例、工具结果和已标识自动消息不提供授权。

拒绝只阻止本次操作。agent 应用普通消息申请授权，同时继续测试、文档及其他不依赖合并的工作，不使用阻塞式提问。授权不会执行合并，也不能取消已经向 GitHub 提交的自动合并或队列任务。

支持 `gh pr merge`（含 `--auto`）、REST 合并与 GitHub MCP `merge_pull_request`。GraphQL 合并和不透明请求体改用明确的 `gh pr merge <number> -R owner/repo`。无法确认目标、元数据或授权状态时拒绝执行。

#### 其他规则与边界

- `block-rm` 覆盖绝对路径、常见包装命令、命令替换和嵌套 shell；普通文本、Docker `--rm` 和 `docker rm` 不误当成 shell `rm`。
- dev server 使用 tmux，普通构建或帮助命令不受限。
- 编辑后使用本地 ruff、oxlint、rustfmt、gofmt；缺工具会提示并跳过，不隐式下载包，不构建整个项目。诊断保留状态和完整输出，最长运行 20 秒。
- hooks 是工具调用保护，不是进程隔离。任意解释器脚本、改名二进制及其他程序内部子进程不在保证范围；用户或宿主可修改、禁用 hooks。
- CLI/Paseo 等宿主必须如实传递用户输入。hook 无法区分恶意宿主伪造的、与人类输入相同的裸文本。

### 4.7 重新加载

技能使用 `/reload-skills` 重新加载；MCP 注册使用 `/mcp` 检查和重连，必要时重启。hooks 修改后检查 `/hooks` 并重启会话，不将技能重载当作 hook 或 MCP 重载。

### 4.8 路由配置与 ccr

`ccr` 是唯一日常入口。它读取 [profiles.json](build/profiles/profiles.json)，生成每个配置的
settings、prompt、mcp 和 router agent，然后用后台会话分发任务。完整协议见
[docs/profiles.md](docs/profiles.md)。

镜像已包含 `/usr/local/bin/ccr` 和 `/opt/cc-router`，首次登录后直接运行：

```bash
ccr refresh --strict
ccr doctor --strict
ccr
```

进入子会话后可以一键调用 `~/.claude/commands/` 下的命令，例如 `/plan`、
`/research`、`/feature`、`/review`、`/security-check`。
路由保留命令可见，但 prompt 要求实现类命令分发给对应配置，只有只读的 `/plan`、
`/research` 可按用户明确要求原地执行。命令清单见
[配置与命令](docs/profiles.md#命令把内化能力做成一次点击)。

手动安装时，把脚本和 profile 源放到用户目录。`ccr` 会依次查找
`$CCR_SOURCE_DIR`、`/opt/cc-router`、`~/.local/share/cc-router`：

```bash
install -Dm755 build/ccr/ccr.py ~/.local/bin/ccr
mkdir -p ~/.local/share/cc-router
cp -R build/profiles/* ~/.local/share/cc-router/
cp -R build/hooks ~/.local/share/cc-router/hooks
export PATH="$HOME/.local/bin:$PATH"
export CLAUDE_HOOK_PYTHON="$HOME/.local/share/claude-hooks-venv/bin/python"
export CCR_HOOKS_DIR="$HOME/.local/share/cc-router/hooks"
ccr refresh --strict
ccr doctor --strict
```

把两条 `export` 加进 `~/.bashrc`，否则新开的 shell 在自动 refresh 时会回退到
系统 Python，找不到 `bashlex`。`CLAUDE_HOOK_PYTHON` 指向[4.6](#46-安全-hooks)创建的
hooks venv。

模型档位用环境变量覆盖，默认 `CCR_ROUTER_MODEL=haiku`、`CCR_HARD_MODEL=opus`、
`CCR_MEDIUM_MODEL=sonnet`、`CCR_EASY_MODEL=haiku`。路由要「便宜、快、上下文大」时，把它设成提供商里符合条件
的别名，然后重新 `ccr refresh`：

```bash
export CCR_ROUTER_MODEL=fable   # 例：网关把 fable 映射到 1M 上下文的便宜模型
export CCR_HARD_MODEL=opus
export CCR_MEDIUM_MODEL=sonnet
export CCR_EASY_MODEL=haiku
ccr refresh
```

升级插件或技能后重新运行 `ccr refresh`；持久化 home 的启动脚本也会自动执行。旧的
user-scope fff 按 4.4 移除。`ccr` 不修改用户 `settings.json`，只写
`~/.claude/agents/ccr-router.md`（已有文件先备份为 `.bak`）。

---

## 5. 登录与认证

先完成 Claude Code 本身的认证，已通过环境变量或宿主配置凭据时仅检查状态：

```bash
claude auth status
claude auth login
```

各集成单独配置，不把凭据写入 Dockerfile：

| 插件 | 要做的事 |
|---|---|
| commit-commands、coderabbit autofix、superpowers 诊断、github MCP、gh-cli | `gh auth login` |
| coderabbit | `coderabbit auth login`（EU 区加 `--region eu`） |
| firecrawl | `firecrawl login --browser`，或 `firecrawl login --api-key fc-...`，或设置环境变量 `FIRECRAWL_API_KEY` |
| linear、cloudflare MCP | 在 claude 里执行 `/mcp`，选中后在浏览器授权 |
| telegram | 在 claude 里执行 `/telegram:configure <bot token>`，然后用 `claude --channels plugin:telegram@claude-plugins-official` 启动 |
| nowledge-mem | 本机运行 Mem 时不用配置；连远程服务器见下 |
| cloudflare wrangler（可选） | `wrangler login`；没有浏览器时设置 `CLOUDFLARE_API_TOKEN`，turnstile 还要 `CLOUDFLARE_ACCOUNT_ID` |
| Cloudflare cf CLI | `cf auth login`；SSH/容器中用 `cf auth login --no-browser`，按提示在本机浏览器完成设备授权；自动化可设置 `CLOUDFLARE_API_TOKEN` |
| remember、security-guidance | 沿用 claude 本身的登录，不用单独配置 |

```bash
gh auth login
coderabbit auth login
firecrawl login --browser
cf auth login --no-browser

# nowledge-mem 远程模式
nmem config client set url "https://your-server"   # 换成服务器地址
nmem config client set api-key "your-api-key"     # 换成 API key
nmem status
```

改完 `[env]` 或登录 gh 之后，要从新开的 shell 里重启 claude，github MCP 才能拿到 token。

cf 的 OAuth 登录与 Cloudflare MCP 授权分别进行。`CLOUDFLARE_API_TOKEN` 优先于 cf 保存的 OAuth 凭据；要使用 OAuth 登录，先取消设置该变量。凭据只在运行时配置，不写入 Dockerfile。

---

## 6. 验证

```bash
# mise 工具在 PATH 上；perl 来自系统，fff 用绝对路径验证
for c in perl jq gh node bun nmem firecrawl coderabbit cf \
         pyright-langserver typescript-language-server gopls rust-analyzer cargo claude; do
  printf '%-28s %s\n' "$c" "$(command -v $c || echo MISSING)"
done

# 共享 venv 已激活：python、python3.13、pyright-langserver 都应来自 ~/.local/share/claude-plugins-venv/bin
echo "VIRTUAL_ENV=$VIRTUAL_ENV"
command -v python python3.13 pyright-langserver
python -c 'import claude_agent_sdk, yaml; print("claude_agent_sdk + pyyaml ok")'
# security-guidance 自己的检查：(0, '', '') 表示直接用当前 python，(1, '', '') 表示走软链接回退
(cd ~/.claude/plugins/cache/claude-plugins-official/security-guidance/*/hooks && \
  python3.13 -c 'import ensure_agent_sdk as e; print(e.main())')
ls -l "$(mise where npm:typescript-language-server)/node_modules/typescript"   # 指向 typescript 6
rustc --print sysroot | xargs -I{} test -d {}/lib/rustlib/src/rust/library && echo "rust-src ok"
[ -n "$GITHUB_PERSONAL_ACCESS_TOKEN" ] && echo "github token ok" || echo "github token EMPTY"
gh auth status
coderabbit auth status
firecrawl --status
cf --version
cf cli search "list zones"   # 命令发现，不执行 API 操作
cf auth whoami              # 登录后核对身份
nmem status
openskills list
"$HOME/.local/bin/fff-mcp" --version
jq '.mcpServers' ~/.local/state/cc-router/profiles/dev/mcp.json
ccr profiles
ccr doctor --strict
test -r ~/.claude/skills/searching-with-fff/SKILL.md
test -r ~/.agents/skills/searching-with-fff/SKILL.md
gh stack --help | head -1
```

启动路由 `ccr` 之后：

```text
/mcp                  # fff + nmem/remember/ops/session-driver 的插件 MCP
/hooks                # 路由 hint + remember/nmem 的记忆 hooks
/plugin               # 只启用 nmem/remember/ops/session-driver
/skills               # searching-with-fff + 上述插件的技能
```

用 `ccr spawn --profile dev --tier easy --name verify --prompt-file -` 派一个验证子会话，
attach 后检查：

```text
/mcp                  # dev 配置应看到 fff connected
/hooks                # block-rm、protected-branches、require-tmux、post-edit-check
/skills               # 只应出现 dev 配置的技能
/feature              # 命令可被模型或用户直接调用
```

### 仓库验收

在 checkout 根目录执行；镜像 smoke 还会校验已安装脚本及实际交互式别名。手动运行安全测试时设置专用解释器：

```bash
CLAUDE_HOOK_PYTHON="$HOME/.local/share/claude-hooks-venv/bin/python" python3 -B build/test-safety-hooks.py
python3 -B build/test-mcp-bootstrap.py
python3 -B build/test-fff.py
python3 -B build/test-entire.py
python3 -B build/test-docs.py
```

这些检查使用隔离目录；不会通过测试合并远端 PR。完整镜像验证使用：

```bash
docker buildx build --target smoke --file build/Dockerfile .
```
