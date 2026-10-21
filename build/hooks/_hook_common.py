"""Shared shell parsing and Claude hook protocol."""

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import bashlex

WRAPPER_VALUE_FLAGS = {
    "sudo": {
        "-u",
        "-g",
        "-h",
        "-p",
        "--user",
        "--group",
        "--host",
        "--prompt",
    },
    "env": {"-u", "-C", "--unset", "--chdir"},
    "xargs": {
        "-n",
        "-P",
        "-I",
        "-d",
        "-s",
        "--max-args",
        "--max-procs",
        "--replace",
        "--delimiter",
    },
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "exec": {"-a"},
}


class PolicyError(Exception):
    """The operation cannot be checked safely."""


def deny(reason):
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def commands(text, depth=0):
    if depth > 8:
        raise PolicyError("Shell nesting exceeds the supported limit")
    # bashlex 0.18 does not remove quotes from heredoc delimiters.
    tokens = list(bashlex.tokenizer.tokenizer(text, bashlex.state.parserstate()))
    quoted = []
    for index, token in enumerate(tokens[:-1]):
        if token.ttype.name in {"LESS_LESS", "LESS_LESS_MINUS"}:
            word = tokens[index + 1]
            if word.value.startswith(("'", '"')):
                quoted.append(
                    (token.lexpos, word.endlexpos, shlex.split(word.value)[0])
                )
    for begin, finish, delimiter in reversed(quoted):
        start = text.find("\n", finish)
        end = (
            re.search(
                r"(?m)^\t*" + re.escape(delimiter) + r"(?:\n|$)", text[start + 1 :]
            )
            if start >= 0
            else None
        )
        if end is None:
            raise PolicyError("Unterminated quoted heredoc")
        text = (
            text[:begin]
            + " < /dev/null"
            + text[finish:start]
            + "\n"
            + text[start + 1 + end.end() :]
        )
    try:
        nodes = bashlex.parse(text)
    except (bashlex.errors.ParsingError, NotImplementedError) as error:
        raise PolicyError(f"Unsupported shell syntax: {error}") from error
    result = []

    def visit(node):
        if node.kind == "command":
            words = [
                shlex.split(text[part.pos[0] : part.pos[1]])[0]
                for part in node.parts
                if part.kind == "word"
            ]
            if words:
                result.append(words)
        for value in vars(node).values():
            if isinstance(value, bashlex.ast.node):
                visit(value)
            elif isinstance(value, list):
                for child in value:
                    if isinstance(child, bashlex.ast.node):
                        visit(child)

    for node in nodes:
        visit(node)
    expanded = []
    for words in result:
        while words and Path(words[0]).name in {
            "command",
            "builtin",
            "exec",
            "env",
            "sudo",
            "xargs",
            "timeout",
            "nohup",
        }:
            wrapper = Path(words.pop(0)).name
            while words and (
                words[0].startswith("-")
                or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0])
            ):
                flag = words.pop(0)
                if wrapper == "env" and (
                    flag == "-S" or flag.startswith("--split-string")
                ):
                    raise PolicyError(
                        "Use a literal command instead of env --split-string"
                    )
                if flag in WRAPPER_VALUE_FLAGS.get(wrapper, ()) and words:
                    words.pop(0)
            if wrapper == "timeout" and words:
                words.pop(0)
        if not words:
            continue
        executable = Path(words[0]).name
        if "$" in words[0] or "`" in words[0] or executable in {"eval", "source", "."}:
            raise PolicyError(
                "Dynamic shell execution cannot be checked; use a literal command"
            )
        if executable in {"bash", "sh", "dash", "zsh"}:
            flags = [
                i
                for i, word in enumerate(words[1:], 1)
                if word.startswith("-") and "c" in word
            ]
            if flags and flags[0] + 1 < len(words):
                expanded.extend(commands(words[flags[0] + 1], depth + 1))
        if executable == "find":
            for marker in ("-exec", "-execdir", "-ok", "-okdir"):
                if marker in words:
                    nested = words[words.index(marker) + 1 :]
                    end = next(
                        (i for i, word in enumerate(nested) if word in {";", "+"}),
                        len(nested),
                    )
                    expanded.extend(commands(shlex.join(nested[:end]), depth + 1))
        expanded.append(words)
    return expanded


def run(check):
    payload = json.load(sys.stdin)
    try:
        result = check(payload)
    except (
        PolicyError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        if payload.get("hook_event_name") == "UserPromptSubmit":
            print(f"Merge authorization was not recorded: {error}", file=sys.stderr)
            sys.exit(2)
        result = deny(
            f"Hook 无法安全判断此次操作：{error}。请使用明确命令；删除文件请改用 trash-put，并继续其他不受阻塞的任务。"
        )
    print(json.dumps(result, ensure_ascii=False))
