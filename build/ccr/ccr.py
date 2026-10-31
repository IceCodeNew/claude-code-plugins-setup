#!/usr/bin/env python3
"""ccr: profile router and context keeper for Claude Code.

The router is a normal Claude Code session started from this command. It launches
child sessions with `claude --bg`, one profile at a time, using:

  --setting-sources ""            ignore the user's always-on settings
  --settings <profile>.json       enable only this profile's plugins/skills/hooks
  --append-system-prompt-file     append the profile's system prompt
  --mcp-config <file>             add this profile's standalone MCP (fff)
                                  (plugin MCPs still load)
  --model <tier model>            router, easy, medium, or hard model

Profiles are generated from build/profiles/profiles.json. The manifest is the
single source of truth for plugin, skill, MCP, keyword, and prompt assignments.
"""

from __future__ import annotations

import argparse
import fcntl
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

VERSION = "1.0.0"
DEFAULT_MODELS = {"router": "haiku", "hard": "opus", "medium": "sonnet", "easy": "haiku"}
CHILD_CONTRACT = "_child-contract.md"
ROUTER_MARKER = "<!-- CCR_PROFILE_INDEX -->"
SAFETY_ROLES = {
    "block-rm": ("PreToolUse", "Bash"),
    "require-tmux": ("PreToolUse", "Bash"),
    "protected-branches": (
        "PreToolUse",
        "Bash|mcp__.*__merge_pull_request",
    ),
    "post-edit-check": ("PostToolUse", "Write|Edit"),
}
# Settings that make providers and credentials work; copied from the user's
# settings because profile sessions deliberately ignore user settings.
AUTH_KEYS = (
    "apiKeyHelper",
    "awsAuthRefresh",
    "awsCredentialExport",
    "gcpAuthRefresh",
    "forceLoginMethod",
    "forceLoginOrgUUID",
    "pluginConfigs",
)
SUBCOMMANDS = {
    "refresh",
    "router",
    "spawn",
    "send",
    "list",
    "status",
    "context",
    "checkpoint",
    "summary",
    "stop",
    "rm",
    "attach",
    "profiles",
    "doctor",
}


class CcrError(Exception):
    """A user-facing ccr failure."""


# ---------------------------------------------------------------------------
# paths and small utilities


def now_iso() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def now_short() -> str:
    return datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M")


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as error:
        raise CcrError(f"Cannot read {path}: {error}") from error


def dump_json(data) -> str:
    return json.dumps(data, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def write_text(path: Path, text: str, mode: int = 0o644) -> bool:
    """Write atomically, return True when the file changed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            if path.read_text() == text:
                return False
        except OSError:
            pass
    fd, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", text=True
    )
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return True


def write_json(path: Path, data, mode: int = 0o600) -> bool:
    return write_text(path, dump_json(data), mode)


@contextmanager
def ledger_lock(path: Path, shared: bool = False):
    """Serialize read-modify-write access to one session ledger."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def state_home(explicit: str | None = None) -> Path:
    value = explicit or os.environ.get("CCR_HOME")
    root = Path(value).expanduser() if value else Path.home() / ".local/state/cc-router"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    return root


def config_dir(explicit: str | None = None) -> Path:
    value = explicit or os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(value).expanduser() if value else Path.home() / ".claude"


def config_dir_path(explicit: str | None) -> Path:
    """Return the config directory without colliding with the parameter name."""
    return config_dir(explicit)


def claude_bin() -> str:
    value = os.environ.get("CLAUDE_BIN") or shutil.which("claude")
    if not value:
        raise CcrError("claude is not on PATH; set CLAUDE_BIN or install Claude Code")
    return value


def source_dir(explicit: str | None = None) -> Path:
    here = Path(__file__).resolve()
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if os.environ.get("CCR_SOURCE_DIR"):
        candidates.append(Path(os.environ["CCR_SOURCE_DIR"]).expanduser())
    candidates += [
        Path("/opt/cc-router"),
        Path.home() / ".local/share/cc-router",
        here.parent.parent / "profiles",
        here.parent.parent,
    ]
    for candidate in candidates:
        if (candidate / "profiles.json").is_file():
            return candidate
    raise CcrError(
        "profiles.json not found; set CCR_SOURCE_DIR or install /opt/cc-router"
    )


def hooks_dir() -> Path:
    here = Path(__file__).resolve()
    candidates = []
    if os.environ.get("CCR_HOOKS_DIR"):
        candidates.append(Path(os.environ["CCR_HOOKS_DIR"]).expanduser())
    candidates += [
        Path("/opt/claude-safety/hooks"),
        Path.home() / ".local/share/cc-router/hooks",
        here.parent.parent / "hooks",
    ]
    for candidate in candidates:
        if (candidate / "block-rm.py").is_file():
            return candidate
    raise CcrError("hook directory not found; set CCR_HOOKS_DIR")


def hook_python() -> str:
    if os.environ.get("CLAUDE_HOOK_PYTHON"):
        return os.environ["CLAUDE_HOOK_PYTHON"]
    manual = Path.home() / ".local/share/claude-hooks-venv/bin/python"
    if manual.is_file():
        return str(manual)
    system = Path("/usr/bin/python3.13")
    return str(system) if system.is_file() else sys.executable


def run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    timeout: int = 120,
    check: bool = False,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            env=env,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
        )
    except FileNotFoundError as error:
        raise CcrError(f"Command not found: {argv[0]}") from error
    except subprocess.TimeoutExpired as error:
        raise CcrError(f"Timed out after {timeout}s: {' '.join(argv[:3])}") from error
    except OSError as error:
        raise CcrError(f"Cannot run {argv[0]}: {error}") from error


def profile_manifest(explicit: str | None = None) -> tuple[Path, dict]:
    root = source_dir(explicit)
    data = load_json(root / "profiles.json")
    if not isinstance(data, dict) or "profiles" not in data:
        raise CcrError(f"Invalid profile manifest: {root / 'profiles.json'}")
    data.setdefault("models", DEFAULT_MODELS)
    for key, value in DEFAULT_MODELS.items():
        data["models"].setdefault(key, value)
    data.setdefault("mcpServers", {})
    data.setdefault("unassignedPlugins", {})
    data.setdefault("unassignedSkills", {})
    return root, data


def user_settings(config: Path) -> dict:
    data = load_json(config / "settings.json", {})
    if not isinstance(data, dict):
        return {}
    return data


def merged_environment(config: Path) -> dict[str, str]:
    """Process environment plus env values from user settings.

    The profile sessions ignore user settings, so gateway/model variables that
    usually live in settings.json must be carried in the process environment.
    Values already exported by the shell win; nothing is written to disk.
    """
    environment = dict(os.environ)
    environment["CLAUDE_CONFIG_DIR"] = str(config)
    settings = user_settings(config)
    values = settings.get("env")
    if isinstance(values, dict):
        for key, value in values.items():
            if key in environment or value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                environment[str(key)] = str(value)
    return environment


def copy_auth_settings(settings: dict, config: Path) -> None:
    source = user_settings(config)
    for key in AUTH_KEYS:
        if key in source and key not in settings:
            settings[key] = source[key]


# ---------------------------------------------------------------------------
# inventory


def parse_plugins_payload(payload) -> list[str]:
    if isinstance(payload, dict):
        payload = payload.get("plugins", payload.get("installed", []))
    if not isinstance(payload, list):
        raise CcrError("Plugin inventory must be a JSON list or {plugins: []}")
    identifiers = []
    for item in payload:
        if isinstance(item, str):
            identifiers.append(item)
        elif isinstance(item, dict):
            identifier = item.get("id") or item.get("plugin")
            if not identifier and item.get("name") and item.get("marketplace"):
                identifier = f"{item['name']}@{item['marketplace']}"
            if identifier:
                identifiers.append(identifier)
    return sorted(set(identifiers))


