"""Profile isolation and ccr routing tests.

These tests do not call a model. `ccr refresh` uses a plugin inventory fixture;
`ccr spawn`, `send`, and `doctor` use a fake `claude` binary that only answers
`plugin list`, `agents --json`, `mcp`, `--version`, and `--bg`/`--resume`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent if (HERE.parent / "build/profiles/profiles.json").is_file() else None
if ROOT:
    SOURCE = ROOT / "build/profiles"
    CCR = [sys.executable, str(ROOT / "build/ccr/ccr.py")]
    HOOKS = ROOT / "build/hooks"
    TSV = ROOT / "claude-plugins.tsv"
else:
    SOURCE = Path("/opt/cc-router")
    CCR = ["/usr/local/bin/ccr"]
    HOOKS = Path("/opt/claude-safety/hooks")
    TSV = None


def plugin_ids() -> list[str]:
    if TSV and TSV.is_file():
        return [
            line.split("\t")[0]
            for line in TSV.read_text().splitlines()
            if line.strip()
        ]
    result = subprocess.run(
        ["claude", "plugin", "list", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [item["id"] for item in json.loads(result.stdout)]


def skill_names(manifest: dict) -> list[str]:
    names = set()
    for profile in manifest["profiles"].values():
        for name in profile.get("skills", []):
            if "*" not in name:
                names.add(name)
    names.update(manifest.get("unassignedSkills", {}))
    names.add("ripwire-review")
    return sorted(names)


FAKE_CLAUDE = """#!/usr/bin/env python3
import json
import sys

args = sys.argv[1:]
if "plugin" in args and "list" in args:
    settings = None
    for index, value in enumerate(args):
        if value == "--settings" and index + 1 < len(args):
            settings = args[index + 1]
    data = json.load(open(settings)) if settings else {}
    print(json.dumps([{"id": key, "enabled": value} for key, value in data.get("enabledPlugins", {}).items()]))
elif "agents" in args:
    print("[]")
elif "--version" in args:
    print("2.1.312 (Claude Code)")
elif "mcp" in args:
    sys.exit(1)
elif "--agent" in args:
    print(" ".join(args))
elif "--disable-slash-commands" in args:
    print(" ".join(args))
elif "--bg" in args or "--resume" in args:
    print("backgrounded · deadbeef · ccr-test")
else:
    print("unexpected fake claude args: " + " ".join(args), file=sys.stderr)
    sys.exit(2)
