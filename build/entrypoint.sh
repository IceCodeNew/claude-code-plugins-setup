#!/bin/bash
set -euo pipefail

init_mcp() {
    local defaults="$1" config="${CLAUDE_CONFIG_DIR:-$HOME}/.claude.json" missing name server
    # Compute missing entries only; Claude owns configuration locking and writes.
    missing=$(jq -crn --slurpfile defaults "$defaults" \
        --slurpfile current <(if [ -f "$config" ]; then cat "$config"; else printf '{}'; fi) '
        if ($current | length) != 1 or ($current[0] | type) != "object"
            or (($current[0].mcpServers // {}) | type) != "object"
            or ($defaults | length) != 1 or ($defaults[0].mcpServers | type) != "object"
        then error("Invalid MCP configuration")
        else $defaults[0].mcpServers | to_entries[]
            | select($current[0].mcpServers[.key] == null) | .key + "\t" + (.value | tojson) end') || { echo 'Invalid MCP configuration; no defaults applied.' >&2; return 1; }
    while IFS=$'\t' read -r name server; do
        [ -n "$name" ] || continue
        case " ${CLAUDE_DEV_SKIP_MCP:-} " in *" $name "*) continue ;; esac
        claude mcp add-json --scope user "$name" "$server" || return 1
    done <<< "$missing"
}

if [ "${1:-}" = --init-mcp ]; then
    init_mcp "${2:-/usr/local/share/claude-dev/mcp.json}"
    exit "$?"
fi

# A mounted home hides the image's user MCP configuration.
if ! init_mcp /usr/local/share/claude-dev/mcp.json; then
    echo 'Warning: MCP bootstrap failed; repair the Claude configuration and run /entrypoint.sh --init-mcp.' >&2
fi

/opt/claude-safety/bin/python -E -s /opt/claude-safety/hooks/configure-claude.py

CRONTAB_PATH="${CRONTAB_PATH:-/home/nonroot/crontab}"
touch "${CRONTAB_PATH}"

# Host keys are generated per container (or kept on a mounted home), never baked into the image.
HOST_KEY="${HOME}/.ssh/ssh_host_ed25519_key"
install -d -m 700 "${HOME}/.ssh"
[ -f "${HOST_KEY}" ] || ssh-keygen -q -t ed25519 -N '' -f "${HOST_KEY}"
if [ -n "${SSH_AUTHORIZED_KEYS:-}" ]; then
    printf '%s\n' "${SSH_AUTHORIZED_KEYS}" > "${HOME}/.ssh/authorized_keys"
    chmod 600 "${HOME}/.ssh/authorized_keys"
fi

supercronic "${CRONTAB_PATH}" &
exec /usr/sbin/sshd -D -e "$@"
