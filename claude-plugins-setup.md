# Claude Code 插件与依赖安装手册

生成日期：2026-09-25。环境：Linux x64，claude 2.1.281，mise 2026.9.12。

插件清单另存为 `claude-plugins.tsv`（4 列：`插件@marketplace`、版本、scope、是否启用）。第 4 节另外安装一批第三方技能（skills）。

本文面向一台全新的机器。命令行工具由 mise 管理，写在 `~/.config/mise/config.toml`；Python 包由 uv 装进 Claude 插件共用的 venv；git、curl、lsof 由系统包管理器安装。

按顺序执行第 1 到第 6 节。每个代码块都能单独复制执行。

---

## 1. 系统包和 mise

mise registry 里没有 git 和 lsof。curl 用来装 mise 本身。

```bash
# Debian / Ubuntu
sudo apt update && sudo apt install -y git curl lsof
# Fedora
# sudo dnf install -y git curl lsof
```

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
| `node = "26"` | firecrawl 的 npx 兜底、session-report、superpowers、pyright 运行时、modern-web-guidance |
| `bun` | telegram 的 stdio MCP |
| `uv` | 创建和管理共享 Python venv（2.2 节） |
| `gh`、`jq` | code-review、commit-commands、pr-review-toolkit、coderabbit、remember、ralph-loop |
| `perl` | ralph-loop 的 stop-hook 用 perl 提取 `<promise>` 标签，缺了不会报错，但循环永远不会结束 |
| `claude-code` | Claude Code 本身；remember、security-guidance、skill-creator 也会调用 `claude` |
| `go`、`"go:golang.org/x/tools/gopls"` | gopls-lsp |
| `rust`（带 `rust-src`、`rust-analyzer` 组件） | rust-analyzer-lsp。mise 按 minimal profile 装的 rust 没有 rust-src，rust-analyzer 无法分析标准库；rust-analyzer 用 rustup 组件，版本和工具链一致 |
| `"npm:typescript" = "6"` | typescript 7 是 Go 原生版，包里没有 `tsserver.js`，typescript-language-server 6.0.0 用不了 |
| `"npm:typescript-language-server"` | typescript-lsp。见下方说明 |
| `"npm:firecrawl-cli"` | firecrawl |
| `"pypi:nmem-cli"` | nowledge-mem 的 hook 和命令 |
| `"npm:openskills"` | 第 4 节安装第三方技能 |
| `"github:Xuanwo/xurl"` | xurl 技能调用的 `xurl` 命令 |
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
perl = "latest"
pnpm = "latest"
claude-code = "latest"
go = "latest"
"go:golang.org/x/tools/gopls" = "latest"
rust = { version = "latest", components = ["rust-src", "rust-analyzer"] }
"npm:typescript" = "6"
"npm:typescript-language-server" = { version = "latest", depends = ["npm:typescript"], postinstall = 'ln -sfn "$HOME/.local/share/mise/installs/npm-typescript/6/node_modules/typescript" "$MISE_TOOL_INSTALL_PATH/node_modules/typescript"' }
"npm:firecrawl-cli" = "latest"
"pypi:nmem-cli" = "latest"
"npm:openskills" = "latest"
"github:Xuanwo/xurl" = "latest"
"github:redhat-et/ripwire" = "latest"

[tools."http:coderabbit"]
version = "latest"
url = "https://cli.coderabbit.ai/releases/{{ version }}/coderabbit-linux-x64.zip"
version_list_url = "https://cli.coderabbit.ai/releases/latest/VERSION"
EOF

