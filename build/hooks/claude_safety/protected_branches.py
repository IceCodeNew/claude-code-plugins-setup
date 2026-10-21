"""Protect shared branch writes through pushes and authorized PR merges."""

import fcntl
import fnmatch
import hashlib
import importlib.resources
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from .common import PolicyError, commands, deny, run


def gh_json(args, cwd):
    try:
        result = subprocess.run(
            ["gh", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=8,
            check=True,
        )
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise PolicyError(
            "GitHub metadata is unavailable; use an explicit repository and PR"
        ) from error


def repository(cwd):
    data = gh_json(["repo", "view", "--json", "nameWithOwner,url"], cwd)
    return urlparse(data["url"]).hostname, data["nameWithOwner"]


def option(words, names, default=None):
    for i, word in enumerate(words):
        for name in names:
            if word == name:
                if i + 1 >= len(words):
                    raise PolicyError(f"Missing {name} value")
                default = words[i + 1]
            elif word.startswith(name + "="):
                default = word.split("=", 1)[1]
            elif len(name) == 2 and word.startswith(name) and len(word) > 2:
                default = word[2:]
    return default


def merge_target(words, cwd):
    executable = Path(words[0]).name
    if executable in {"curl", "wget"} and re.search(
        r"/pulls/\d+/merge|mergePullRequest|enablePullRequestAutoMerge|enqueuePullRequest",
        " ".join(words),
    ):
        raise PolicyError(
            "Use gh pr merge with an explicit PR instead of raw HTTP merge requests"
        )
    if executable != "gh":
        return None
    args = words[1:]
    if args and args[0].startswith("-") and "merge" in args:
        raise PolicyError(
            "Put gh options after pr merge and specify the repository explicitly"
        )
    if args[:2] == ["pr", "merge"]:
        if "--disable-auto" in args and "--auto" not in args:
            return None
        selected_repo = option(args, {"-R", "--repo"}, os.environ.get("GH_REPO"))
        host = os.environ.get("GH_HOST", "github.com")
        selector = None
        skip = False
        for value in args[2:]:
            if skip:
                skip = False
                continue
            if value in {
                "-R",
                "--repo",
                "--match-head-commit",
                "-t",
                "--subject",
                "-b",
                "--body",
                "-F",
                "--body-file",
                "-A",
                "--author-email",
            }:
                skip = True
            elif not value.startswith("-") and selector is None:
                selector = value
        if selector and selector.startswith("https://"):
            parsed = urlparse(selector)
            match = re.fullmatch(r"/([^/]+/[^/]+)/pull/(\d+)/?", parsed.path)
            if not match:
                raise PolicyError("Unsupported PR URL")
            return parsed.hostname, match[1], int(match[2])
        if selected_repo:
            bits = selected_repo.split("/")
            if len(bits) == 3:
                host, selected_repo = bits[0], "/".join(bits[1:])
            elif len(bits) != 2:
                raise PolicyError("Use owner/repo for the target repository")
        else:
            host, selected_repo = repository(cwd)
        if not selector or not selector.isdecimal():
            data = gh_json(
                [
                    "pr",
                    "view",
                    *([selector] if selector else []),
                    "-R",
                    f"{host}/{selected_repo}",
                    "--json",
                    "number",
                ],
                cwd,
            )
            selector = str(data["number"])
        return host, selected_repo, int(selector)
    if args[:1] == ["api"]:
        endpoint = next(
            (
                value
                for value in args[1:]
                if value == "graphql"
                or value.startswith(("repos/", "/repos/", "https://"))
            ),
            "",
        )
        opaque = any(
            value == "--input" or "@" in value or value.startswith("--input=")
            for value in args
        )
        if endpoint.startswith("https://"):
            parsed = urlparse(endpoint)
            if parsed.hostname != "api.github.com":
                raise PolicyError(
                    "Use an explicit gh API hostname and repository endpoint"
                )
            endpoint = parsed.path
        if endpoint == "graphql":
            query = " ".join(args)
            if opaque or re.search(
                r"\b(mergePullRequest|enablePullRequestAutoMerge|enqueuePullRequest)\b",
                query,
            ):
                raise PolicyError(
                    "Use an explicit gh pr merge <number> -R owner/repo; opaque GraphQL merges are blocked"
                )
            return None
        match = re.fullmatch(r"/?repos/([^/]+/[^/]+)/pulls/(\d+)/merge", endpoint)
        if match:
            method = option(
                args,
                {"-X", "--method"},
                "POST"
                if any(
                    v.startswith(("-f", "-F", "--field", "--raw-field")) for v in args
                )
                or opaque
                else "GET",
            )
            if method.upper() in {"GET", "HEAD"}:
                return None
            return (
                option(args, {"--hostname"}, os.environ.get("GH_HOST", "github.com")),
                match[1],
                int(match[2]),
            )
    return None


def state_file(payload):
    session = payload.get("session_id")
    if not isinstance(session, str) or not session:
        raise PolicyError("Missing session identity")
    directory = (
        Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
        / "claude-safety"
    )
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory / (hashlib.sha256(session.encode()).hexdigest() + ".json")


def state(payload, change=None):
    path = state_file(payload)
    with path.with_suffix(".lock").open("a") as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(path.read_text()) if path.exists() else []
        if not isinstance(data, list):
            raise PolicyError("Invalid merge authorization state")
        if change is not None:
            change(data)
            with tempfile.NamedTemporaryFile(
                mode="w", dir=path.parent, delete=False
            ) as temp:
                json.dump(data, temp)
            os.replace(temp.name, path)
        return data


def record(payload):
    if payload.get("source") not in {None, "user", "sdk"}:
        return {}
    prompt = payload.get("prompt", "")
    match = re.fullmatch(r"(允许|撤销)合并 PR #([1-9][0-9]*)\n?", prompt)
    if payload.get("agent_id") or payload.get("origin", {}).get("kind") not in {
        None,
        "human",
    }:
        return {}
    if prompt == "撤销所有合并授权":
        state(payload, lambda data: data.clear())
    elif match and match[1] == "撤销":
        # Revocation must work even when GitHub or repository discovery is unavailable.
        state(
            payload,
            lambda data: data.__setitem__(
                slice(None),
                [key for key in data if not key.endswith(f"#{int(match[2])}")],
            ),
        )
    elif match:
        host, repo = repository(payload["cwd"])
        key = f"{host}/{repo}#{int(match[2])}".lower()

        def change(data):
            if key in data:
                data.remove(key)
            if match[1] == "允许":
                data.append(key)

        state(payload, change)
    return {}


def check_merge(payload, entries):
    if payload.get("permission_mode") not in {"bypassPermissions", None}:
        return {}
    tool = payload.get("tool_name", "")
    values = payload.get("tool_input", {})
    cwd = payload["cwd"]
    targets = []
    if tool.endswith("__merge_pull_request"):
        targets.append(
            (
                "github.com",
                f"{values['owner']}/{values['repo']}",
                int(values["pullNumber"]),
            )
        )
    elif tool == "Bash":
        text = values.get("command", "")
        if re.search(r"\bgh\b.*\b(?:merge|api)\b", text) and re.search(
            r"\b(?:GH_REPO|GH_HOST)=", text
        ):
            raise PolicyError(
                "Run merge commands without inline GitHub environment changes"
            )
        targets = [target for words in entries if (target := merge_target(words, cwd))]
        if targets and (
            re.search(
                r"(?:^|[;&|])\s*(?:cd|pushd|export)\b|\b(?:GH_REPO|GH_HOST)=", text
            )
            or any(words[:2] == ["gh", "pr"] and "edit" in words for words in entries)
        ):
            raise PolicyError(
                "Run the merge as a separate explicit command without context changes"
            )
    for host, repo, number in targets:
        metadata = gh_json(
            ["api", "--hostname", host, f"repos/{repo}/pulls/{number}"], cwd
        )
        base = metadata["base"]
        if (
            base["repo"]["full_name"].lower() != repo.lower()
            or metadata["number"] != number
        ):
            raise PolicyError("GitHub returned a different PR identity")
        if protected_branch(
            host, repo, base["ref"], base["repo"]["default_branch"], cwd
        ):
            key = f"{host}/{repo}#{number}".lower()
            if key not in state(payload):
                return deny(
                    f"合并 PR #{number} 到受保护分支尚未获授权。请用普通消息申请用户回复「允许合并 PR #{number}」，不要使用阻塞式 AskUserQuestion；继续完成不依赖此次合并的其他任务，不要重试或绕过合并限制。"
                )
    return {}


def protected_branch(host, repo, branch, default, cwd):
    patterns = json.loads(
        importlib.resources.files(__package__)
        .joinpath("protected-branches.json")
        .read_text()
    )
    if branch == default or any(
        fnmatch.fnmatchcase(branch.lower(), pattern) for pattern in patterns
    ):
        return True
    pages = gh_json(
        [
            "api",
            "--hostname",
            host,
            f"repos/{repo}/branches?protected=true&per_page=100",
            "--paginate",
            "--slurp",
        ],
        cwd,
    )
    return any(item["name"] == branch for page in pages for item in page)


def check_push(words, cwd):
    if Path(words[0]).name != "git" or "push" not in words[1:]:
        return
    index = words.index("push")
    if index != 1:
        raise PolicyError("Run git push as a separate explicit command")
    args = words[index + 1 :]
    if any("$" in arg or "`" in arg for arg in args):
        raise PolicyError(
            "Use literal push remotes and refspecs instead of shell expansions"
        )
    if any(arg in {"--all", "--branches", "--mirror"} for arg in args):
        raise PolicyError("明确指定 push 目标分支，避免批量写入受保护分支。")
    positional = []
    skip = False
    for arg in args:
        if skip:
            skip = False
        elif arg in {"--repo", "--receive-pack", "--exec", "-o", "--push-option"}:
            skip = True
        elif not arg.startswith("-"):
            positional.append(arg)
    remote = positional[0] if positional else "origin"
    urls = (
        subprocess.check_output(
            ["git", "remote", "get-url", "--push", "--all", remote], cwd=cwd, text=True
        ).splitlines()
        if ":" not in remote and "/" not in remote
        else [remote]
    )
    destinations = []
    for url in urls:
        if url.startswith("git@"):
            host, repo = url[4:].split(":", 1)
        else:
            parsed = urlparse(url)
            host, repo = parsed.hostname, parsed.path.lstrip("/")
        repo = repo.removesuffix(".git")
        if not host or len(repo.split("/")) != 2:
            raise PolicyError("Cannot resolve the push destination repository")
        metadata = gh_json(["api", "--hostname", host, f"repos/{repo}"], cwd)
        destinations.append((host, repo, metadata["default_branch"]))
    refs = positional[1:]
    if not refs and "--tags" in args:
        return
    if not refs:
        raise PolicyError(
            "明确指定 push 目标分支，避免 Git upstream/refspec 配置改变实际目标。"
        )
    if any(":" not in ref for ref in refs):
        mapping = subprocess.run(
            ["git", "config", "--get-all", f"remote.{remote}.push"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if mapping.returncode not in {0, 1}:
            raise PolicyError("Cannot read Git push mappings")
        if mapping.stdout.strip():
            raise PolicyError(
                "Use source:refs/heads/destination when the remote has configured push mappings"
            )
    for ref in refs:
        target = ref.lstrip("+").rsplit(":", 1)[-1].removeprefix("refs/heads/")
        if target == "HEAD":
            target = subprocess.check_output(
                ["git", "symbolic-ref", "--short", "HEAD"], cwd=cwd, text=True
            ).strip()
        if not target or any(char in target for char in "*?["):
            raise PolicyError("Use an explicit target branch for git push")
        if any(
            protected_branch(host, repo, target, default, cwd)
            for host, repo, default in destinations
        ):
            raise PolicyError(
                f"禁止直接 push 到受保护分支 {target}；请通过已授权的 PR 合并。"
            )


def check(payload):
    if payload.get("hook_event_name") == "UserPromptSubmit":
        return record(payload)
    entries = None
    if payload.get("tool_name") == "Bash":
        entries = commands(payload.get("tool_input", {}).get("command", ""))
        if any(
            Path(words[0]).name == "git" and "push" in words[1:] for words in entries
        ) and any(
            Path(words[0]).name in {"cd", "pushd", "export"} for words in entries
        ):
            raise PolicyError(
                "Run push as a separate command from its target repository"
            )
        for words in entries:
            check_push(words, payload["cwd"])
    return check_merge(payload, entries)


if __name__ == "__main__":
    run(check)
