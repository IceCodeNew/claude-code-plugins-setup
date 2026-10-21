#!/bin/sh
set -eu
hook_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
python=${CLAUDE_HOOK_PYTHON:-"$hook_dir/../bin/python"}
[ -x "$python" ] || python=${CLAUDE_HOOK_PYTHON:-python3}
exec "$python" -I -c 'import runpy, sys; sys.path.insert(0, sys.argv.pop(1)); runpy.run_module("claude_safety.require_tmux", run_name="__main__")' "$hook_dir" "$@"
