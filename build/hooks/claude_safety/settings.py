"""Register independent hooks and preserve each user's enable/disable choices."""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROLES = {
    "block-rm": ("PreToolUse", "Bash", "block_rm"),
    "require-tmux": ("PreToolUse", "Bash", "require_tmux"),
    "protected-branches": (
        "PreToolUse",
        "Bash|mcp__.*__merge_pull_request",
        "protected_branches",
    ),
    "post-edit-check": ("PostToolUse", "Write|Edit", "post_edit_check"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable", nargs="+", choices=ROLES)
    parser.add_argument("--disable", nargs="+", choices=ROLES)
    args = parser.parse_args()
    directory = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "settings.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    original = json.dumps(data, sort_keys=True)
    hooks = data.setdefault("hooks", {})
    env = data.setdefault("env", {})
    for entries in hooks.values():
        for entry in entries:
            entry["hooks"] = [
                hook
                for hook in entry.get("hooks", [])
                if not any(
                    value in {"claude_safety." + role[2] for role in ROLES.values()}
                    for value in hook.get("args", [])
                )
            ]
        entries[:] = [entry for entry in entries if entry.get("hooks")]
    for role, (event, matcher, module) in ROLES.items():
        key = "CLAUDE_DEV_HOOK_" + role.upper().replace("-", "_")
        if role in (args.disable or []):
            env[key] = "0"
        if role in (args.enable or []):
            env[key] = "1"
        if env.get(key, os.environ.get(key)) == "0":
            continue
        targets: list[tuple[str, str | None]] = [(event, matcher)]
        if role == "protected-branches":
            targets.append(("UserPromptSubmit", None))
        for event, matcher in targets:
            group = {
                "matcher": matcher,
                "hooks": [
                    {
                        "type": "command",
                        "command": sys.executable,
                        "args": ["-I", "-m", "claude_safety." + module],
                        "timeout": 30,
                        "onFailure": "block",
                    }
                ],
            }
            if matcher is None:
                group.pop("matcher")
            hooks.setdefault(event, []).append(group)
    if json.dumps(data, sort_keys=True) == original:
        return
    with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as temp:
        json.dump(data, temp, indent=2)
        temp.write("\n")
    os.replace(temp.name, path)


if __name__ == "__main__":
    main()