def installed_plugins(explicit: str | None = None) -> list[str]:
    def from_value(value: str) -> list[str]:
        stripped = value.lstrip()
        if stripped.startswith(("[", "{")):
            try:
                return parse_plugins_payload(json.loads(value))
            except json.JSONDecodeError as error:
                raise CcrError(f"Plugin inventory is not valid JSON: {error}") from error
        path = Path(value).expanduser()
        if path.is_file():
            return parse_plugins_payload(load_json(path))
        raise CcrError(f"Plugin inventory file not found: {path}")

    if explicit:
        return from_value(explicit)
    env_value = os.environ.get("CCR_PLUGINS_JSON")
    if env_value:
        return from_value(env_value)
    result = run([claude_bin(), "plugin", "list", "--json"], timeout=60)
    if result.returncode != 0:
        raise CcrError(
            "claude plugin list --json failed:\n"
            + (result.stderr or result.stdout).strip()
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise CcrError(f"claude plugin list returned invalid JSON: {error}") from error
    return parse_plugins_payload(payload)


def skill_name(directory: Path) -> str:
    try:
        text = (directory / "SKILL.md").read_text(errors="replace")[:4096]
    except OSError:
        return directory.name
    match = re.search(r"(?m)^name:\s*(.+?)\s*$", text)
    if not match:
        return directory.name
    return match.group(1).strip().strip("\"'") or directory.name


def installed_skills(
    explicit: str | None = None, config: Path | None = None
) -> list[str]:
    root = (
        Path(explicit).expanduser()
        if explicit
        else (config or config_dir()) / "skills"
    )
    if not root.is_dir():
        return []
    skills = set()
    for child in sorted(root.iterdir()):
        if child.name.startswith(".") or child.name == "synced":
            continue
        try:
            if child.is_dir() and (child / "SKILL.md").is_file():
                skills.add(skill_name(child))
        except OSError:
            continue
    return sorted(skills)


def expand_skill_patterns(
    patterns: list[str], available: list[str]
) -> tuple[set[str], list[str]]:
    expanded: set[str] = set()
    missing: list[str] = []
    for pattern in patterns:
        matches = fnmatch.filter(available, pattern)
        if matches:
            expanded.update(matches)
        elif "*" not in pattern and "?" not in pattern and "[" not in pattern:
            missing.append(pattern)
    return expanded, missing


# ---------------------------------------------------------------------------
# profile generation


def base_permissions(profile: dict) -> dict:
    permissions = {
        "allow": [
            "Bash(ccr checkpoint *)",
            "Bash(ccr context *)",
            "Bash(git status *)",
            "Bash(ls *)",
            "Bash(jq *)",
        ],
        "ask": [
            "Bash(git push *)",
            "Bash(git reset *)",
            "Bash(git checkout -- *)",
            "Bash(curl *)",
            "Bash(wget *)",
            "Bash(npm install *)",
            "Bash(pnpm install *)",
            "Bash(pip install *)",
            "Bash(uv add *)",
            "Bash(cargo install *)",
        ],
        "deny": [
            "Bash(git diff *--output*)",
            "Bash(git log *--output*)",
            "Bash(git show *--output*)",
        ],
    }
    extra = profile.get("permissions") or {}
    for key in ("allow", "ask", "deny"):
        values = list(permissions.get(key, []))
        for value in extra.get(key, []):
            if value not in values:
                values.append(value)
        permissions[key] = values
    mode = profile.get("permissionMode")
    if mode:
        permissions["defaultMode"] = mode
    return permissions


def router_permissions() -> dict:
    return {
        "allow": [
            "Bash(ccr *)",
            "Bash(claude agents --json *)",
            "Bash(claude logs *)",
            "Bash(claude stop *)",
            "Bash(claude rm *)",
            "Bash(git status *)",
            "Bash(ls *)",
            "Bash(jq *)",
        ],
        "ask": ["Bash(git push *)"],
        "deny": [
            "Edit",
            "Write",
            "NotebookEdit",
            "Bash(git diff *--output*)",
            "Bash(git log *--output*)",
            "Bash(git show *--output*)",
        ],
        "defaultMode": "default",
    }


def hook_entry(script: Path, role: str) -> dict:
    return {
        "type": "command",
        "command": hook_python(),
        "args": ["-E", "-s", str(script)],
        "timeout": 30,
        "onFailure": "block",
    }


def safety_hooks(roles: list[str], root: Path) -> dict:
    hooks: dict[str, list] = {}
    for role in roles:
        if role not in SAFETY_ROLES:
            raise CcrError(f"Unknown safety hook role: {role}")
        script = root / f"{role}.py"
        if not script.is_file():
            raise CcrError(f"Missing safety hook: {script}")
        event, matcher = SAFETY_ROLES[role]
        targets = [(event, matcher)]
        if role == "protected-branches":
            targets.append(("UserPromptSubmit", None))
        for hook_event, hook_matcher in targets:
            group = {"hooks": [hook_entry(script, role)]}
            if hook_matcher is not None:
                group["matcher"] = hook_matcher
            hooks.setdefault(hook_event, []).append(group)
    return hooks


def router_hooks(root: Path) -> dict:
    script = root / "route-hint.py"
    if not script.is_file():
        raise CcrError(f"Missing route hint hook: {script}")
    return {
        "UserPromptSubmit": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": hook_python(),
                        "args": ["-E", "-s", str(script)],
                        "timeout": 5,
                        "onFailure": "continue",
                    }
                ]
            }
        ]
    }


def enabled_safety_roles(roles: list[str], config: Path) -> list[str]:
    user = user_settings(config).get("env") or {}
    enabled = []
    for role in roles:
        key = "CLAUDE_DEV_HOOK_" + role.upper().replace("-", "_")
        value = user.get(key, os.environ.get(key))
        if str(value) != "0":
            enabled.append(role)
    return enabled


def profile_settings(
    name: str,
    profile: dict,
    manifest: dict,
    plugins: list[str],
    skills: list[str],
    config: Path,
    state: Path,
    hooks_root: Path,
) -> tuple[dict, dict]:
    installed = set(plugins)
    enabled = {plugin: False for plugin in plugins}
    missing_plugins = []
    for plugin in profile.get("plugins", []):
        if plugin in installed:
            enabled[plugin] = True
        else:
            missing_plugins.append(plugin)

    skill_overrides = {skill: "off" for skill in skills}
    expanded, missing_skills = expand_skill_patterns(profile.get("skills", []), skills)
    for skill in expanded:
        skill_overrides[skill] = "on"

    settings: dict = {
        "enabledPlugins": enabled,
        "skillOverrides": skill_overrides,
        "permissions": base_permissions(profile),
        "hooks": safety_hooks(
            enabled_safety_roles(
                list(profile.get("hooks", SAFETY_ROLES)), config
            ),
            hooks_root,
        ),
        "env": {
            "CCR_HOME": str(state),
            "CCR_PROFILE": name,
        },
        "includeGitInstructions": profile.get("includeGitInstructions", True),
        "autoMemoryEnabled": profile.get("autoMemoryEnabled", False),
        "disableBundledSkills": profile.get("disableBundledSkills", False),
    }
    for key in ("effortLevel", "autoCompactWindow", "modelSettings", "env"):
        if key in profile:
            if key == "env":
                settings["env"].update(profile["env"])
            else:
                settings[key] = profile[key]
    if profile.get("effort"):
        settings.setdefault("effortLevel", profile["effort"])
    extra = profile.get("settings") or {}
    for key, value in extra.items():
        settings[key] = value
    copy_auth_settings(settings, config)
    return settings, {
        "missing_plugins": missing_plugins,
        "missing_skills": missing_skills,
    }


def router_settings(
    manifest: dict,
    plugins: list[str],
    skills: list[str],
    config: Path,
    state: Path,
    hooks_root: Path,
) -> dict:
    router = manifest.get("router", {})
    models = manifest["models"]
    router_model = os.environ.get("CCR_ROUTER_MODEL") or models.get("router")
    enabled = {plugin: False for plugin in plugins}
    for plugin in router.get("plugins", []):
        if plugin in enabled:
            enabled[plugin] = True
    enabled_skills = set(router.get("skills", []))
    settings: dict = {
        "enabledPlugins": enabled,
        "skillOverrides": {
            skill: ("on" if skill in enabled_skills else "off") for skill in skills
        },
        "permissions": router_permissions(),
        "hooks": router_hooks(hooks_root),
        "env": {
            "CCR_HOME": str(state),
            "CCR_PROFILE": "router",
            "CCR_ROUTER": "1",
        },
        "agent": router.get("agent", "ccr-router"),
        "disableBundledSkills": True,
        "includeGitInstructions": False,
        "autoMemoryEnabled": False,
    }
    if router_model:
        settings["model"] = router_model
    copy_auth_settings(settings, config)
    return settings


