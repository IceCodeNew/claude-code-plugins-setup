# syntax=mirror.gcr.io/docker/dockerfile:1.27.0@sha256:bde3983e9c939224420ddaf6b784cc30e09b035a4dea01f581230c50809f372e

# Stages are grouped by how often their inputs change, and each lands in the final image
# through COPY --link. A Claude Code bump rebuilds the claude stage and replaces its layer;
# every other layer keeps its digest, so CI skips them and users do not re-pull them.
# Stages that install "latest" versions (toolchains, cli, npm-tools, browsers, venv,
# agent-config) rebuild only when their own instructions or the mise stage change.

FROM icecodexi/python:debian-nonroot@sha256:76cf2573848ee1df53ff8a07b86fb31535f42703087c33897affb20d53c86f40 AS secure-mirrors
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


FROM ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424 AS uv-bin


FROM icecodexi/python:debian-nonroot@sha256:76cf2573848ee1df53ff8a07b86fb31535f42703087c33897affb20d53c86f40 AS mise
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
USER root:root
# git, curl and lsof are not in the mise registry; perl comes with Debian.
# openssh-server runs as nonroot (see entrypoint.sh); sudo stands in for root login.
RUN extrepo enable mise \
    && install_packages \
        libatomic1 mise \
        build-essential musl \
        curl \
        fd-find findutils \
        git patchutils \
        jq \
        lsof \
        ncdu \
        openssh-server \
        plocate procps psmisc px \
        ripgrep rsync \
        sudo \
        tmux vim \
    && rm -f /etc/ssh/ssh_host_* \
    && echo 'nonroot ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/nonroot
COPY --link <<sshd_config /etc/ssh/sshd_config.d/nonroot.conf
Port 8964
HostKey /home/nonroot/.ssh/ssh_host_ed25519_key
PasswordAuthentication no
sshd_config


ENV HOME=/home/nonroot
RUN mkdir -p \
    "${HOME}/.cache" "${HOME}/.config/mise/conf.d" "${HOME}/.local/share/mise" "${HOME}/.local/state/mise" "${HOME}/go/pkg" \
    && chown -R 65532:65532 "${HOME}"

USER nonroot:nonroot
ENV PNPM_HOME="${HOME}/.local/share/pnpm"
ENV PNPM_CONFIG_STORE_DIR="${PNPM_HOME}/store"
ENV PATH="${HOME}/.local/share/mise/shims:${PNPM_HOME}/bin:${PATH}" \
    SHELL=bash


FROM mise AS toolchains
# The minimal profile leaves out rust-docs (917M); clippy and rustfmt come from the default profile.
RUN --mount=type=cache,id=mise-cache,target=/home/nonroot/.cache/mise,uid=65532,gid=65532 \
    --mount=type=cache,id=mise-downloads-cache,target=/home/nonroot/.local/share/mise/downloads,uid=65532,gid=65532 \
    --mount=type=cache,id=sigstore-cache,target=/home/nonroot/.cache/sigstore-rust,uid=65532,gid=65532 \
    --mount=type=cache,id=go-build-cache,target=/home/nonroot/.cache/go-build,uid=65532,gid=65532 \
    --mount=type=cache,id=go-mod-cache,target=/home/nonroot/go/pkg/mod,uid=65532,gid=65532 \
    <<EOF
set -euo pipefail
cat > "${HOME}/.config/mise/conf.d/10-toolchains.toml" <<'CONFIG'
[tools]
rust = { version = "latest", profile = "minimal", components = ["rust-src", "rust-analyzer", "clippy", "rustfmt"] }
go = "latest"
"go:golang.org/x/tools/gopls" = "latest"
CONFIG
mise install
rm -rf "${HOME}/.local/share/mise/installs/.mise-installs.toml" "${HOME}/.local/share/mise/shims"
# go install leaves local telemetry counters (with an upload token) and a checksum-database
# cache behind; neither belongs in the image.
rm -rf "${HOME}/.config/go/telemetry" "${HOME}/go/pkg/sumdb"
EOF


