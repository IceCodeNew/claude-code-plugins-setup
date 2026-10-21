"""Keep development servers inside tmux sessions."""

import os
from pathlib import Path

from .common import commands, deny, run


def check(payload):
    if os.environ.get("TMUX"):
        return {}
    for words in commands(payload.get("tool_input", {}).get("command", "")):
        executable = Path(words[0]).name
        args = words[1:]
        dev = (
            (
                executable in {"npm", "pnpm", "bun", "yarn"}
                and args
                and (
                    args[0] in {"dev", "start", "serve"}
                    or args[:1] == ["run"]
                    and len(args) > 1
                    and args[1] in {"dev", "start", "serve"}
                )
            )
            or executable == "vite"
            and (
                not args
                or args[0] in {"dev", "serve", "preview"}
                or args[0].startswith("--host")
            )
            or executable == "uvicorn"
            and not any(arg in {"--help", "--version"} for arg in args)
            or executable in {"npx", "bunx"}
            and args
            and Path(args[0]).name
            in {"vite", "serve", "http-server", "next", "nuxt", "astro"}
            and not any(arg in {"build", "--help", "--version"} for arg in args)
            or executable in {"next", "nuxt", "astro", "fastapi"}
            and args[:1] in [["dev"], ["run"]]
        )
        if dev:
            return deny(
                "dev server 必须在 tmux 中运行；使用 tmux new-session -d -s dev '<command>'，并继续其他任务。"
            )
    return {}


if __name__ == "__main__":
    run(check)