def generate_index(
    manifest: dict,
    profiles: dict,
    plugins: list[str],
    skills: list[str],
    paths: dict,
    warnings: list[str],
) -> dict:
    assignments: dict[str, list[str]] = {}
    skill_assignments: dict[str, list[str]] = {}
    orphan_plugins = []
    orphan_skills = []
    for plugin in manifest.get("router", {}).get("plugins", []):
        assignments.setdefault(plugin, []).append("router")
    for name, profile in profiles.items():
        for plugin in profile.get("plugins", []):
            assignments.setdefault(plugin, []).append(name)
        expanded, _ = expand_skill_patterns(profile.get("skills", []), skills)
        for skill in expanded:
            skill_assignments.setdefault(skill, []).append(name)

    known_plugins = set(assignments) | set(manifest.get("unassignedPlugins", {}))
    known_skills = set(skill_assignments) | set(manifest.get("unassignedSkills", {}))
    orphan_plugins = sorted(set(plugins) - known_plugins)
    orphan_skills = sorted(set(skills) - known_skills)
    for plugin in orphan_plugins:
        warnings.append(
            f"installed plugin not classified: {plugin} (hidden everywhere)"
        )
    for skill in orphan_skills:
        warnings.append(f"installed skill not classified: {skill} (hidden everywhere)")

    return {
        "version": manifest.get("version", 1),
        "ccr_version": VERSION,
        "generated_at": now_iso(),
        "models": manifest["models"],
        "model_env": manifest.get("modelEnv", {}),
        "router": manifest.get("router", {}),
        "profiles": profiles,
        "paths": paths,
        "plugin_assignments": assignments,
        "skill_assignments": skill_assignments,
        "unassigned_plugins": manifest.get("unassignedPlugins", {}),
        "unassigned_skills": manifest.get("unassignedSkills", {}),
        "orphan_plugins": orphan_plugins,
        "orphan_skills": orphan_skills,
    }


def profile_index_markdown(manifest: dict) -> str:
    router = manifest.get("router", {})
    lines = [
        "## Profile index",
        "",
        "Generated from `profiles.json`. Pick by domain first, then by tier.",
        "",
        "| profile | use for | default tier |",
        "|---|---|---|",
        f"| `router` | {str(router.get('description', '')).replace('|', chr(92) + '|')} | router |",
    ]
    for name, profile in manifest.get("profiles", {}).items():
        description = str(profile.get("description", "")).replace("|", "\\|")
        lines.append(f"| `{name}` | {description} | {profile.get('tier', 'hard')} |")
    lines += [
        "",
        "Model defaults live in `profiles.json`: "
        + ", ".join(f"{k}={v}" for k, v in manifest["models"].items())
        + ". Override with `CCR_ROUTER_MODEL`, `CCR_HARD_MODEL`, "
        + "`CCR_MEDIUM_MODEL`, `CCR_EASY_MODEL`.",
        "",
        (
            "Default tiers: `quick`/`librarian` easy, `finder` medium, implementation "
            "and review profiles hard. A small Rust edit is `rust` + `--tier easy`; "
            "a local code search is `finder` + `--tier medium`."
        ),
        "",
    ]
    return "\n".join(lines)


def resolve_mcp_server(name: str, definition: dict) -> dict:
    server = dict(definition)
    command = server.get("command")
    if isinstance(command, str) and "/" not in command:
        resolved = shutil.which(command)
        if resolved:
            server["command"] = resolved
        else:
            fallback = Path.home() / ".local/bin" / command
            if fallback.is_file():
                server["command"] = str(fallback)
    return server


COMMAND_MARKER = "<!-- ccr-command -->"


def install_commands(
    source: Path, config: Path, state: Path
) -> tuple[list[str], list[str], list[str]]:
    """Install the user-invocable commands; never overwrite a human's command.

    Commands are global because plugin-scoped commands would be namespaced. They
    set `disable-model-invocation`, so they do not enter the model's skill list.
    The router's prompt forbids running implementation commands; its agent also
    disallows Edit/Write/Agent, so a mis-invoked command cannot implement in the
    router.
    """
    directory = source / "commands"
    target_dir = config / "commands"
    if not directory.is_dir():
        return [], [], []
    installed, skipped, removed = [], [], []
    source_names = set()
    for path in sorted(directory.glob("*.md")):
        name = path.stem
        source_names.add(name)
        body = path.read_text().rstrip()
        if COMMAND_MARKER not in body:
            body = body + "\n\n" + COMMAND_MARKER + "\n"
        target = target_dir / f"{name}.md"
        if target.exists() and COMMAND_MARKER not in target.read_text(errors="replace"):
            skipped.append(name)
            continue
        if write_text(target, body + "\n"):
            installed.append(name)
        else:
            installed.append(name)
    if target_dir.is_dir():
        for path in sorted(target_dir.glob("*.md")):
            if path.stem in source_names:
                continue
            try:
                text = path.read_text(errors="replace")
            except OSError:
                continue
            if COMMAND_MARKER in text:
                path.unlink()
                removed.append(path.stem)
    return installed, skipped, removed