mise install
```

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
| skill-creator | pyyaml | SKILL.md 里调用的是 `python -m scripts...`，venv 提供 `python` 命令，且能 `import yaml` |
| pyright-lsp | pyright | venv 的 `bin/` 里有 `pyright-langserver`，运行时用 mise 的 node |
| read 技能（第 4 节） | readability-lxml、html2text | 本地网页正文提取；缺少时退回标准库解析，输出质量较差 |

venv 的 Python 固定为 3.13：`sg-python.sh` 只探测 python3.13 到 3.10 这几个带版本号的名字，3.14 会被跳过。`create = true` 时 mise 调用 uv 建 venv，系统里没有 3.13 的话 uv 会自己下载。

`GITHUB_PERSONAL_ACCESS_TOKEN` 给 github MCP 用，从 gh 的登录 token 读取；gh 未安装或未登录时取值为空，不影响 mise 正常工作。也可以在 shell 配置里 `export GITHUB_PERSONAL_ACCESS_TOKEN="$(gh auth token)"`，两处只保留一处。

```bash
cat >> ~/.config/mise/config.toml <<'EOF'

[env]
# Claude 插件共用的 uv venv（security-guidance、skill-creator、pyright-lsp），mise 激活时自动创建并加入 PATH
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

由 IDE 等不经过 `mise activate` 的方式启动 claude 时，venv 不在 PATH 上：security-guidance 通过软链接仍可使用，pyright-lsp 和 skill-creator 的 `python` 则找不到。

---

## 3. 添加 marketplace 并安装插件

scope 默认是 user。

```bash
claude plugin marketplace add anthropics/claude-plugins-official
claude plugin marketplace add https://github.com/nowledge-co/community.git
claude plugin marketplace add pydantic/skills
claude plugin marketplace add JetBrains/go-modern-guidelines
claude plugin marketplace update
```

安装全部 31 个插件：

```bash
for p in \
  claude-code-setup claude-md-management claude-security cloudflare code-review \
  code-simplifier coderabbit commit-commands context7 feature-dev firecrawl github \
  gopls-lsp hookify linear modern-web-guidance pr-review-toolkit pyright-lsp \
  ralph-loop redis-development remember rust-analyzer-lsp security-guidance \
  session-report skill-creator superpowers telegram typescript-lsp
do
  claude plugin install "$p@claude-plugins-official" --scope user
done
claude plugin install nowledge-mem@nowledge-community --scope user
claude plugin install pydantic@pydantic-skills --scope user
claude plugin install modern-go-guidelines@goland-claude-marketplace --scope user
```

在脚本或管道里跑、stdin/stdout 不是终端时，给需要确认的安装加 `-y`。

以下 3 个插件装好后禁用：

```bash
for p in claude-security redis-development modern-web-guidance; do
  claude plugin disable "$p@claude-plugins-official" --scope user
done
```

也可以直接用 `claude-plugins.tsv` 驱动：

```bash
cut -f1 claude-plugins.tsv | xargs -n1 claude plugin install --scope user
awk -F'\t' '$4=="false"{print $1}' claude-plugins.tsv | xargs -n1 claude plugin disable --scope user
```

核对：

```bash
claude plugin list
```

---

## 4. 第三方技能

技能均安装上游当时的最新版本。ninehills 维护的技能用其仓库自带的 Python 脚本安装；ripwire 的技能用 ripwire 发布包自带的安装脚本安装；其余技能用 openskills 装到 `~/.claude/skills`（`-g` 为全局，`-y` 跳过交互选择）。pydantic 和 use-modern-go 以插件形式提供，已在第 3 节安装。

### 4.1 ninehills 技能（官方 skills-manager 脚本）

脚本按「场景」整组安装，用软链接把技能装进 `~/.codex/skills`、`~/.pi/agent/skills`、`~/.claude/skills`、`~/.hermes/skills` 四个目录，所以仓库要克隆到一个长期保留的位置。这里用 Common 场景（33 个技能，含 better-goal、hunt、karpathy-guidelines、learn、pua、read、review-code、tdd、think、write）。

```bash
git clone https://github.com/ninehills/skills ~/git/ninehills-skills
cd ~/git/ninehills-skills
python3 skills-manager scenarios list
python3 skills-manager scenarios install Common
```

更新：

```bash
git -C ~/git/ninehills-skills pull
python3 ~/git/ninehills-skills/skills-manager scenarios install Common
```

同一仓库中的 tech-doc-style-chinese 不属于任何场景，用 openskills 安装（见 4.3）。

