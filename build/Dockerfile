# syntax=mirror.gcr.io/docker/dockerfile:1.25.0@sha256:0adf442eae370b6087e08edc7c50b552d80ddf261576f4ebd6421006b2461f12

FROM icecodexi/python:debian-nonroot@sha256:55799dfc2ebc565ecd29a2ac4588efa58daedaad39e31fadef1cec998dd43fb9 AS secure-mirrors
COPY --link <<npm <<pip <<uv /

registry=https://npm.flatt.tech/
npm

[global]
index-url = https://pypi.flatt.tech/simple/
pip

[[index]]
url = "https://pypi.flatt.tech/simple/"
default = true
uv

USER root:root
ENV HOME=/home/nonroot
RUN mkdir -p \
    "/secure-mirrors/${HOME}/.config/pnpm/" \
    "/secure-mirrors/${HOME}/.config/pip/" \
    "/secure-mirrors/${HOME}/.config/uv" \
    && cp -f /npm "/secure-mirrors/${HOME}/.npmrc" \
    && cp -f /npm "/secure-mirrors/${HOME}/.config/pnpm/auth.ini" \
    && cp -f /pip "/secure-mirrors/${HOME}/.config/pip/pip.conf" \
    && cp -f /uv  "/secure-mirrors/${HOME}/.config/uv/uv.toml"


FROM icecodexi/python:debian-nonroot@sha256:55799dfc2ebc565ecd29a2ac4588efa58daedaad39e31fadef1cec998dd43fb9 AS mise
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
USER root:root
# git, curl and lsof are not in the mise registry; perl comes with Debian.
# openssh-server runs as nonroot (see entrypoint.sh); sudo stands in for root login.
RUN extrepo enable mise \
    && install_packages \
        libatomic1 mise \
        build-essential musl \
        curl \
        git \
        jq \
        lsof \
        openssh-server \
        ripgrep \
        sudo \
    && rm -f /etc/ssh/ssh_host_* \
    && echo 'nonroot ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/nonroot
COPY --link <<sshd_config /etc/ssh/sshd_config.d/nonroot.conf
Port 8964
HostKey /home/nonroot/.ssh/ssh_host_ed25519_key
PasswordAuthentication no
sshd_config

ENV HOME=/home/nonroot
RUN mkdir -p \
    "/empty/${HOME}/.local/share/" \
    "${HOME}/.cache" "${HOME}/.config/mise" "${HOME}/.local/share/mise" "${HOME}/.local/state/mise" "${HOME}/go/pkg" \
    && chown -R 65532:65532 "${HOME}" /empty/

USER nonroot:nonroot
ENV PNPM_HOME="${HOME}/.local/share/pnpm"
ENV PNPM_CONFIG_STORE_DIR="${PNPM_HOME}/store"
ENV PATH="${HOME}/.local/share/mise/shims:${PNPM_HOME}/bin:${PATH}" \
    SHELL=bash


FROM mise AS assets
# renovate: datasource=node-version packageName=node
ARG NODE_VERSION=26.10.0
# renovate: datasource=github-releases packageName=pnpm/pnpm
ARG PNPM_VERSION=12.6.0
# renovate: datasource=npm packageName=@openai/codex
ARG CODEX_VERSION=0.157.1
# renovate: datasource=npm packageName=@jackwener/opencli
ARG OPENCLI_VERSION=1.8.7
# renovate: datasource=npm packageName=@anthropic-ai/claude-code
ARG CLAUDE_CODE_VERSION=2.1.283
# renovate: datasource=npm packageName=playwright-core
ARG PLAYWRIGHT_CORE_VERSION=1.63.0
RUN --mount=type=cache,id=mise-cache,target=/home/nonroot/.cache/mise,uid=65532,gid=65532 \
    --mount=type=cache,id=mise-downloads-cache,target=/home/nonroot/.local/share/mise/downloads,uid=65532,gid=65532 \
    --mount=type=cache,id=npm-cache,target=/home/nonroot/.npm,uid=65532,gid=65532 \
    --mount=type=cache,id=sigstore-cache,target=/home/nonroot/.cache/sigstore-rust,uid=65532,gid=65532 \
    <<EOF