def refresh(args) -> int:
    root, manifest = profile_manifest(getattr(args, "source", None))
    state = state_home(getattr(args, "home", None))
    config = config_dir(getattr(args, "config_dir", None))
    hooks_root = hooks_dir()
    plugins = installed_plugins(getattr(args, "plugins_json", None))
    skills = installed_skills(getattr(args, "skills_dir", None), config)
    profiles = manifest.get("profiles", {})
    if not profiles:
        raise CcrError("profiles.json has no profiles")

    warnings: list[str] = []
    errors: list[str] = []
    generated = {}
    contract = (root / "prompts" / CHILD_CONTRACT).read_text()

    for name, profile in profiles.items():
        target = state / "profiles" / name
        prompt = (root / profile["prompt"]).read_text().rstrip()
        write_text(target / "prompt.md", prompt + "\n\n" + contract.rstrip() + "\n")
        settings, issues = profile_settings(
            name, profile, manifest, plugins, skills, config, state, hooks_root
        )
        write_json(target / "settings.json", settings, mode=0o600)
        selected = {
            server: resolve_mcp_server(server, manifest["mcpServers"][server])
            for server in profile.get("mcp", [])
        }
        write_json(target / "mcp.json", {"mcpServers": selected}, mode=0o600)
        if issues["missing_plugins"]:
            errors.append(
                f"{name}: plugins not installed: " + ", ".join(issues["missing_plugins"])
            )
        for skill in issues["missing_skills"]:
            message = f"{name}: skill not installed: {skill}"
            warnings.append(message)
            if getattr(args, "strict", False):
                errors.append(message)
        generated[name] = {
            **{k: v for k, v in profile.items() if k not in {"prompt", "settings"}},
            "prompt": str(target / "prompt.md"),
            "settings": str(target / "settings.json"),
            "mcp_file": str(target / "mcp.json"),
        }

    for plugin in manifest.get("router", {}).get("plugins", []):
        if plugin not in plugins:
            errors.append(f"router: plugin not installed: {plugin}")
    for skill in manifest.get("router", {}).get("skills", []):
        if skill not in skills:
            errors.append(f"router: skill not installed: {skill}")
    router = router_settings(manifest, plugins, skills, config, state, hooks_root)
    router_file = state / "runtime/router-settings.json"
    write_json(router_file, router, mode=0o600)
    router_servers = {
        server: resolve_mcp_server(server, manifest["mcpServers"][server])
        for server in manifest.get("router", {}).get("mcp", [])
    }
    router_mcp = state / "runtime/router-mcp.json"
    write_json(router_mcp, {"mcpServers": router_servers}, mode=0o600)

    router_prompt = (root / manifest["router"]["prompt"]).read_text().rstrip()
    if ROUTER_MARKER in router_prompt:
        router_prompt = router_prompt.replace(
            ROUTER_MARKER, profile_index_markdown(manifest).rstrip()
        )
    else:
        router_prompt += "\n\n" + profile_index_markdown(manifest).rstrip() + "\n"
    write_text(state / "runtime/router-prompt.md", router_prompt + "\n")

    paths = {
        "source": str(root),
        "config": str(config),
        "state": str(state),
        "router_settings": str(router_file),
        "router_mcp": str(router_mcp),
        "router_prompt": str(state / "runtime/router-prompt.md"),
    }
    index = generate_index(manifest, generated, plugins, skills, paths, warnings)
    if getattr(args, "strict", False):
        for plugin in index["orphan_plugins"]:
            errors.append(f"installed plugin not classified: {plugin}")
        for skill in index["orphan_skills"]:
            errors.append(f"installed skill not classified: {skill}")
    write_json(state / "index.json", index, mode=0o600)

    agent_name = manifest["router"].get("agent", "ccr-router")
    agent_path = config / "agents" / f"{agent_name}.md"
    model = os.environ.get("CCR_ROUTER_MODEL") or manifest["models"].get(
        "router", "haiku"
    )
    frontmatter = "\n".join(
        [
            "---",
            f"name: {agent_name}",
            "description: Route requests to ccr profiles and keep their context current.",
            f"model: {model}",
            "disallowedTools: Edit, Write, NotebookEdit, Agent, Workflow",
            "---",
            "",
        ]
    )
    agent_text = frontmatter + router_prompt + "\n"
    if agent_path.exists() and agent_path.read_text() != agent_text:
        backup = agent_path.with_suffix(".md.bak")
        if not backup.exists():
            write_text(backup, agent_path.read_text(), mode=0o600)
    write_text(agent_path, agent_text, mode=0o600)
    commands_installed, commands_skipped, commands_removed = install_commands(
        root, config, state
    )
    for name in commands_skipped:
        warnings.append(
            f"command {name} already exists without the ccr marker; left untouched"
        )

    summary = {
        "profiles": generated,
        "router": {
            "agent": str(agent_path),
            "settings": str(router_file),
            "mcp": str(router_mcp),
        },
        "plugins": {
            "installed": len(plugins),
            "assigned": len(set(plugins) & set(index["plugin_assignments"])),
            "unassigned": len(set(plugins) & set(manifest.get("unassignedPlugins", {}))),
            "orphan": index["orphan_plugins"],
        },
        "skills": {
            "installed": len(skills),
            "assigned": len(set(skills) & set(index["skill_assignments"])),
            "unassigned": len(set(skills) & set(manifest.get("unassignedSkills", {}))),
            "orphan": index["orphan_skills"],
        },
        "commands": {
            "installed": commands_installed,
            "skipped": commands_skipped,
            "removed": commands_removed,
        },
        "warnings": warnings,
        "errors": errors,
    }
    if getattr(args, "json", False):
        print(dump_json(summary))
    elif not getattr(args, "quiet", False):
        print(
            f"ccr: {len(generated)} profiles + router, {len(plugins)} plugins "
            f"({summary['plugins']['assigned']} assigned, "
            f"{summary['plugins']['unassigned']} unassigned, "
            f"{len(index['orphan_plugins'])} orphan), "
            f"{len(skills)} skills ({len(index['orphan_skills'])} orphan), "
            f"{len(commands_installed)} commands"
        )
        for warning in warnings:
            print(f"ccr: warning: {warning}", file=sys.stderr)
    for error in errors:
        print(f"ccr: error: {error}", file=sys.stderr)
    if errors and getattr(args, "strict", False):
        return 1
    return 0


# ---------------------------------------------------------------------------
# Claude session helpers


def agents_json(threshold: int = 30) -> list[dict]:
    result = run([claude_bin(), "agents", "--json", "--all"], timeout=threshold)
    if result.returncode != 0:
        return []
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def find_agent(entry: dict, agents: list[dict]) -> dict | None:
    session_id = entry.get("session_id")
    short_id = entry.get("id")
    name = entry.get("name")
    for agent in agents:
        if session_id and agent.get("sessionId") == session_id:
            return agent
    for agent in agents:
        if short_id and agent.get("id") == short_id:
            return agent
    for agent in agents:
        if name and agent.get("name") == name:
            return agent
    return None