FROM mise AS cli
# uv is the pinned uv-bin binary (also copied into the final image), not a mise tool; the pypi
# backend below uses it.
COPY --link --from=uv-bin /uv /uvx /usr/local/bin/
RUN --mount=type=cache,id=mise-cache,target=/home/nonroot/.cache/mise,uid=65532,gid=65532 \
    --mount=type=cache,id=mise-downloads-cache,target=/home/nonroot/.local/share/mise/downloads,uid=65532,gid=65532 \
    --mount=type=cache,id=sigstore-cache,target=/home/nonroot/.cache/sigstore-rust,uid=65532,gid=65532 \
    --mount=type=cache,id=uv-cache,target=/home/nonroot/.cache/uv,uid=65532,gid=65532 \
    <<EOF
set -euo pipefail
cat > "${HOME}/.config/mise/conf.d/20-cli.toml" <<'CONFIG'
[tools]
age = "latest"
atuin = "latest"
bat = "latest"
bat-extras = "latest"
bun = "latest"
cargo-binstall = "latest"
croc = "latest"
dive = "latest"
duf = "latest"
gh = "latest"
helm = "latest"
hyperfine = "latest"
kubecm = "latest"
kubectl = "latest"
shellcheck = "latest"
usage = "latest"

ast-grep = "latest"
tree-sitter = "latest"

"aqua:iffse/pay-respects" = "latest"

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
mise install
rm -rf "${HOME}/.local/share/mise/installs/.mise-installs.toml" "${HOME}/.local/share/mise/shims"
EOF


FROM mise AS node
# renovate: datasource=node-version packageName=node
ARG NODE_VERSION=26.10.0
# renovate: datasource=github-releases packageName=pnpm/pnpm
ARG PNPM_VERSION=12.7.0
RUN --mount=type=cache,id=mise-cache,target=/home/nonroot/.cache/mise,uid=65532,gid=65532 \
    --mount=type=cache,id=mise-downloads-cache,target=/home/nonroot/.local/share/mise/downloads,uid=65532,gid=65532 \
    --mount=type=cache,id=sigstore-cache,target=/home/nonroot/.cache/sigstore-rust,uid=65532,gid=65532 \
    <<EOF
set -euo pipefail
cat > "${HOME}/.config/mise/conf.d/30-node.toml" <<CONFIG
[tools]
node = "${NODE_VERSION}"
pnpm = "${PNPM_VERSION}"
CONFIG
mise install
rm -rf "${HOME}/.local/share/mise/installs/.mise-installs.toml" "${HOME}/.local/share/mise/shims"
EOF


FROM node AS npm-tools
RUN --mount=type=cache,id=mise-cache,target=/home/nonroot/.cache/mise,uid=65532,gid=65532 \
    --mount=type=cache,id=mise-downloads-cache,target=/home/nonroot/.local/share/mise/downloads,uid=65532,gid=65532 \
    --mount=type=cache,id=npm-cache,target=/home/nonroot/.npm,uid=65532,gid=65532 \
    <<EOF
set -euo pipefail
# typescript 7 is the Go-native build without tsserver.js; typescript-language-server resolves
# typescript from its own node_modules, so postinstall links it to typescript 6.
cat > "${HOME}/.config/mise/conf.d/40-npm-tools.toml" <<'CONFIG'
[tools]
"npm:typescript" = "6"
"npm:typescript-language-server" = { version = "latest", depends = ["npm:typescript"], postinstall = 'ln -sfn "$HOME/.local/share/mise/installs/npm-typescript/6/node_modules/typescript" "$MISE_TOOL_INSTALL_PATH/node_modules/typescript"' }
"npm:@getpaseo/cli" = "latest"
"npm:openskills" = "latest"
"npm:firecrawl-cli" = "latest"
"npm:playwright-core" = "latest"
CONFIG
mise install
# paseo depends on @anthropic-ai/claude-agent-sdk, whose platform package ships its own claude
# (~240M). paseo passes the claude on PATH to the SDK anyway, so point the bundled one at the
# claude installed by the claude stage instead of carrying a second copy.
find "${HOME}/.local/share/mise/installs/npm-getpaseo-cli" -type f -name claude \
        -path '*/@anthropic-ai/claude-agent-sdk-linux-*/claude' \
    -exec ln -sfn "${HOME}/.local/share/mise/installs/claude-code/latest/claude" {} \;
EOF


# The headless shell cannot load extensions, so install only full Chromium.
FROM npm-tools AS browsers
RUN playwright-core install --no-shell chromium


