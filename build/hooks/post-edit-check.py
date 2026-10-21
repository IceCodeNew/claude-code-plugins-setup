"""Report bounded, file-local diagnostics after edits."""

import os
import shutil
import subprocess
from pathlib import Path

from _hook_common import run


def post_edit(payload):
    file = Path(payload.get("tool_input", {}).get("file_path", ""))
    if not file.is_file():
        return {}
    if file.suffix == ".py":
        command = ["ruff", "check", str(file)]
    elif file.suffix in {".ts", ".tsx", ".js", ".jsx"}:
        command = ["oxlint", str(file)]
    elif file.suffix == ".rs":
        command = ["rustfmt", "--check", str(file)]
    elif file.suffix == ".go":
        command = ["gofmt", "-d", str(file)]
    else:
        return {}
    if not shutil.which(command[0]):
        return {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": f"Post-edit check skipped: install {command[0]} locally; no package was downloaded.",
            }
        }
    try:
        result = subprocess.run(
            command,
            cwd=payload["cwd"],
            env=os.environ,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        message = f"Post-edit {command[0]} timed out after 20 seconds. Run the project check explicitly."
    else:
        if result.returncode == 0 and not (command[0] == "gofmt" and result.stdout):
            return {}
        message = f"Post-edit {command[0]} exit {result.returncode}:\n{result.stdout}{result.stderr}"
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": message,
        }
    }


if __name__ == "__main__":
    run(post_edit)