### 4.2 ripwire 技能（官方 skills/install.sh）

mise 安装的 ripwire 压缩包里带有 `skills/` 目录和 `skills/install.sh`。脚本把每个 `ripwire-*` 技能软链接进 `~/.claude/skills`，链接目标是脚本所在的目录。通过 mise 的 `latest` 路径执行，链接就指向 `latest`，`mise upgrade` 之后仍然有效。`ripwire-opt-remarks` 只用于开发 ripwire 本身，脚本默认跳过。

```bash
bash ~/.local/share/mise/installs/github-redhat-et-ripwire/latest/skills/install.sh
```

ripwire 升级后技能列表可能变化，重新执行同一条命令即可：新技能会建立链接，上游删掉的技能会被清理。

### 4.3 其余技能（openskills）

最后一项是 GitHub Gist 上的 japanese-tech-writing（日语技术文档写作规范），openskills 直接用 gist 的 git 地址安装，技能目录名取自 SKILL.md 的 `name`。

```bash
cd ~
for s in \
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
  Xuanwo/xurl/skills/xurl \
  ninehills/skills/tech-doc-style-chinese \
  https://gist.github.com/k16shikano/fd287c3133457c4fd8f5601d34aa817d.git
do
  openskills install "$s" -g -y
done
```

更新全部 openskills 技能：

```bash
openskills update
```

技能依赖的命令：

| 技能 | 依赖 | 安装 |
|---|---|---|
| xurl | `xurl` | mise（2.1 节已包含） |
| gh-stack | `gh stack` | gh 扩展，见下方命令 |
| read | readability-lxml、html2text | 共享 uv venv（2.2 节已包含） |

```bash
gh extension install github/gh-stack
```

### 4.4 重新加载

在已经运行的 claude 会话里执行 `/reload-skills`，新装的技能就能用；新开的会话会自动加载。

---

## 5. 登录与认证

| 插件 | 要做的事 |
|---|---|
| code-review、commit-commands、pr-review-toolkit、coderabbit autofix、superpowers 诊断、github MCP | `gh auth login` |
| coderabbit | `coderabbit auth login`（EU 区加 `--region eu`） |
| firecrawl | `firecrawl login --browser`，或 `firecrawl login --api-key fc-...`，或设置环境变量 `FIRECRAWL_API_KEY` |
| linear、cloudflare MCP | 在 claude 里执行 `/mcp`，选中后在浏览器授权 |
| telegram | 在 claude 里执行 `/telegram:configure <bot token>`，然后用 `claude --channels plugin:telegram@claude-plugins-official` 启动 |
| nowledge-mem | 本机运行 Mem 时不用配置；连远程服务器见下 |
| cloudflare wrangler（可选） | `wrangler login`；没有浏览器时设置 `CLOUDFLARE_API_TOKEN`，turnstile 还要 `CLOUDFLARE_ACCOUNT_ID` |
| remember、security-guidance、skill-creator | 沿用 claude 本身的登录，不用单独配置 |

```bash
gh auth login
coderabbit auth login
firecrawl login --browser

# nowledge-mem 远程模式
nmem config client set url "https://your-server"   # 换成你的服务器地址
nmem config client set api-key "your-api-key"     # 换成你的 API key
nmem status
```

改完 `[env]` 或登录 gh 之后，要从新开的 shell 里重启 claude，github MCP 才能拿到 token。

---

## 6. 验证

```bash
# 工具都在 PATH 上，且来自 mise
for c in perl jq gh node bun nmem firecrawl coderabbit \
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
nmem status
openskills list
find ~/.claude/skills -maxdepth 1 -type l | wc -l   # ninehills Common 场景的 33 个软链接
gh stack --help | head -1
```

启动 claude 之后：

```text
/mcp                  # context7、github、linear、cloudflare、telegram 应显示 connected
/remember:doctor      # remember 插件自检
/plugin               # 插件和启用状态
/skills               # 技能列表，第 4 节装的技能应在其中
```