# Shared venv for claude-agent-sdk (security-guidance), pyyaml (skill-creator), pyright (pyright-lsp)
# and readability-lxml/html2text (read skill). python 3.13 because security-guidance only probes
# python3.13 through python3.10. The [env] entry in config.toml points mise at this venv.
FROM mise AS venv
ENV CLAUDE_PLUGINS_VENV="${HOME}/.local/share/claude-plugins-venv"
COPY --link --from=uv-bin /uv /usr/local/bin/
RUN --mount=type=cache,id=uv-cache,target=/home/nonroot/.cache/uv,uid=65532,gid=65532 \
    <<EOF
set -euo pipefail
export UV_LINK_MODE=copy
uv venv --python /usr/bin/python3.13 "${CLAUDE_PLUGINS_VENV}"
uv pip install --python "${CLAUDE_PLUGINS_VENV}/bin/python" \
    claude-agent-sdk pyyaml pyright readability-lxml html2text
# claude-agent-sdk bundles its own claude (~230M); point it at the one from the claude stage.
ln -sfn "${HOME}/.local/share/mise/installs/claude-code/latest/claude" \
    "${CLAUDE_PLUGINS_VENV}/lib/python3.13/site-packages/claude_agent_sdk/_bundled/claude"
mkdir -p "${HOME}/.claude/security"
ln -sfn "${CLAUDE_PLUGINS_VENV}" "${HOME}/.claude/security/agent-sdk-venv"
EOF


# Plugins and skills are fetched from their default branches. The claude binary here only runs
# `claude plugin` and is not the pinned CLAUDE_CODE_VERSION, so a Claude Code bump does not
# refetch every plugin and skill. gh and ripwire come from the cli stage.
FROM npm-tools AS agent-config
COPY --link --from=cli /home/ /home/
RUN --mount=type=cache,id=mise-cache,target=/home/nonroot/.cache/mise,uid=65532,gid=65532 \
    --mount=type=cache,id=mise-downloads-cache,target=/home/nonroot/.local/share/mise/downloads,uid=65532,gid=65532 \
    --mount=type=cache,id=npm-cache,target=/home/nonroot/.npm,uid=65532,gid=65532 \
    --mount=type=cache,id=sigstore-cache,target=/home/nonroot/.cache/sigstore-rust,uid=65532,gid=65532 \
    <<EOF
set -euo pipefail
echo '[tools]' > "${HOME}/.config/mise/conf.d/50-installer.toml"
echo 'claude-code = "latest"' >> "${HOME}/.config/mise/conf.d/50-installer.toml"
mise install claude-code
# shims are not reliable before the final reshim, so put every tool directory on PATH
export PATH="$(mise bin-paths | paste -sd:):${PATH}"

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

# Skills go to ~/.claude/skills first, then every one is linked into ~/.agents/skills for Codex.
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

rm -rf "${HOME}/.codex/skills" "${HOME}/.pi" "${HOME}/.hermes" "${HOME}/.cache/gh"
mkdir -p "${HOME}/.agents/skills"
for s in "${HOME}"/.claude/skills/*; do
    ln -sfn "$s" "${HOME}/.agents/skills/${s##*/}"
done
EOF


FROM mise AS claude
# renovate: datasource=npm packageName=@anthropic-ai/claude-code
ARG CLAUDE_CODE_VERSION=2.1.283
RUN --mount=type=cache,id=mise-cache,target=/home/nonroot/.cache/mise,uid=65532,gid=65532 \
    --mount=type=cache,id=mise-downloads-cache,target=/home/nonroot/.local/share/mise/downloads,uid=65532,gid=65532 \
    --mount=type=cache,id=sigstore-cache,target=/home/nonroot/.cache/sigstore-rust,uid=65532,gid=65532 \
    <<EOF
set -euo pipefail
printf '[tools]\nclaude-code = "%s"\n' "${CLAUDE_CODE_VERSION}" > "${HOME}/.config/mise/conf.d/60-claude.toml"
mise install
rm -rf "${HOME}/.local/share/mise/installs/.mise-installs.toml" "${HOME}/.local/share/mise/shims"
EOF