def read_records(state: Path) -> list[dict]:
    directory = state / "sessions"
    if not directory.is_dir():
        return []
    records = []
    for path in sorted(directory.glob("*/record.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            records.append(data)
    return records


def resolve_record(state: Path, reference: str) -> dict:
    records = read_records(state)
    matches = [
        record
        for record in records
        if reference
        in {
            record.get("id"),
            record.get("local_id"),
            record.get("session_id"),
            record.get("name"),
        }
    ]
    if not matches:
        matches = [
            record
            for record in records
            if str(record.get("session_id", "")).startswith(reference)
            or str(record.get("id", "")).startswith(reference)
            or str(record.get("local_id", "")).startswith(reference)
        ]
    if not matches:
        raise CcrError(f"No ccr session matches {reference!r}; try `ccr list`")
    if len(matches) > 1:
        raise CcrError(
            f"{reference!r} matches several sessions: "
            + ", ".join(str(m.get("id")) for m in matches)
        )
    return matches[0]


def record_path(state: Path, record: dict) -> Path:
    directory = str(record.get("local_id") or record["id"])
    return state / "sessions" / directory / "record.json"


def context_path(state: Path, record: dict) -> Path:
    return Path(record.get("context_file") or state / "sessions" / record["id"] / "context.md")


def trim_ledger(text: str, limit: int = 96 * 1024) -> str:
    if len(text.encode()) <= limit:
        return text

    def head_bytes(value: str, size: int) -> str:
        return value.encode()[:size].decode(errors="ignore")

    def tail_bytes(value: str, size: int) -> str:
        if size <= 0:
            return ""
        return value.encode()[-size:].decode(errors="ignore")

    marker = "\n## Status log"
    if marker not in text:
        return tail_bytes(text, limit)

    head, _, tail = text.partition(marker)
    notice = "\n\n(older status entries trimmed)\n"
    overhead = len(marker.encode()) + len(notice.encode())
    if overhead >= limit:
        return tail_bytes(text, limit)
    available = limit - overhead
    head_size = len(head.encode())
    tail_size = len(tail.encode())
    if head_size <= available:
        head_limit = head_size
        tail_limit = min(tail_size, available - head_limit)
    else:
        head_limit = min(head_size, max(8 * 1024, available // 2), available)
        tail_limit = max(0, available - head_limit)
    result = (
        head_bytes(head, head_limit)
        + marker
        + notice
        + tail_bytes(tail, tail_limit)
    )
    return result


def append_ledger(path: Path, title: str, body: str, source: str) -> None:
    with ledger_lock(path):
        current = path.read_text() if path.exists() else ""
        if not current:
            current = "# ccr session\n\n## Status log\n"
        block = f"\n### {now_short()} · {source}\n\n{body.strip()}\n"
        if title:
            block = f"\n### {now_short()} · {source} · {title}\n\n{body.strip()}\n"
        write_text(path, trim_ledger(current.rstrip() + "\n" + block), mode=0o600)


def initial_ledger(record: dict, prompt: str) -> str:
    return (
        f"# Session {record['id']} · {record['profile']} · {record['tier']}\n\n"
        f"- name: {record['name']}\n"
        f"- cwd: {record['cwd']}\n"
        f"- model: {record['model']}\n"
        f"- created: {record['created_at']}\n\n"
        "## Objective\n\n"
        f"{prompt.strip()}\n\n"
        "## Must-retain context\n\n"
        "(The router updates this section. It is attached to every `ccr send`.)\n\n"
        "## Status log\n"
    )


def write_session_settings(
    profile_settings_file: Path, context: Path, record: dict
) -> Path:
    data = load_json(profile_settings_file, {})
    if not isinstance(data, dict):
        raise CcrError(f"Invalid profile settings: {profile_settings_file}")
    environment = data.setdefault("env", {})
    environment.update(
        {
            "CCR_HOME": str(context.parent.parent),
            "CCR_PROFILE": str(record["profile"]),
            "CCR_SESSION_ID": str(record.get("local_id") or record["id"]),
            "CCR_CONTEXT_FILE": str(record["context_file"]),
        }
    )
    path = context / "settings.json"
    write_json(path, data, mode=0o600)
    return path


def model_for(
    manifest: dict, tier: str, explicit: str | None = None
) -> str | None:
    if explicit:
        return explicit
    env_name = manifest.get("modelEnv", {}).get(tier)
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    return manifest["models"].get(tier)


def preflight(settings_file: Path, profile_plugins: list[str]) -> None:
    """Check that Claude parses the settings and enables the expected plugins.

    `plugin list` does not call a model, so this is cheap and works before auth.
    """
    result = run(
        [
            claude_bin(),
            "--setting-sources",
            "",
            "--settings",
            str(settings_file),
            "plugin",
            "list",
            "--json",
        ],
        timeout=60,
    )
    if result.returncode != 0:
        raise CcrError(
            f"Claude rejected {settings_file}:\n"
            + (result.stderr or result.stdout).strip()
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise CcrError(f"Invalid plugin list output: {error}") from error
    enabled = {
        item.get("id"): bool(item.get("enabled"))
        for item in payload
        if isinstance(item, dict)
    }
    missing = [plugin for plugin in profile_plugins if not enabled.get(plugin)]
    if missing:
        raise CcrError(
            "Profile plugins are not enabled by Claude: " + ", ".join(missing)
        )


def session_environment(
    config: Path, state: Path, record: dict, extra: dict | None = None
) -> dict[str, str]:
    environment = merged_environment(config)
    environment.pop("CCR_ROUTER", None)
    environment.update(
        {
            "CCR_HOME": str(state),
            "CCR_CHILD": "1",
            "CCR_SESSION_ID": str(record.get("local_id") or record["id"]),
            "CCR_CONTEXT_FILE": str(context_path(state, record)),
            "CCR_PROFILE": str(record["profile"]),
        }
    )
    if extra:
        environment.update(extra)
    return environment


def parse_background(output: str, name: str) -> str | None:
    match = re.search(r"backgrounded\s*[·\-]?\s*([0-9a-f]{8})\b", output)
    if match:
        return match.group(1)
    for agent in agents_json():
        if agent.get("name") == name and agent.get("id"):
            return str(agent["id"])
    return None


def print_result(data, as_json: bool) -> None:
    if as_json:
        print(dump_json(data))
        return
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            print(f"{key}: {value}")
    else:
        print(data)


# ---------------------------------------------------------------------------
# commands


def cmd_router(
    cli_args: list[str],
    home: str | None = None,
    source: str | None = None,
    config_dir: str | None = None,
) -> int:
    if os.environ.get("CCR_CHILD"):
        raise CcrError("ccr router cannot run inside a ccr child session")
    leading, cli_args = take_all_common(cli_args)
    home = home or leading.get("home")
    source = source or leading.get("source")
    config_dir = config_dir or leading.get("config_dir")
    state = state_home(home)
    config = config_dir_path(config_dir)
    root, manifest = profile_manifest(source)
    index = load_json(state / "index.json")
    paths = index.get("paths", {}) if isinstance(index, dict) else {}
    artifacts = (
        state / "runtime/router-settings.json",
        state / "runtime/router-mcp.json",
        state / "runtime/router-prompt.md",
        config / "agents" / f"{manifest.get('router', {}).get('agent', 'ccr-router')}.md",
    )
    stale = (
        not index
        or paths.get("source") != str(root)
        or paths.get("config") != str(config)
        or any(not path.is_file() for path in artifacts)
    )
    if stale:
        refresh(
            argparse.Namespace(
                source=source,
                home=home,
                config_dir=config_dir,
                plugins_json=None,
                skills_dir=None,
                json=False,
                quiet=True,
                strict=False,
            )
        )
    router_file = state / "runtime/router-settings.json"
    router = manifest.get("router", {})
    agent_name = router.get("agent", "ccr-router")
    model = model_for(manifest, "router")
    argv = [
        claude_bin(),
        "--setting-sources",
        "",
        "--settings",
        str(router_file),
        "--agent",
        agent_name,
        "--mcp-config",
        str(state / "runtime/router-mcp.json"),
    ]
    if model and "--model" not in cli_args:
        argv += ["--model", model]
    argv += cli_args
    environment = merged_environment(config)
    environment.update({"CCR_HOME": str(state), "CCR_PROFILE": "router"})
    os.execvpe(argv[0], argv, environment)
    return 0


def cmd_spawn(args) -> int:
    if os.environ.get("CCR_CHILD") and not args.force:
        raise CcrError(
            "Refusing to spawn a ccr child from a child session; report back instead"
        )
    _, manifest = profile_manifest(getattr(args, "source", None))
    state = state_home(getattr(args, "home", None))
    config = config_dir(getattr(args, "config_dir", None))
    name = args.profile
    if name not in manifest["profiles"]:
        raise CcrError(
            f"Unknown profile {name!r}; choose from "
            + ", ".join(manifest["profiles"])
        )
    profile = manifest["profiles"][name]
    prompt = args.prompt or ""
    if args.prompt_file:
        if args.prompt_file == "-":
            prompt = sys.stdin.read()
        else:
            prompt = Path(args.prompt_file).expanduser().read_text()
    if not prompt.strip():
        raise CcrError("A task prompt is required (--prompt or --prompt-file)")
    if len(prompt.encode()) > 100 * 1024:
        raise CcrError("Prompt is over 100 KiB; put the detail in the workspace")

    tier = args.tier or profile.get("tier", "hard")
    if tier not in {"hard", "medium", "easy"}:
        raise CcrError("--tier must be hard, medium, or easy")
    model = model_for(manifest, tier, args.model)
    settings_file = state / "profiles" / name / "settings.json"
    prompt_file = state / "profiles" / name / "prompt.md"
    mcp_file = state / "profiles" / name / "mcp.json"
    for required in (settings_file, prompt_file, mcp_file):
        if not required.is_file():
            raise CcrError(f"Missing {required}; run `ccr refresh` first")

    local_id = uuid.uuid4().hex[:8]
    slug = re.sub(r"[^a-z0-9]+", "-", args.name.lower()).strip("-")[:32] or "task"
    session_name = f"ccr-{name}-{slug}-{local_id[:4]}"
    context = state / "sessions" / local_id
    record = {
        "id": local_id,
        "local_id": local_id,
        "session_id": None,
        "name": session_name,
        "profile": name,
        "tier": tier,
        "model": model,
        "cwd": str(Path(args.cwd).expanduser().resolve()) if args.cwd else os.getcwd(),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "context_file": str(context / "context.md"),
        "settings_file": str(context / "settings.json"),
        "profile_settings": str(settings_file),
        "prompt_file": str(prompt_file),
        "mcp_file": str(mcp_file),
        "task": prompt.strip().splitlines()[0][:200],
        "permission_mode": args.permission_mode or profile.get("permissionMode"),
    }

    session_settings = Path(record["settings_file"])
    argv = [
        claude_bin(),
        "--bg",
        "--name",
        session_name,
        "--setting-sources",
        "",
        "--settings",
        str(session_settings),
        "--append-system-prompt-file",
        str(prompt_file),
        "--mcp-config",
        str(mcp_file),
    ]
    if model:
        argv += ["--model", model]
    if record["permission_mode"]:
        argv += ["--permission-mode", record["permission_mode"]]
    if args.worktree is not None:
        argv += ["--worktree"]
        if args.worktree:
            argv += [args.worktree]
    for directory in args.add_dir or []:
        argv += ["--add-dir", directory]
    argv += ["--", prompt]

    if args.dry_run:
        print_result({"argv": argv, "record": record}, args.json)
        return 0
    context.mkdir(parents=True, exist_ok=True, mode=0o700)
    session_settings = write_session_settings(settings_file, context, record)
    if not args.no_preflight:
        preflight(session_settings, profile.get("plugins", []))

    write_text(Path(record["context_file"]), initial_ledger(record, prompt), mode=0o600)
    environment = session_environment(config, state, record)
    result = run(argv, cwd=Path(record["cwd"]), env=environment, timeout=args.timeout)
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        raise CcrError(
            f"claude --bg failed ({result.returncode}):\n{output or '(no output)'}"
        )
    short_id = parse_background(output, session_name)
    if not short_id:
        raise CcrError(
            "Could not identify the background session. Output was:\n"
            + (output or "(empty)")
            + "\nRun `claude agents --json` to inspect it."
        )
    record["id"] = short_id
    agents = agents_json()
    agent = find_agent(record, agents)
    if agent and agent.get("sessionId"):
        record["session_id"] = agent["sessionId"]
    write_json(record_path(state, record), record, mode=0o600)
    append_ledger(
        context_path(state, record),
        "dispatch",
        f"profile={name} tier={tier} model={model} cwd={record['cwd']}",
        "router",
    )
    print_result(
        {
            "id": record["id"],
            "session_id": record["session_id"],
            "name": session_name,
            "profile": name,
            "tier": tier,
            "model": model,
            "cwd": record["cwd"],
            "context": record["context_file"],
            "attach": f"claude attach {record['id']}",
        },
        args.json,
    )
    return 0


def read_message(args) -> str:
    if args.stdin:
        return sys.stdin.read()
    if args.message:
        return " ".join(args.message)
    raise CcrError("Provide a message or --stdin")


def cmd_send(args) -> int:
    if os.environ.get("CCR_CHILD") and not args.force:
        raise CcrError("A ccr child must not dispatch work")
    state = state_home(getattr(args, "home", None))
    config = config_dir(getattr(args, "config_dir", None))
    record = resolve_record(state, args.session)
    message = read_message(args)
    if not message.strip():
        raise CcrError("Empty message")
    settings_file = Path(record.get("settings_file", ""))
    prompt_file = Path(record.get("prompt_file", ""))
    mcp_file = Path(record.get("mcp_file", ""))
    if not settings_file.is_file():
        profile_settings = Path(
            record.get("profile_settings")
            or state / "profiles" / record["profile"] / "settings.json"
        )
        if not profile_settings.is_file():
            raise CcrError(f"Session {record['id']} settings are missing; re-spawn it")
        settings_file = write_session_settings(
            profile_settings, context_path(state, record).parent, record
        )
        record["settings_file"] = str(settings_file)
    if not prompt_file.is_file() or not mcp_file.is_file():
        raise CcrError(f"Session {record['id']} settings are missing; re-spawn it")
    context = context_path(state, record)
    with ledger_lock(context, shared=True):
        ledger = context.read_text().strip() if context.exists() else initial_ledger(
            record, record.get("task", "")
        )
    if args.no_context:
        payload = message
    else:
        payload = (
            f'<ccr-context session="{record["id"]}" profile="{record["profile"]}">\n'
            f"{ledger}\n"
            "</ccr-context>\n\n"
            "<ccr-message>\n"
            f"{message.strip()}\n"
            "</ccr-message>\n"
        )
    if len(payload.encode()) > 120 * 1024:
        if args.no_context or len(message.encode()) > 120 * 1024:
            raise CcrError("Message exceeds 120 KiB; shorten the message")
        raise CcrError(
            "Message plus ledger exceeds 120 KiB; compact it with "
            f"`ccr context {record['id']} --replace -`"
        )
    argv = [
        claude_bin(),
        "--bg",
        "--resume",
        record["session_id"] or record["name"],
        "--name",
        record["name"],
        "--setting-sources",
        "",
        "--settings",
        str(settings_file),
        "--append-system-prompt-file",
        str(prompt_file),
        "--mcp-config",
        str(mcp_file),
    ]
    if record.get("model"):
        argv += ["--model", record["model"]]
    if record.get("permission_mode"):
        argv += ["--permission-mode", record["permission_mode"]]
    argv += ["--", payload]
    if args.dry_run:
        print_result({"argv": argv, "payload": payload}, args.json)
        return 0
    environment = session_environment(config, state, record)
    result = run(argv, cwd=Path(record["cwd"]), env=environment, timeout=args.timeout)
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        raise CcrError(f"claude --resume failed:\n{output or '(no output)'}")
    append_ledger(context, "router instruction", message, "router")
    new_id = parse_background(output, record["name"])
    if new_id and new_id != record["id"]:
        record["id"] = new_id
        agent = find_agent(record, agents_json())
        if agent and agent.get("sessionId"):
            record["session_id"] = agent["sessionId"]
    record["updated_at"] = now_iso()
    write_json(record_path(state, record), record, mode=0o600)
    print_result(
        {
            "id": record["id"],
            "name": record["name"],
            "profile": record["profile"],
            "sent": len(message),
            "attach": f"claude attach {record['id']}",
        },
        args.json,
    )
    return 0


def cmd_context(args) -> int:
    state = state_home(getattr(args, "home", None))
    record = resolve_record(state, args.session)
    path = context_path(state, record)
    if args.replace is not None or args.append is not None:
        body = sys.stdin.read() if (args.replace == "-" or args.append == "-") else (
            args.replace if args.replace is not None else args.append
        )
        if not body or not body.strip():
            raise CcrError("Refusing to write an empty context")
        if args.replace is not None:
            with ledger_lock(path):
                write_text(path, trim_ledger(body.rstrip() + "\n"), mode=0o600)
        else:
            append_ledger(path, "router note", body, "router")
        print(f"updated {path}")
        return 0
    with ledger_lock(path, shared=True):
        print(path.read_text() if path.exists() else "(no context yet)")
    return 0


def cmd_checkpoint(args) -> int:
    state = state_home(getattr(args, "home", None))
    reference = args.session or os.environ.get("CCR_SESSION_ID")
    if not reference:
        raise CcrError("CCR_SESSION_ID is not set; ccr checkpoint runs in a child")
    record = resolve_record(state, reference)
    body = sys.stdin.read() if args.stdin or not args.message else " ".join(args.message)
    body = body or ""
    if not body.strip():
        raise CcrError("Empty checkpoint")
    append_ledger(
        context_path(state, record),
        args.title or "status",
        body,
        args.source or ("child" if os.environ.get("CCR_CHILD") else "router"),
    )
    print(f"checkpoint recorded for {record['id']}")
    return 0


def status_rows(state: Path) -> tuple[list[dict], list[dict]]:
    records = read_records(state)
    agents = agents_json()
    rows = []
    for record in records:
        agent = find_agent(record, agents)
        row = dict(record)
        row["state"] = agent.get("state") if agent else "missing"
        row["status"] = agent.get("status") if agent else None
        row["waiting_for"] = agent.get("waitingFor") if agent else None
        row["session_id"] = record.get("session_id") or (
            agent.get("sessionId") if agent else None
        )
        row["agent_id"] = agent.get("id") if agent else None
        row["age_minutes"] = age_minutes(record.get("created_at"))
        path = context_path(state, record)
        row["last_status"] = last_status(path)
        rows.append(row)
    order = {"blocked": 0, "working": 1, "done": 2, "failed": 3, "stopped": 4, "missing": 5}
    rows.sort(key=lambda row: (order.get(row["state"], 9), row["created_at"]))
    return rows, agents


def age_minutes(timestamp: str | None) -> int | None:
    if not timestamp:
        return None
    try:
        created = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    return max(0, int((datetime.now(UTC) - created).total_seconds() // 60))


def last_status(path: Path) -> str:
    if not path.exists():
        return ""
    text = path.read_text()
    blocks = re.split(r"\n### ", text)
    if len(blocks) < 2:
        return ""
    tail = re.sub(r"\s+", " ", blocks[-1]).strip()
    return tail[:300]


def cmd_list(args) -> int:
    rows, _ = status_rows(state_home(getattr(args, "home", None)))
    if args.json:
        print(dump_json(rows))
        return 0
    if not rows:
        print("No ccr sessions.")
        return 0
    print(f"{'id':8} {'profile':10} {'tier':5} {'state':8} {'age':>6}  name")
    for row in rows:
        age = f"{row['age_minutes']}m" if row["age_minutes"] is not None else "-"
        print(
            f"{row['id']:8} {row['profile']:10} {row['tier']:5} "
            f"{row['state']:8} {age:>6}  {row['name']}"
        )
    return 0


def cmd_status(args) -> int:
    state = state_home(getattr(args, "home", None))
    record = resolve_record(state, args.session)
    agents = agents_json()
    agent = find_agent(record, agents)
    data = dict(record)
    data["agent"] = agent
    data["context"] = context_path(state, record).read_text() if context_path(state, record).exists() else ""
    if args.logs:
        result = run([claude_bin(), "logs", record["id"]], timeout=30)
        data["logs"] = (result.stdout + result.stderr).strip()
    print(dump_json(data) if args.json else json.dumps(data, indent=2, ensure_ascii=False))
    return 0


def cmd_summary(args) -> int:
    rows, _ = status_rows(state_home(getattr(args, "home", None)))
    if args.json:
        print(dump_json(rows))
        return 0
    if not rows:
        print("No ccr sessions.")
        return 0
    print(f"## ccr sessions ({len(rows)})\n")
    print("| id | profile | tier | state | age | task |")
    print("|---|---|---|---|---|---|")
    for row in rows:
        task = re.sub(r"\s+", " ", row.get("task") or "")[:80].replace("|", "\\|")
        age = f"{row['age_minutes']}m" if row["age_minutes"] is not None else "-"
        print(
            f"| {row['id']} | {row['profile']} | {row['tier']} | "
            f"{row['state']} | {age} | {task} |"
        )
    attention = [row for row in rows if row["state"] == "blocked"]
    if attention:
        print("\n### Needs attention\n")
        for row in attention:
            print(f"- {row['id']} ({row['profile']}): {row['waiting_for'] or 'blocked'}")
    latest = [row for row in rows if row.get("last_status")]
    if latest:
        print("\n### Latest status\n")
        for row in latest[:8]:
            print(f"- {row['id']} ({row['profile']}): {row['last_status']}")
    return 0


def cmd_stop(args) -> int:
    state = state_home(getattr(args, "home", None))
    record = resolve_record(state, args.session)
    result = run([claude_bin(), "stop", record["id"]], timeout=60)
    print((result.stdout + result.stderr).strip() or f"stopped {record['id']}")
    return result.returncode


def cmd_rm(args) -> int:
    state = state_home(getattr(args, "home", None))
    record = resolve_record(state, args.session)
    result = run([claude_bin(), "rm", record["id"]], timeout=60)
    print((result.stdout + result.stderr).strip() or f"removed {record['id']}")
    if result.returncode == 0:
        local_id = str(record.get("local_id") or record["id"])
        directory = state / "sessions" / local_id
        archive = state / "archive" / local_id
        archive.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory.exists():
            if archive.exists():
                shutil.rmtree(archive)
            shutil.move(str(directory), str(archive))
    return result.returncode


def cmd_attach(args) -> int:
    state = state_home(getattr(args, "home", None))
    record = resolve_record(state, args.session)
    argv = [claude_bin(), "attach", record["id"]]
    os.execvpe(
        argv[0],
        argv,
        merged_environment(config_dir(getattr(args, "config_dir", None))),
    )
    return 0


def cmd_profiles(args) -> int:
    _, manifest = profile_manifest(getattr(args, "source", None))
    if args.json:
        print(dump_json(manifest))
        return 0
    print(f"{'profile':10} {'tier':5} {'plugins':>7} {'skills':>7} {'mcp':>5}  description")
    router = manifest.get("router", {})
    print(
        f"{'router':10} {'router':5} {len(router.get('plugins', [])):7} {0:7} {0:5}  "
        f"{router.get('description', '')}"
    )
    for name, profile in manifest["profiles"].items():
        print(
            f"{name:10} {profile.get('tier', 'hard'):5} "
            f"{len(profile.get('plugins', [])):7} {len(profile.get('skills', [])):7} "
            f"{len(profile.get('mcp', [])):5}  {profile.get('description', '')}"
        )
    return 0


def cmd_doctor(args) -> int:
    state = state_home(getattr(args, "home", None))
    config = config_dir(getattr(args, "config_dir", None))
    root, manifest = profile_manifest(getattr(args, "source", None))
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[tuple[str, str]] = []

    try:
        version = run([claude_bin(), "--version"], timeout=30).stdout.strip()
        checks.append(("claude", version))
    except CcrError as error:
        errors.append(str(error))

    index = load_json(state / "index.json")
    for label, path in (
        ("index", state / "index.json"),
        ("router settings", state / "runtime/router-settings.json"),
        ("router mcp", state / "runtime/router-mcp.json"),
        ("router agent", config / "agents" / f"{manifest['router']['agent']}.md"),
    ):
        if path.is_file():
            checks.append((label, str(path)))
        else:
            errors.append(f"missing {label}: {path}; run `ccr refresh`")

    try:
        plugins = installed_plugins(args.plugins_json)
        skills = installed_skills(args.skills_dir, config)
        assigned_plugins = set(manifest.get("router", {}).get("plugins", []))
        assigned_skills = set()
        for profile in manifest["profiles"].values():
            assigned_plugins.update(profile.get("plugins", []))
            expanded, missing = expand_skill_patterns(profile.get("skills", []), skills)
            assigned_skills.update(expanded)
            for skill in missing:
                warnings.append(f"profile skill not installed: {skill}")
        known_plugins = assigned_plugins | set(manifest.get("unassignedPlugins", {}))
        known_skills = assigned_skills | set(manifest.get("unassignedSkills", {}))
        for plugin in sorted(set(plugins) - known_plugins):
            errors.append(f"installed plugin not classified: {plugin}")
        for plugin in sorted(assigned_plugins - set(plugins)):
            errors.append(f"profile plugin not installed: {plugin}")
        for skill in sorted(set(skills) - known_skills):
            errors.append(f"installed skill not classified: {skill}")
    except CcrError as error:
        errors.append(str(error))
        plugins, skills = [], []

    if index:
        for name, profile in manifest["profiles"].items():
            settings_file = state / "profiles" / name / "settings.json"
            if not settings_file.is_file():
                errors.append(f"missing settings for {name}")
                continue
            try:
                settings = load_json(settings_file, {})
            except CcrError as error:
                errors.append(str(error))
                continue
            for plugin in profile.get("plugins", []):
                if not settings.get("enabledPlugins", {}).get(plugin):
                    errors.append(f"{name}: {plugin} is not enabled")
            fp_check_enabled = bool(
                settings.get("enabledPlugins", {}).get("fp-check@trailofbits")
            )
            if name == "review" and not fp_check_enabled:
                errors.append("review: fp-check is not enabled")
            if name != "review" and fp_check_enabled:
                errors.append(f"{name}: fp-check must be review-only")
        router_file = state / "runtime/router-settings.json"
        if router_file.is_file():
            router = load_json(router_file, {})
            expected = set(manifest.get("router", {}).get("plugins", []))
            enabled_router = {
                plugin
                for plugin, value in router.get("enabledPlugins", {}).items()
                if value
            }
            if enabled_router != expected:
                errors.append(
                    "router plugins mismatch: expected "
                    + ", ".join(sorted(expected))
                    + "; got "
                    + ", ".join(sorted(enabled_router))
                )
            if "fp-check@trailofbits" in enabled_router:
                errors.append("router settings enable fp-check")

    skills_root = config / "skills"
    if skills_root.is_dir():
        for child in sorted(skills_root.iterdir()):
            if child.name.startswith(".") or child.name == "synced":
                continue
            if child.is_dir() and not (child / "SKILL.md").is_file():
                warnings.append(
                    f"skill entry has no top-level SKILL.md: {child.name}"
                )

    command_source = root / "commands"
    if command_source.is_dir():
        for path in sorted(command_source.glob("*.md")):
            target = config / "commands" / path.name
            if not target.is_file():
                errors.append(f"command not installed: {path.stem}; run `ccr refresh`")
            elif COMMAND_MARKER not in target.read_text(errors="replace"):
                warnings.append(f"command {path.stem} was not overwritten (no marker)")

    user = user_settings(config)
    enabled_user = [
        plugin for plugin, value in (user.get("enabledPlugins") or {}).items() if value
    ]
    if enabled_user:
        warnings.append(
            "user settings enable plugins that ccr ignores: "
            + ", ".join(enabled_user[:8])
            + ("..." if len(enabled_user) > 8 else "")
        )
    mcp = run([claude_bin(), "mcp", "get", "fff"], timeout=30)
    if mcp.returncode == 0:
        warnings.append(
            "user-scope fff MCP is registered; ccr ignores it, plain claude does not. "
            "Remove it with: claude mcp remove --scope user fff"
        )

    for tier in ("router", "hard", "medium", "easy"):
        env_name = manifest.get("modelEnv", {}).get(tier)
        value = os.environ.get(env_name) if env_name else None
        checks.append(
            (
                f"model {tier}",
                (
                    f"{env_name or '-'}={value or '(default)'} -> "
                    f"{manifest['models'].get(tier)}"
                ),
            )
        )

    if not args.no_preflight and plugins:
        router_file = state / "runtime/router-settings.json"
        if router_file.is_file():
            try:
                preflight(router_file, manifest.get("router", {}).get("plugins", []))
                checks.append(("preflight router", "ok"))
            except CcrError as error:
                errors.append(f"router: {error}")
        for name, profile in manifest["profiles"].items():
            settings_file = state / "profiles" / name / "settings.json"
            if not settings_file.is_file():
                continue
            try:
                preflight(settings_file, profile.get("plugins", []))
                checks.append((f"preflight {name}", "ok"))
            except CcrError as error:
                errors.append(f"{name}: {error}")

    for label, value in checks:
        print(f"ok   {label}: {value}")
    for warning in warnings:
        print(f"warn {warning}")
    for error in errors:
        print(f"FAIL {error}", file=sys.stderr)
    if errors:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)", file=sys.stderr)
        return 1
    print(f"\nok: {len(checks)} checks, {len(warnings)} warning(s)")
    return 0


# ---------------------------------------------------------------------------
# argument parsing


def take_all_common(argv: list[str]) -> tuple[dict[str, str], list[str]]:
    """Remove path options anywhere; used for the router's Claude argument list."""
    values: dict[str, str] = {}
    remaining: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in {"--home", "--source", "--config-dir"}:
            if index + 1 >= len(argv):
                raise CcrError(f"{arg} requires a value")
            values[arg[2:].replace("-", "_")] = argv[index + 1]
            index += 2
        elif arg.startswith(("--home=", "--source=", "--config-dir=")):
            key, value = arg[2:].split("=", 1)
            values[key.replace("-", "_")] = value
            index += 1
        else:
            remaining.append(arg)
            index += 1
    return values, remaining


def take_common(argv: list[str]) -> tuple[dict[str, str], list[str]]:
    """Consume leading path options; leave everything else for the subcommand."""
    values: dict[str, str] = {}
    remaining = list(argv)
    while remaining:
        arg = remaining[0]
        if arg in {"--home", "--source", "--config-dir"}:
            if len(remaining) < 2:
                raise CcrError(f"{arg} requires a value")
            values[arg[2:].replace("-", "_")] = remaining[1]
            remaining = remaining[2:]
        elif arg.startswith(("--home=", "--source=", "--config-dir=")):
            key, value = arg[2:].split("=", 1)
            values[key.replace("-", "_")] = value
            remaining = remaining[1:]
        else:
            break
    return values, remaining


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--home",
        default=argparse.SUPPRESS,
        help="ccr state directory (default ~/.local/state/cc-router)",
    )
    parser.add_argument(
        "--source",
        default=argparse.SUPPRESS,
        help="directory containing profiles.json",
    )
    parser.add_argument(
        "--config-dir",
        default=argparse.SUPPRESS,
        help="Claude config directory (default ~/.claude)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ccr",
        description="Profile router and context keeper for Claude Code.",
    )
    parser.add_argument("--version", action="version", version=f"ccr {VERSION}")
    add_common(parser)
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("refresh", help="regenerate profile settings from the manifest")
    add_common(p)
    p.add_argument("--plugins-json", help="plugin inventory JSON (file or inline)")
    p.add_argument("--skills-dir", help="skills directory (default <config>/skills)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.set_defaults(func=refresh)

    p = sub.add_parser("router", help="start the user-facing router session")
    p.add_argument("cli_args", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_router)

    p = sub.add_parser("spawn", help="dispatch a background child session")
    add_common(p)
    p.add_argument("--profile", required=True)
    p.add_argument("--tier", choices=["hard", "medium", "easy"])
    p.add_argument("--name", default="task")
    p.add_argument("--cwd")
    p.add_argument("--model")
    p.add_argument("--permission-mode")
    p.add_argument("--prompt")
    p.add_argument("--prompt-file")
    p.add_argument("--worktree", nargs="?", const="")
    p.add_argument("--add-dir", action="append")
    p.add_argument("--force", action="store_true", help="allow spawning from a ccr child")
    p.add_argument("--no-preflight", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--timeout", type=int, default=120)
    p.set_defaults(func=cmd_spawn)

    p = sub.add_parser("send", help="send a message with the context ledger attached")
    add_common(p)
    p.add_argument("session")
    p.add_argument("message", nargs="*")
    p.add_argument("--stdin", action="store_true")
    p.add_argument("--no-context", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--timeout", type=int, default=120)
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("list", help="list ccr sessions")
    add_common(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("status", help="show one session, its context, and optional logs")
    add_common(p)
    p.add_argument("session")
    p.add_argument("--logs", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("context", help="read or update a session's context ledger")
    add_common(p)
    p.add_argument("session")
    p.add_argument("--append", nargs="?", const="-")
    p.add_argument("--replace", nargs="?", const="-")
    p.set_defaults(func=cmd_context)

    p = sub.add_parser("checkpoint", help="append a child status block")
    p.add_argument("--home", default=argparse.SUPPRESS)
    p.add_argument("--config-dir", default=argparse.SUPPRESS)
    p.add_argument("message", nargs="*")
    p.add_argument("--session")
    p.add_argument("--stdin", action="store_true")
    p.add_argument("--title")
    p.add_argument("--source", choices=["child", "router"])
    p.set_defaults(func=cmd_checkpoint)

    p = sub.add_parser("summary", help="compact progress summary for the router")
    add_common(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("stop", help="stop a child session")
    add_common(p)
    p.add_argument("session")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("rm", help="remove a child session and archive its ledger")
    add_common(p)
    p.add_argument("session")
    p.set_defaults(func=cmd_rm)

    p = sub.add_parser("attach", help="attach to a child session")
    add_common(p)
    p.add_argument("session")
    p.set_defaults(func=cmd_attach)

    p = sub.add_parser("profiles", help="show the profile manifest")
    add_common(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_profiles)

    p = sub.add_parser("doctor", help="check isolation, assignment, and runtime state")
    add_common(p)
    p.add_argument("--plugins-json")
    p.add_argument("--skills-dir")
    p.add_argument("--no-preflight", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.set_defaults(func=cmd_doctor)

    return parser


def _dispatch(argv: list[str]) -> int:
    leading, argv = take_common(argv)
    if not argv:
        return cmd_router([], **leading)
    if argv[0] in {"-h", "--help"}:
        build_parser().print_help()
        return 0
    if argv[0] == "--version":
        print(f"ccr {VERSION}")
        return 0
    if argv[0] == "router":
        return cmd_router(argv[1:], **leading)
    if argv[0] not in SUBCOMMANDS:
        return cmd_router(argv, **leading)
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    for key, value in leading.items():
        if not hasattr(args, key):
            setattr(args, key, value)
    return int(args.func(args) or 0)


def main(argv: list[str] | None = None) -> int:
    try:
        return _dispatch(list(sys.argv[1:] if argv is None else argv))
    except CcrError as error:
        print(f"ccr: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
