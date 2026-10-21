"""Reject shell rm execution in every permission mode."""

from pathlib import Path

from _hook_common import commands, deny, run


def check(payload):
    entries = commands(payload.get("tool_input", {}).get("command", ""))
    if any(Path(words[0]).name == "rm" for words in entries):
        return deny(
            "禁止执行 rm；请改用 trash-cli 的 trash-put -- <path>，不要通过包装命令绕过。"
        )
    return {}


if __name__ == "__main__":
    run(check)
