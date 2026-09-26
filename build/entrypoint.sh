#!/bin/bash
set -euo pipefail

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
