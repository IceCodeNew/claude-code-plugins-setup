#!/bin/bash
set -euo pipefail

CRONTAB_PATH="${CRONTAB_PATH:-/home/nonroot/crontab}"
touch "${CRONTAB_PATH}"

supercronic "${CRONTAB_PATH}" &
exec raft-daemon "$@"
