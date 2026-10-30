#!/usr/bin/env python3
"""Deterministic keyword hint for the ccr router.

Runs as a UserPromptSubmit command hook in the router settings only. It never
calls a model, never blocks, and never raises: on any error it exits 0 silently.
The hint is advisory; the router still classifies the whole request.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HARD_SIGNALS = (
    "design",
    "architecture",
    "debug",
    "refactor",
    "migrate",
    "migration",
    "plan",
    "multi-file",
    "across several files",
    "code review",
    "audit",
    "security",
    "vulnerability",
    "verify",
    "implement",
    "feature",
    "设计",
    "架构",
    "调试",
    "重构",
    "迁移",
    "规划",
    "多文件",
    "跨文件",
    "审查",
    "审计",
    "安全",
    "漏洞",
    "验证",
    "实现",
    "功能",
)
MEDIUM_SIGNALS = (
    "find all",
    "find every",
    "all occurrences",
    "call sites",
    "callers",
    "usages",
    "references",
    "where is",
    "where are",
    "which module",
    "locate",
    "search for",
    "grep",
    "查找",
    "在哪儿",
    "在哪里",
    "调用点",
    "引用",
    "定义",
    "搜索",
    "定位",
    "所有出现",
)
EASY_SIGNALS = (
    "quick question",
    "small edit",
    "one file",
    "single file",
    "typo",
    "rename",
    "what is",
    "how do i",
    "run the command",
    "run this",
    "小改",
    "单文件",
    "改个名",
    "查一下",
    "是什么",
    "怎么用",
    "跑一下",
    "执行命令",
)
MAX_HINT = 900


def keyword_present(prompt: str, keyword: str) -> bool:
    needle = keyword.strip().lower()
    if not needle:
        return False
    if re.search(r"[a-z]", needle):
        pattern = r"(?<![a-z0-9_])" + re.escape(needle) + r"(?![a-z0-9_])"
        return re.search(pattern, prompt) is not None
    return needle in prompt


def hint(prompt: str, index: dict) -> str | None:
    prompt = prompt.lower()
    scored = []
    for order, (name, profile) in enumerate(index.get("profiles", {}).items()):
        hits = [
            keyword
            for keyword in profile.get("keywords", [])
            if keyword_present(prompt, keyword)
        ]
        if hits:
            scored.append((len(hits), -order, name, hits))
    scored.sort(reverse=True)
    candidates = scored[:3]

    hard_hits = [signal for signal in HARD_SIGNALS if keyword_present(prompt, signal)]
    medium_hits = [signal for signal in MEDIUM_SIGNALS if keyword_present(prompt, signal)]
    easy_hits = [signal for signal in EASY_SIGNALS if keyword_present(prompt, signal)]
    if hard_hits:
        # A code-change verb outranks a question or lookup signal.
        tier = ("hard", hard_hits)
    elif medium_hits:
        tier = ("medium", medium_hits)
    elif easy_hits:
        tier = ("easy", easy_hits)
    else:
        tier = (None, [])

    if not candidates and tier[0] is None:
        return None

    parts = []
    if candidates:
        rendered = []
        for count, _, name, hits in candidates:
            rendered.append(f"{name} ({count} keyword hits: {', '.join(hits[:4])})")
        parts.append("Profile candidates: " + "; ".join(rendered) + ".")
    if tier[0]:
        parts.append(
            f"Tier signal: {tier[0]} ({len(tier[1])} signals: "
            + ", ".join(tier[1][:4])
            + ")."
        )
    parts.append("This is a keyword hint only; classify the full request.")
    text = "<ccr-route-hint>" + " ".join(parts) + "</ccr-route-hint>"
    return text[:MAX_HINT]


def main() -> int:
    try:
        if os.environ.get("CCR_PROFILE") not in (None, "router"):
            return 0
        payload = json.loads(sys.stdin.read() or "{}")
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return 0
        home = Path(
            os.environ.get("CCR_HOME", Path.home() / ".local/state/cc-router")
        ).expanduser()
        index_path = home / "index.json"
        if not index_path.is_file():
            return 0
        index = json.loads(index_path.read_text())
        if not isinstance(index, dict):
            return 0
        text = hint(prompt, index)
        if not text:
            return 0
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": text,
                    }
                },
                ensure_ascii=False,
            )
        )
    except Exception:  # noqa: BLE001 - a hint hook must never break the prompt
        # A hint hook must never break the prompt.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