FROM node AS codex
# renovate: datasource=npm packageName=@openai/codex
ARG CODEX_VERSION=0.157.1
RUN --mount=type=cache,id=mise-cache,target=/home/nonroot/.cache/mise,uid=65532,gid=65532 \
    --mount=type=cache,id=mise-downloads-cache,target=/home/nonroot/.local/share/mise/downloads,uid=65532,gid=65532 \
    --mount=type=cache,id=npm-cache,target=/home/nonroot/.npm,uid=65532,gid=65532 \
    <<EOF
set -euo pipefail
printf '[tools]\n"npm:@openai/codex" = "%s"\n' "${CODEX_VERSION}" > "${HOME}/.config/mise/conf.d/61-codex.toml"
mise install
EOF


FROM node AS opencli
# renovate: datasource=npm packageName=@jackwener/opencli
ARG OPENCLI_VERSION=1.8.7
RUN --mount=type=cache,id=mise-cache,target=/home/nonroot/.cache/mise,uid=65532,gid=65532 \
    --mount=type=cache,id=mise-downloads-cache,target=/home/nonroot/.local/share/mise/downloads,uid=65532,gid=65532 \
    --mount=type=cache,id=npm-cache,target=/home/nonroot/.npm,uid=65532,gid=65532 \
    <<EOF
set -euo pipefail
printf '[tools]\n"npm:@jackwener/opencli" = "%s"\n' "${OPENCLI_VERSION}" > "${HOME}/.config/mise/conf.d/62-opencli.toml"
mise install
EOF


FROM node AS cf
# renovate: datasource=npm packageName=cf
ARG CF_VERSION=1.0.0-beta.5
RUN --mount=type=cache,id=mise-cache,target=/home/nonroot/.cache/mise,uid=65532,gid=65532 \
    --mount=type=cache,id=mise-downloads-cache,target=/home/nonroot/.local/share/mise/downloads,uid=65532,gid=65532 \
    --mount=type=cache,id=npm-cache,target=/home/nonroot/.npm,uid=65532,gid=65532 \
    <<EOF
set -euo pipefail
printf '[tools]\n"npm:cf" = "%s"\n' "${CF_VERSION}" > "${HOME}/.config/mise/conf.d/63-cf.toml"
mise install
EOF