set -euo pipefail
# typescript 7 is the Go-native build without tsserver.js; typescript-language-server resolves
# typescript from its own node_modules, so postinstall links it to typescript 6.
cat > "${HOME}/.config/mise/config.toml" <<'CONFIG'
[tools]
ast-grep = "latest"
bun = "latest"
gh = "latest"
go = "latest"
rust = { version = "latest", components = ["rust-src", "rust-analyzer"] }
shellcheck = "latest"
tree-sitter = "latest"
uv = "latest"

"go:golang.org/x/tools/gopls" = "latest"
"npm:typescript" = "6"
"npm:typescript-language-server" = { version = "latest", depends = ["npm:typescript"], postinstall = 'ln -sfn "$HOME/.local/share/mise/installs/npm-typescript/6/node_modules/typescript" "$MISE_TOOL_INSTALL_PATH/node_modules/typescript"' }
"npm:firecrawl-cli" = "latest"
"npm:openskills" = "latest"
"pypi:nmem-cli" = "latest"
"github:aptible/supercronic" = "latest"
"github:redhat-et/ripwire" = "latest"
"github:Xuanwo/xurl" = "latest"

[tools."http:coderabbit"]
version = "latest"
version_list_url = "https://cli.coderabbit.ai/releases/latest/VERSION"
platforms.linux-x64 = { url = "https://cli.coderabbit.ai/releases/{{ version }}/coderabbit-linux-x64.zip" }
platforms.linux-arm64 = { url = "https://cli.coderabbit.ai/releases/{{ version }}/coderabbit-linux-arm64.zip" }
CONFIG

mise use -g \
    node@${NODE_VERSION} pnpm@${PNPM_VERSION}
mise use -g \
    claude-code@${CLAUDE_CODE_VERSION} \
    "npm:@openai/codex"@${CODEX_VERSION} \
    "npm:@jackwener/opencli"@${OPENCLI_VERSION} \
    "npm:playwright-core"@${PLAYWRIGHT_CORE_VERSION}
mise install \
    npm:typescript npm:typescript-language-server npm:firecrawl-cli npm:openskills
cp -a "${HOME}/.local/share/mise" "/empty/${HOME}/.local/share/"
EOF


FROM scratch AS npm-pkgs
COPY --link --from=assets /home/nonroot/ /home/nonroot/
COPY --link --from=assets /empty/ /


FROM mise AS tools
COPY --link --from=ghcr.io/astral-sh/ruff:0.15.21@sha256:d88c0de3362ae064e5f3175ff558ee1077223d3f81a1e78b1cf57825c4882454 /ruff /usr/local/bin/
COPY --link --from=ghcr.io/astral-sh/ty:0.0.58@sha256:8d279433ab7ebba881fe2c8a66bc892c4f3411a54f440b79c59621bc9db3ef03 /ty /usr/local/bin/
COPY --link --from=ghcr.io/astral-sh/uv:0.11.28@sha256:0f36cb9361a3346885ca3677e3767016687b5a170c1a6b88465ec14aefec90aa /uv /uvx /usr/local/bin/
COPY --link --from=mikefarah/yq:4.53.3@sha256:11a1f0b604b13dbbdc662260d8db6f644b22d8553122a25c1b5b2e8713ca6977 /usr/bin/yq /usr/local/bin/
COPY --link --from=ghcr.io/j178/prek:v0.4.8@sha256:923fe4fde30504a5043a590e8dc175d0dc270a3311d14aec44994ad4fd4a088e /prek /usr/local/bin/
COPY --link --from=npm-pkgs --chown=65532:65532 /home/nonroot/ /home/nonroot/
RUN --mount=type=cache,id=mise-cache,target=/home/nonroot/.cache/mise,uid=65532,gid=65532 \
    --mount=type=cache,id=mise-downloads-cache,target=/home/nonroot/.local/share/mise/downloads,uid=65532,gid=65532 \
    --mount=type=cache,id=npm-cache,target=/home/nonroot/.npm,uid=65532,gid=65532 \
    --mount=type=cache,id=sigstore-cache,target=/home/nonroot/.cache/sigstore-rust,uid=65532,gid=65532 \
    --mount=type=cache,id=go-build-cache,target=/home/nonroot/.cache/go-build,uid=65532,gid=65532 \
    --mount=type=cache,id=go-mod-cache,target=/home/nonroot/go/pkg/mod,uid=65532,gid=65532 \
    --mount=type=cache,id=uv-cache,target=/home/nonroot/.cache/uv,uid=65532,gid=65532 \
    mise install && mise reshim