"""


class Profiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((SOURCE / "profiles.json").read_text())
        cls.plugins = plugin_ids()
        cls.directory = tempfile.TemporaryDirectory(prefix="ccr-profiles-")
        cls.root = Path(cls.directory.name)
        cls.home = cls.root / "home"
        cls.config = cls.root / "config"
        cls.state = cls.root / "state"
        cls.skills = cls.config / "skills"
        for name in skill_names(cls.manifest):
            target = cls.skills / name
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: fixture\n---\n"
            )
        cls.fake = cls.home / "bin/claude"
        cls.fake.parent.mkdir(parents=True)
        cls.fake.write_text(FAKE_CLAUDE)
        cls.fake.chmod(0o755)
        cls.inventory = cls.root / "plugins.json"
        cls.inventory.write_text(json.dumps([{"id": p} for p in cls.plugins]))
        cls.env = {
            **os.environ,
            "HOME": str(cls.home),
            "CLAUDE_CONFIG_DIR": str(cls.config),
            "CCR_HOME": str(cls.state),
            "CCR_SOURCE_DIR": str(SOURCE),
            "CCR_HOOKS_DIR": str(HOOKS),
            "CLAUDE_HOOK_PYTHON": sys.executable,
            "CCR_PLUGINS_JSON": str(cls.inventory),
            "CLAUDE_BIN": str(cls.fake),
        }
        cls.refresh = subprocess.run(
            CCR + ["refresh", "--strict"],
            env=cls.env,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def settings(self, profile: str) -> dict:
        return json.loads(
            (self.state / f"profiles/{profile}/settings.json").read_text()
        )

    def test_refresh_succeeds_and_writes_every_profile(self):
        self.assertEqual(self.refresh.returncode, 0, self.refresh.stderr)
        for name in self.manifest["profiles"]:
            self.assertTrue((self.state / f"profiles/{name}/settings.json").is_file())
            self.assertTrue((self.state / f"profiles/{name}/prompt.md").is_file())
            self.assertTrue((self.state / f"profiles/{name}/mcp.json").is_file())
        self.assertTrue((self.state / "index.json").is_file())
        self.assertTrue((self.config / "agents/ccr-router.md").is_file())

    def test_fp_check_is_review_only(self):
        for name in self.manifest["profiles"]:
            value = self.settings(name)["enabledPlugins"].get(
                "fp-check@trailofbits", False
            )
            self.assertEqual(value, name == "review", name)
        router = json.loads(
            (self.state / "runtime/router-settings.json").read_text()
        )
        self.assertFalse(router["enabledPlugins"].get("fp-check@trailofbits", False))

    def test_fff_is_enabled_for_every_role(self):
        for name in self.manifest["profiles"]:
            mcp = json.loads((self.state / f"profiles/{name}/mcp.json").read_text())
            self.assertIn("fff", mcp["mcpServers"], name)
        router_mcp = json.loads((self.state / "runtime/router-mcp.json").read_text())
        self.assertIn("fff", router_mcp["mcpServers"])

    def test_router_has_expected_plugins_and_skills(self):
        router = json.loads(
            (self.state / "runtime/router-settings.json").read_text()
        )
        expected = set(self.manifest["router"].get("plugins", []))
        enabled = {
            plugin
            for plugin, value in router["enabledPlugins"].items()
            if value
        }
        self.assertEqual(enabled, expected)
        self.assertEqual(
            {skill for skill, value in router["skillOverrides"].items() if value == "on"},
            set(self.manifest["router"].get("skills", [])),
        )
        self.assertNotIn("deniedMcpServers", router)
        self.assertEqual(router["agent"], "ccr-router")
        self.assertEqual(set(router["hooks"]), {"UserPromptSubmit"})
        router_mcp = json.loads((self.state / "runtime/router-mcp.json").read_text())
        self.assertIn("fff", router_mcp["mcpServers"])

    def test_each_profile_enables_only_its_plugins(self):
        for name, profile in self.manifest["profiles"].items():
            settings = self.settings(name)
            enabled = {
                plugin
                for plugin, value in settings["enabledPlugins"].items()
                if value
            }
            self.assertEqual(enabled, set(profile.get("plugins", [])), name)

    def test_profile_skills_are_on_and_everything_else_is_off(self):
        all_skills = {path.name for path in self.skills.iterdir()}
        for name, profile in self.manifest["profiles"].items():
            settings = self.settings(name)
            self.assertEqual(set(settings["skillOverrides"]), all_skills)
            on = {
                skill
                for skill, value in settings["skillOverrides"].items()
                if value == "on"
            }
            expected = set()
            for pattern in profile.get("skills", []):
                if "*" in pattern:
                    expected.update(
                        skill
                        for skill in all_skills
                        if skill.startswith(pattern.rstrip("*"))
                    )
                else:
                    expected.add(pattern)
            self.assertEqual(on, expected & all_skills, name)
        router = json.loads(
            (self.state / "runtime/router-settings.json").read_text()
        )
        self.assertEqual(set(router["skillOverrides"]), all_skills)
        self.assertEqual(
            {skill for skill, value in router["skillOverrides"].items() if value == "on"},
            set(self.manifest["router"].get("skills", [])),
        )

    def test_safety_hooks_exist_in_children_and_not_router(self):
        for name in self.manifest["profiles"]:
            settings = self.settings(name)
            self.assertIn("PreToolUse", settings["hooks"])
            self.assertIn("PostToolUse", settings["hooks"])
        router = json.loads(
            (self.state / "runtime/router-settings.json").read_text()
        )
        self.assertNotIn("PreToolUse", router["hooks"])

    def test_prompts_include_contract_and_router_index(self):
        for name in self.manifest["profiles"]:
            prompt = (self.state / f"profiles/{name}/prompt.md").read_text()
            self.assertIn("Router contract", prompt)
            self.assertIn("ccr checkpoint", prompt)
        router = (self.state / "runtime/router-prompt.md").read_text()
        self.assertIn("## Profile index", router)
        self.assertIn("ccr spawn", router)
        for name in self.manifest["profiles"]:
            self.assertIn(f"`{name}`", router)

    def test_commands_are_installed_model_invocable_and_marked(self):
        commands = self.config / "commands"
        self.assertTrue(commands.is_dir())
        installed = {path.stem for path in commands.glob("*.md")}
        self.assertIn("review", installed)
        self.assertIn("security-check", installed)
        self.assertIn("plan", installed)
        self.assertIn("research", installed)
        for name in installed:
            text = (commands / f"{name}.md").read_text()
            self.assertIn("<!-- ccr-command -->", text)
            self.assertNotIn("disable-model-invocation: true", text)

    def test_offline_plugins_are_deleted_and_disabled_ones_are_kept(self):
        deleted = {
            "feature-dev@claude-plugins-official",
            "code-review@claude-plugins-official",
            "pr-review-toolkit@claude-plugins-official",
            "ralph-loop@claude-plugins-official",
            "double-shot-latte@superpowers-marketplace",
        }
        disabled = {
            "skill-creator@claude-plugins-official",
            "redis-development@claude-plugins-official",
        }
        self.assertEqual(set(self.manifest["unassignedPlugins"]), disabled)
        self.assertFalse(deleted & set(self.plugins))
        self.assertTrue(disabled <= set(self.plugins))
        for name in self.manifest["profiles"]:
            enabled = self.settings(name)["enabledPlugins"]
            for plugin in deleted | disabled:
                self.assertFalse(enabled.get(plugin, False), (name, plugin))

    def test_waza_skills_are_fully_installed_and_ui_has_no_command(self):
        dockerfile = (HOOKS.parent / "Dockerfile").read_text() if (HOOKS.parent / "Dockerfile").is_file() else ""
        if not dockerfile:
            dockerfile = (SOURCE.parent.parent / "build/Dockerfile").read_text() if (SOURCE.parent.parent / "build/Dockerfile").is_file() else ""
        if dockerfile:
            self.assertIn("tw93/Waza", dockerfile)
            self.assertNotIn("tw93/Waza/skills/check", dockerfile)
        self.assertIn("ui", self.manifest["profiles"]["frontend"]["skills"])
        self.assertIn("check", self.manifest["profiles"]["review"]["skills"])
        self.assertIn("health", self.manifest["profiles"]["dev"]["skills"])
        self.assertFalse((self.config / "commands/ui.md").exists())

    def test_hookify_all_roles_and_gh_cli_dev_roles(self):
        self.assertNotIn("session-report@claude-plugins-official", self.plugins)
        for name in self.manifest["profiles"]:
            enabled = self.settings(name)["enabledPlugins"]
            self.assertTrue(enabled.get("hookify@claude-plugins-official"), name)
        router = json.loads((self.state / "runtime/router-settings.json").read_text())
        self.assertTrue(router["enabledPlugins"].get("hookify@claude-plugins-official"))
        for name in ("dev", "rust", "go", "python", "frontend", "review"):
            enabled = self.settings(name)["enabledPlugins"]
            self.assertTrue(enabled.get("gh-cli@trailofbits"), name)

    def test_pure_prompt_plugins_stay_plugins(self):
        dev = self.settings("dev")["enabledPlugins"]
        for plugin in (
            "code-simplifier@claude-plugins-official",
            "commit-commands@claude-plugins-official",
            "claude-code-setup@claude-plugins-official",
        ):
            self.assertTrue(dev.get(plugin), plugin)
        self.assertFalse((self.config / "commands/simplify.md").exists())
        self.assertFalse((self.config / "commands/commit.md").exists())

    def test_finder_is_medium_and_librarian_is_easy(self):
        self.assertEqual(self.manifest["profiles"]["finder"]["tier"], "medium")
        self.assertEqual(self.manifest["profiles"]["librarian"]["tier"], "easy")
        self.assertEqual(self.manifest["profiles"]["oracle"]["tier"], "hard")
        finder = self.settings("finder")
        self.assertTrue(finder.get("permissions", {}).get("deny"))
        self.assertTrue((self.state / "profiles/finder/mcp.json").is_file())
        self.assertEqual(
            finder["skillOverrides"].get("ripwire-review"),
            "on",
        )

    def test_frontend_and_language_roles_own_their_toolchain(self):
        frontend = self.settings("frontend")["enabledPlugins"]
        dev = self.settings("dev")["enabledPlugins"]
        self.assertTrue(frontend.get("modern-web-guidance@claude-plugins-official"))
        self.assertTrue(frontend.get("typescript-lsp@claude-plugins-official"))
        self.assertFalse(dev.get("typescript-lsp@claude-plugins-official"))
        prompt = (self.state / "profiles/frontend/prompt.md").read_text()
        self.assertIn("oxlint", prompt)
        self.assertIn("oxfmt", prompt)
        self.assertTrue(self.settings("go")["enabledPlugins"].get("modern-go-guidelines@goland-claude-marketplace"))
        self.assertTrue(self.settings("python")["enabledPlugins"].get("modern-python@trailofbits"))
        self.assertIn(
            "code-review-page",
            {skill for skill, value in self.settings("review")["skillOverrides"].items() if value == "on"},
        )

    def test_rust_security_review_belongs_to_review_profile(self):
        review = self.settings("review")["enabledPlugins"]
        rust = self.settings("rust")["enabledPlugins"]
        self.assertTrue(review.get("rust-review@trailofbits"))
        self.assertTrue(review.get("rust-analyzer-lsp@claude-plugins-official"))
        self.assertFalse(rust.get("rust-review@trailofbits"))

    def test_manifest_covers_every_installed_plugin(self):
        assigned = set(self.manifest["router"].get("plugins", []))
        for profile in self.manifest["profiles"].values():
            assigned.update(profile.get("plugins", []))
        unassigned = set(self.manifest.get("unassignedPlugins", {}))
        self.assertEqual(assigned & unassigned, set())
        self.assertEqual(assigned | unassigned, set(self.plugins))

    def test_route_hint_prefers_rust_and_easy(self):
        hook = HOOKS / "route-hint.py"
        rust = subprocess.run(
            [sys.executable, str(hook)],
            input=json.dumps({"prompt": "refactor this rust crate, fix the unsafe block"}),
            env={**self.env, "CCR_PROFILE": "router"},
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(rust.returncode, 0, rust.stderr)
        text = json.loads(rust.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("rust", text)
        self.assertIn("hard", text)
        medium = subprocess.run(
            [sys.executable, str(hook)],
            input=json.dumps({"prompt": "find all call sites of this function"}),
            env={**self.env, "CCR_PROFILE": "router"},
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        text = json.loads(medium.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("finder", text)
        self.assertIn("medium", text)
        easy = subprocess.run(
            [sys.executable, str(hook)],
            input=json.dumps({"prompt": "改个名，跑一下测试"}),
            env={**self.env, "CCR_PROFILE": "router"},
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        text = json.loads(easy.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("quick", text)
        self.assertIn("easy", text)
        silent = subprocess.run(
            [sys.executable, str(hook)],
            input=json.dumps({"prompt": "hello"}),
            env={**self.env, "CCR_PROFILE": "router"},
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(silent.returncode, 0)
        self.assertEqual(silent.stdout, "")


class Routing(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ccr-routing-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.home = self.root / "home"
        self.config = self.root / "config"
        self.state = self.root / "state"
        self.skills = self.config / "skills"
        manifest = json.loads((SOURCE / "profiles.json").read_text())
        for name in skill_names(manifest):
            target = self.skills / name
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: fixture\n---\n"
            )
        self.fake = self.home / "bin/claude"
        self.fake.parent.mkdir(parents=True)
        self.fake.write_text(FAKE_CLAUDE)
        self.fake.chmod(0o755)
        self.inventory = self.root / "plugins.json"
        self.inventory.write_text(json.dumps([{"id": p} for p in plugin_ids()]))
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "CLAUDE_CONFIG_DIR": str(self.config),
            "CCR_HOME": str(self.state),
            "CCR_SOURCE_DIR": str(SOURCE),
            "CCR_HOOKS_DIR": str(HOOKS),
            "CLAUDE_HOOK_PYTHON": sys.executable,
            "CCR_PLUGINS_JSON": str(self.inventory),
            "CLAUDE_BIN": str(self.fake),
        }
        refresh = subprocess.run(
            CCR + ["refresh", "--strict"],
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        self.assertEqual(refresh.returncode, 0, refresh.stderr)

    def ccr(self, *args, **kwargs):
        return subprocess.run(
            CCR + list(args),
            env={**self.env, **kwargs.get("env", {})},
            input=kwargs.get("input"),
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )

    def test_spawn_dry_run_has_all_isolation_flags(self):
        result = self.ccr(
            "spawn",
            "--profile",
            "rust",
            "--tier",
            "easy",
            "--name",
            "small",
            "--prompt",
            "fix",
            "--dry-run",
            "--json",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        argv = data["argv"]
        for flag in (
            "--bg",
            "--setting-sources",
            "--settings",
            "--append-system-prompt-file",
            "--mcp-config",
            "--model",
        ):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("--model") + 1], "haiku")
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "")
        self.assertIn("--permission-mode", argv)
        self.assertNotIn("--agent", argv)
        self.assertEqual(data["record"]["profile"], "rust")
        medium = self.ccr(
            "spawn",
            "--profile",
            "finder",
            "--tier",
            "medium",
            "--name",
            "find",
            "--prompt",
            "where is the parser",
            "--dry-run",
            "--json",
        )
        self.assertEqual(medium.returncode, 0, medium.stderr)
        medium_argv = json.loads(medium.stdout)["argv"]
        self.assertEqual(medium_argv[medium_argv.index("--model") + 1], "sonnet")

    def test_spawn_send_checkpoint_and_summary(self):
        spawned = self.ccr(
            "spawn",
            "--profile",
            "rust",
            "--tier",
            "hard",
            "--name",
            "routing-test",
            "--prompt",
            "fix the unsafe block",
            "--json",
        )
        self.assertEqual(spawned.returncode, 0, spawned.stderr)
        record = json.loads(spawned.stdout)
        self.assertEqual(record["id"], "deadbeef")
        record_file = self.state / "sessions" / self._local_id() / "record.json"
        stored = json.loads(record_file.read_text())
        self.assertEqual(stored["local_id"], self._local_id())
        self.assertEqual(stored["session_id"], None)
        context = Path(stored["context_file"])
        self.assertIn("## Objective", context.read_text())
        settings = json.loads(Path(stored["settings_file"]).read_text())
        self.assertEqual(settings["env"]["CCR_SESSION_ID"], stored["local_id"])
        self.assertEqual(
            settings["env"]["CCR_CONTEXT_FILE"], str(context)
        )

        checkpoint = self.ccr(
            "checkpoint",
            input="done: fixed\nverification: cargo test\n",
            env={"CCR_SESSION_ID": stored["local_id"], "CCR_CHILD": "1"},
        )
        self.assertEqual(checkpoint.returncode, 0, checkpoint.stderr)
        self.assertIn("verification: cargo test", context.read_text())

        sent = self.ccr("send", "deadbeef", "add a regression test", "--json")
        self.assertEqual(sent.returncode, 0, sent.stderr)
        self.assertIn("router instruction", context.read_text())

        summary = self.ccr("summary", "--json")
        self.assertEqual(summary.returncode, 0, summary.stderr)
        rows = json.loads(summary.stdout)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["profile"], "rust")

        doctor = self.ccr("doctor")
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)

    def _local_id(self):
        records = list((self.state / "sessions").glob("*/record.json"))
        self.assertEqual(len(records), 1)
        return records[0].parent.name

    def test_router_uses_agent_profile_and_fff_mcp(self):
        result = self.ccr("router", "--resume")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("--disable-slash-commands", result.stdout)
        self.assertIn("--agent ccr-router", result.stdout)
        self.assertNotIn("--strict-mcp-config", result.stdout)
        self.assertIn("--mcp-config", result.stdout)
        self.assertIn("--setting-sources", result.stdout)

    def test_orphan_plugin_fails_strict_refresh(self):
        inventory = self.root / "orphan.json"
        inventory.write_text(
            json.dumps([{"id": p} for p in plugin_ids()] + [{"id": "new@unknown"}])
        )
        result = subprocess.run(
            CCR + ["refresh", "--strict"],
            env={**self.env, "CCR_PLUGINS_JSON": str(inventory)},
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("new@unknown", result.stderr)

    def test_missing_profile_plugin_fails_strict_refresh(self):
        missing = "rust-review@trailofbits"
        inventory = self.root / "missing.json"
        inventory.write_text(
            json.dumps([{"id": p} for p in plugin_ids() if p != missing])
        )
        result = subprocess.run(
            CCR + ["refresh", "--strict"],
            env={**self.env, "CCR_PLUGINS_JSON": str(inventory)},
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(missing, result.stderr)


if __name__ == "__main__":
    unittest.main()