FROM mise AS runtime
USER root:root
# Codex's Linux sandbox runs the first bwrap on PATH; without one it warns and falls back to
# a bundled helper.
RUN install_packages bubblewrap
# Chromium's system libraries. playwright-core comes from a bind mount, so the image gets the
# apt packages without a second copy of node and playwright-core.
RUN --mount=type=bind,from=npm-tools,source=/home/nonroot/.local/share/mise/installs,target=/home/nonroot/.local/share/mise/installs \
    PATH="${HOME}/.local/share/mise/installs/node/latest/bin:${PATH}" \
    "${HOME}/.local/share/mise/installs/npm-playwright-core/latest/node_modules/.bin/playwright-core" install-deps chromium \
    && rm -rf /var/lib/apt/lists/*
USER nonroot:nonroot


FROM runtime AS final
COPY --link --from=ghcr.io/astral-sh/ruff:0.16.9@sha256:fd4a00e8f586c07495822a1c93702737b9a98d826b76d460caa514df7794f259 /ruff /usr/local/bin/
COPY --link --from=ghcr.io/astral-sh/ty:0.0.84@sha256:bfbe9542ee3a7b7c644f0b470cf1bd99543a7598aeb9e539ef121f9a9b7b2784 /ty /usr/local/bin/
COPY --link --from=uv-bin /uv /uvx /usr/local/bin/
COPY --link --from=mikefarah/yq:4.53.6@sha256:cfc4eee658595834ef304eadb0c3ea721f3b7cb6404ad8b7cb909cc5b5145b23 /usr/bin/yq /usr/local/bin/
COPY --link --from=ghcr.io/j178/prek:0.5.3@sha256:f27d17a6b21959c5ba7d65039d72e9502c6951e79cbbfae2c1a0498a4859a5cb /prek /usr/local/bin/
# COPY --link builds each layer as if copying into an empty image, so every directory the
# destination path creates is root:root 755 unless the copied entries include it. Copying
# /home/ (not /home/nonroot/), or naming paths from /./home with --parents, carries the source
# ownership of /home/nonroot and everything below it, and the stages install as nonroot, so no
# --chown is needed. Stages built FROM mise start with an empty home, so all of it is theirs;
# stages built FROM node or npm-tools also hold node, so only their own paths are listed.
# The stages copied whole delete two things after installing, since each copy would replace
# the previous stage's: .mise-installs.toml, which mise only writes to record installs and does
# not read for ls, which or reshim, and the shims, which the mise reshim below recreates.
COPY --link --from=toolchains /home/ /home/
COPY --link --from=cli /home/ /home/
COPY --link --from=node /home/ /home/
COPY --link --parents --from=npm-tools \
    /./home/nonroot/.local/share/mise/installs/npm-typescript \
    /./home/nonroot/.local/share/mise/installs/npm-typescript-language-server \
    /./home/nonroot/.local/share/mise/installs/npm-getpaseo-cli \
    /./home/nonroot/.local/share/mise/installs/npm-openskills \
    /./home/nonroot/.local/share/mise/installs/npm-firecrawl-cli \
    /./home/nonroot/.local/share/mise/installs/npm-playwright-core \
    /./home/nonroot/.config/mise/conf.d/40-npm-tools.toml \
    /
COPY --link --parents --from=browsers /./home/nonroot/.cache/ms-playwright /
COPY --link --from=venv /home/ /home/
COPY --link --parents --from=agent-config \
    /./home/nonroot/.claude \
    /./home/nonroot/.claude.json \
    /./home/nonroot/.agents \
    /./home/nonroot/git \
    /./home/nonroot/.local/share/gh \
    /
COPY --link --parents --from=opencli /./home/nonroot/.local/share/mise/installs/npm-jackwener-opencli /./home/nonroot/.config/mise/conf.d/62-opencli.toml /
COPY --link --parents --from=codex /./home/nonroot/.local/share/mise/installs/npm-openai-codex /./home/nonroot/.config/mise/conf.d/61-codex.toml /
COPY --link --parents --from=cf /./home/nonroot/.local/share/mise/installs/npm-cf /./home/nonroot/.config/mise/conf.d/63-cf.toml /
COPY --link --from=claude /home/ /home/
ENV CLAUDE_PLUGINS_VENV="${HOME}/.local/share/claude-plugins-venv"
# sshd sessions do not inherit ENV, so login shells activate mise (tools, venv, GITHUB_PERSONAL_ACCESS_TOKEN)
# before the non-interactive early return in ~/.bashrc.
RUN --mount=type=cache,id=mise-cache,target=/home/nonroot/.cache/mise,uid=65532,gid=65532 <<EOF
set -euo pipefail
cat > "${HOME}/.config/mise/config.toml" <<'CONFIG'
[env]
_.python.venv = { path = "{{ env.HOME }}/.local/share/claude-plugins-venv", create = true, python = "3.13" }
# github MCP; empty until `gh auth login`
GITHUB_PERSONAL_ACCESS_TOKEN = "{{ exec(command='for g in $HOME/.local/share/mise/installs/gh/latest/*/bin/gh; do $g auth token 2>/dev/null || true; done') }}"
CONFIG
mise reshim
sed -i '1i eval "$(mise activate bash)"\nalias cr=coderabbit' "${HOME}/.bashrc"
EOF
COPY --link --chmod=755 entrypoint.sh /
EXPOSE 8964
ENTRYPOINT [ "catatonit", "-g", "--", "/entrypoint.sh" ]


# CI builds this target before pushing, so the checks run inside BuildKit on the image it is
# about to push, without loading or pulling it. It adds nothing to the default target below.
FROM final AS smoke
RUN <<EOF
set -euo pipefail
claude --version
test -z "$(mise ls 2>&1 >/dev/null)"
# COPY --link into a path below /home/nonroot would leave root-owned directories behind
test -z "$(find "${HOME}" -xdev ! -user nonroot -print -quit)"
# the SDKs' bundled claude must stay symlinks to the one installed by the claude stage
bundled=$(find "${HOME}/.local/share" -name claude -path '*claude[-_]agent[-_]sdk*')
test "$(wc -l <<< "${bundled}")" -eq 2
for c in ${bundled}; do
    test -L "${c}"
    "${c}" --version
done
codex --version
cf --version
paseo --version
vim --version >/dev/null
bwrap --version
yq --version
bash -lc 'python -c "import claude_agent_sdk, yaml" && claude plugin list && ls ~/.agents/skills'
EOF


FROM final