# The headless shell cannot load extensions, so install only full Chromium.
# --with-deps uses apt through sudo when it does not run as root.
# hadolint ignore=DL3004
RUN playwright-core --version \
    && playwright-core install --with-deps --no-shell chromium \
    && sudo rm -rf /var/lib/apt/lists/*

# Shared venv for claude-agent-sdk (security-guidance), pyyaml (skill-creator), pyright (pyright-lsp)
# and readability-lxml/html2text (read skill). python 3.13 because security-guidance only probes
# python3.13 through python3.10.
ENV CLAUDE_PLUGINS_VENV="${HOME}/.local/share/claude-plugins-venv"
RUN --mount=type=cache,id=uv-cache,target=/home/nonroot/.cache/uv,uid=65532,gid=65532 \
    <<EOF
set -euo pipefail
cat >> "${HOME}/.config/mise/config.toml" <<'CONFIG'

[env]
_.python.venv = { path = "{{ env.HOME }}/.local/share/claude-plugins-venv", create = true, python = "3.13" }
# github MCP; empty until `gh auth login`
GITHUB_PERSONAL_ACCESS_TOKEN = "{{ exec(command='for g in $HOME/.local/share/mise/installs/gh/latest/*/bin/gh; do $g auth token 2>/dev/null || true; done') }}"
CONFIG

export UV_LINK_MODE=copy
# mise creates the venv from [env] on its first run
mise exec -- python --version
uv pip install --python "${CLAUDE_PLUGINS_VENV}/bin/python" \
    claude-agent-sdk pyyaml pyright readability-lxml html2text
mkdir -p "${HOME}/.claude/security"
ln -sfn "${CLAUDE_PLUGINS_VENV}" "${HOME}/.claude/security/agent-sdk-venv"
EOF


FROM tools AS plugins
RUN <<EOF
set -euo pipefail
claude plugin marketplace add anthropics/claude-plugins-official
claude plugin marketplace add https://github.com/nowledge-co/community.git
claude plugin marketplace add pydantic/skills
claude plugin marketplace add JetBrains/go-modern-guidelines

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

for p in claude-security redis-development modern-web-guidance; do
    claude plugin disable "$p@claude-plugins-official" --scope user
done
EOF


FROM plugins AS skills
# Skills go to ~/.claude/skills first, then every one is linked into ~/.agents/skills for Codex.
RUN --mount=type=cache,id=npm-cache,target=/home/nonroot/.npm,uid=65532,gid=65532 \
    <<EOF
set -euo pipefail
git clone --depth 1 https://github.com/ninehills/skills "${HOME}/git/ninehills-skills"
python3 "${HOME}/git/ninehills-skills/skills-manager" scenarios install Common

bash "${HOME}/.local/share/mise/installs/github-redhat-et-ripwire/latest/skills/install.sh"

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
    openclaw/openclaw/.agents/skills/test-audit \
    https://gist.github.com/k16shikano/fd287c3133457c4fd8f5601d34aa817d.git
do
    openskills install "$s" -g -y
done
gh extension install github/gh-stack

rm -rf "${HOME}/.codex/skills" "${HOME}/.pi" "${HOME}/.hermes"
mkdir -p "${HOME}/.agents/skills"
for s in "${HOME}"/.claude/skills/*; do
    ln -sfn "$s" "${HOME}/.agents/skills/${s##*/}"
done
EOF


FROM skills AS final
# sshd sessions do not inherit ENV, so login shells activate mise (tools, venv, GITHUB_PERSONAL_ACCESS_TOKEN)
# before the non-interactive early return in ~/.bashrc.
RUN sed -i '1i eval "$(mise activate bash)"\nalias cr=coderabbit' "${HOME}/.bashrc"
COPY --link --chmod=755 entrypoint.sh /
EXPOSE 8964
ENTRYPOINT [ "catatonit", "-g", "--", "/entrypoint.sh" ]
