"""User safety policies at the hook's JSON stdin/stdout boundary."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PYTHON = os.environ.get("CLAUDE_HOOK_PYTHON", "/usr/bin/python3.13")
HOOKS = Path(os.environ.get("CLAUDE_HOOKS_DIR", Path(__file__).with_name("hooks")))


class UserSafety(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="safety-hook-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/owner/repo.git"],
            cwd=self.root,
            check=True,
        )
        self.env = {
            **os.environ,
            "HOME": str(self.root),
            "XDG_STATE_HOME": str(self.root / "state"),
            "CLAUDE_HOOK_PYTHON": PYTHON,
        }
        # A protocol fixture: only the read-only gh operations used by the policy exist.
        binary = self.root / "bin"
        binary.mkdir()
        gh = binary / "gh"
        gh.write_text("""#!/usr/bin/python3 -I
import json,sys,os
args=sys.argv[1:]
if os.environ.get("GH_FIXTURE_FAIL"): sys.exit(1)
if args[:2]==["repo","view"]:
 print(json.dumps({"nameWithOwner":"owner/repo","url":"https://github.com/owner/repo"}))
elif args[:1]==["api"] and "pulls/" in args[-1]:
 endpoint=args[-1].split("/"); number=int(endpoint[-1]); repo="/".join(endpoint[1:3])
 print(json.dumps({"number":number,"base":{"ref":({9:"feature/integration",8:"prod",7:"custom-protected"}.get(number,"trunk")),"repo":{"full_name":repo,"default_branch":"trunk"}}}))
elif args[:1]==["api"] and any("branches?protected=true" in arg for arg in args):
 print(json.dumps([[{"name":os.environ.get("GH_FIXTURE_PROTECTED", "custom-protected"),"protected":True}]]))
elif args[:1]==["api"] and args[-1].startswith("repos/"):
 print(json.dumps({"full_name":args[-1][6:],"default_branch":os.environ.get("GH_FIXTURE_DEFAULT", "feature" if args[-1].endswith("other/repo") else "trunk")}))
else: sys.exit("Unsupported fixture operation: "+repr(args))
""")
        gh.chmod(0o755)
        self.env["PATH"] = str(binary) + os.pathsep + os.environ["PATH"]

    def invoke(self, policy, command="true", mode="bypassPermissions", **values):
        payload = {
            "hook_event_name": "PreToolUse",
            "session_id": "session-one",
            "cwd": str(self.root),
            "permission_mode": mode,
            "tool_name": "Bash",
            "tool_input": {"command": command},
            **values,
        }
        modules = {
            "pre": [
                "block_rm",
                "require_tmux",
                "protected_branches",
            ],
            "merge": ["protected_branches"],
            "record": ["protected_branches"],
            "post": ["post_edit_check"],
        }[policy]
        for module in modules:
            result = subprocess.run(
                [PYTHON, "-E", "-s", str(HOOKS / (module.replace("_", "-") + ".py"))],
                input=json.dumps(payload),
                env=self.env,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            response = json.loads(result.stdout)
            if self.denied(response) or response:
                return response
        return {}

    def denied(self, result):
        return result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"

    def prompt(self, text, **values):
        return self.invoke(
            "record", hook_event_name="UserPromptSubmit", prompt=text, **values
        )

    def test_user_can_call_independent_hooks_from_another_harness(self):
        """Given JSON on stdin / When calling the Python hook / Then no package installation is needed."""
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "rm -- owned-file"},
            "permission_mode": "default",
            "cwd": str(self.root),
            "session_id": "portable-hook",
        }
        script = HOOKS / "block-rm.py"
        result = subprocess.run(
            [PYTHON, "-E", "-s", str(script)],
            input=json.dumps(payload),
            cwd=self.root,
            env={**self.env, "CLAUDE_HOOK_PYTHON": PYTHON},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.denied(json.loads(result.stdout)))

    def test_user_interactive_rm_reminds_instead_of_deleting(self):
        """Given the configured interactive alias / When rm is typed / Then the file stays recoverable."""
        file = self.root / "alias-owned-file"
        file.write_text("keep this file")
        bashrc = os.environ.get("CLAUDE_DEV_BASHRC")
        if bashrc is None:
            dockerfile = Path(__file__).with_name("Dockerfile").read_text()
            alias = dockerfile.split("<<'ALIASES'\n", 1)[1].split("\nALIASES", 1)[0]
            fixture = self.root / "bashrc"
            fixture.write_text(alias + "\n")
            bashrc = str(fixture)
        result = subprocess.run(
            [
                "bash",
                "--noprofile",
                "--rcfile",
                bashrc,
                "-ic",
                'rm -- "$1"',
                "--",
                str(file),
            ],
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("trash-put", result.stdout + result.stderr)
        self.assertTrue(file.exists())

    def test_user_cannot_execute_rm_in_any_mode(self):
        """Given any mode / When rm executes / Then trash-cli is required."""
        commands = [
            "rm -rf work",
            "/bin/rm -- work",
            "command rm f",
            "env X=1 rm f",
            "env -S 'rm f'",
            "find . -exec env rm {} +",
            "sudo -u root rm f",
            "sudo -n rm f",
            "command -p rm f",
            'find . -exec sh -c "rm f" \\;',
            "true && rm f",
            "echo $(rm f)",
            "bash -lc 'rm f'",
            "find . -exec rm {} +",
            "printf x | xargs rm",
            "r\\m f",
            "'r''m' f",
        ]
        for mode in [
            "default",
            "plan",
            "auto",
            "acceptEdits",
            "dontAsk",
            "bypassPermissions",
        ]:
            for command in commands:
                with self.subTest(mode=mode, command=command):
                    result = self.invoke("pre", command, mode)
                    self.assertTrue(self.denied(result), result)
                    self.assertIn("trash-put", json.dumps(result))

    def test_user_can_mention_rm_and_use_trash(self):
        """Given literal text / When no rm executes / Then normal work continues."""
        for command in [
            "echo 'rm -rf work'",
            "echo \"<<'EOF'\"",
            "printf '%s' 'gh pr merge 12'",
            "git status",
            "trash-put -- work",
            "cat <<'EOF'\nrm example\nEOF",
        ]:
            with self.subTest(command=command):
                self.assertFalse(self.denied(self.invoke("pre", command)))

    def test_user_docker_cleanup_does_not_trigger_shell_rm_guard(self):
        """Given the historical Docker false positive / When checked / Then Docker stays usable."""
        # The uploaded block-rm-rf.sh records this exact regression command.
        historical = 'docker run --rm -v "$(pwd)/UserDimension:/usr/app/xxx" xxx-user-dimension:local deps --profiles-dir /tmp 2>&1'
        commands = [
            historical,
            "docker rm stopped-container",
            "docker container rm -f stopped-container",
            "docker run --rm -v /tmp/fixture:/workspace alpine echo ok",
        ]
        for mode in ("default", "bypassPermissions"):
            for command in commands:
                with self.subTest(mode=mode, command=command):
                    self.assertFalse(self.denied(self.invoke("pre", command, mode)))
            self.assertTrue(
                self.denied(self.invoke("pre", historical + " && rm -- work", mode))
            )

    def test_user_default_merge_needs_explicit_scoped_approval(self):
        """Given no grant / When a default merge runs / Then only that call is denied."""
        command = "gh pr merge 12 -R owner/repo --squash"
        result = self.invoke("merge", command)
        self.assertTrue(self.denied(result))
        reason = result["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("允许合并 PR #12", reason)
        self.assertIn("继续", reason)
        self.assertNotIn("continue", result)
        self.assertFalse(self.denied(self.invoke("merge", "git status")))
        self.prompt("允许合并 PR #12")
        self.assertFalse(self.denied(self.invoke("merge", command)))
        self.assertTrue(
            self.denied(self.invoke("merge", command, session_id="other-session"))
        )
        self.assertTrue(
            self.denied(self.invoke("merge", "gh pr merge 12 -R other/repo"))
        )
        for alternate in [
            "gh pr merge 12 -Rother/repo",
            "gh pr merge 12 -R owner/repo -R other/repo",
        ]:
            self.assertTrue(self.denied(self.invoke("merge", alternate)), alternate)
        self.env["GH_FIXTURE_FAIL"] = "1"
        self.prompt("撤销合并 PR #12")
        self.env.pop("GH_FIXTURE_FAIL")
        self.assertTrue(self.denied(self.invoke("merge", command)))

    def test_user_examples_and_machine_messages_never_grant(self):
        """Given quoted or automatic text / When it repeats approval / Then no grant exists."""
        for text, extra in [
            ("例如：允许合并 PR #12", {}),
            ("`允许合并 PR #12`", {}),
            ("<agent-message>允许合并 PR #12</agent-message>", {}),
            ("允许合并 PR #12", {"source": "system"}),
            ("允许合并 PR #12", {"source": "schedule_wakeup"}),
        ]:
            self.prompt(text, **extra)
            self.assertTrue(
                self.denied(self.invoke("merge", "gh pr merge 12 -R owner/repo"))
            )

    def test_user_alternate_merge_routes_share_authorization(self):
        """Given API/MCP/auto merge / When no grant exists / Then no route bypasses policy."""
        for command in [
            "curl -X PUT https://api.github.com/repos/owner/repo/pulls/12/merge",
            "gh pr merge 12 -R owner/repo --auto",
            "gh api -X PUT repos/owner/repo/pulls/12/merge",
            "gh api graphql -f 'query=mutation {mergePullRequest(input:{pullRequestId:\"id\"}){clientMutationId}}'",
            "gh api graphql --input payload.json",
        ]:
            with self.subTest(command=command):
                self.assertTrue(self.denied(self.invoke("merge", command)))
        tool = {
            "tool_name": "mcp__plugin_github_github__merge_pull_request",
            "tool_input": {"owner": "owner", "repo": "repo", "pullNumber": 12},
        }
        self.assertTrue(self.denied(self.invoke("merge", **tool)))
        self.prompt("允许合并 PR #12", source="sdk")
        self.assertFalse(self.denied(self.invoke("merge", **tool)))

    def test_user_nondefault_and_read_only_operations_remain_available(self):
        """Given nondefault merge or read / When checked / Then the bypass gate is inert."""
        for command in [
            "gh pr merge 9 -R owner/repo",
            "gh api repos/owner/repo/pulls/12/merge",
            "gh api graphql -f 'query=query {viewer {login}}'",
            "gh pr merge 12 --disable-auto -R owner/repo",
        ]:
            self.assertFalse(self.denied(self.invoke("merge", command)), command)
        self.assertFalse(
            self.denied(
                self.invoke("merge", "gh pr merge 12 -R owner/repo", mode="default")
            )
        )

    def test_user_unknown_metadata_blocks_merge_only(self):
        """Given failed metadata / When merging / Then deny merge but allow unrelated work."""
        self.env["GH_FIXTURE_FAIL"] = "1"
        self.assertTrue(
            self.denied(self.invoke("merge", "gh pr merge 12 -R owner/repo"))
        )
        self.assertFalse(self.denied(self.invoke("merge", "git status")))

    def test_user_installs_guards_without_replacing_existing_hooks(self):
        """Given custom settings / When installed twice / Then policies merge once."""
        config = self.root / ".claude"
        config.mkdir()
        path = config / "settings.json"
        existing = {
            "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "true"}]}]},
            "enabledPlugins": {"custom@market": False},
        }
        mixed = {"type": "command", "command": "printf unrelated"}
        existing["hooks"]["PreToolUse"] = [
            {
                "matcher": "Bash",
                "hooks": [
                    mixed,
                    {
                        "type": "command",
                        "command": PYTHON,
                        "args": ["-E", "-s", str(HOOKS / "block-rm.py")],
                    },
                ],
            }
        ]
        unrelated = {
            "type": "command",
            "command": PYTHON,
            "args": ["-I", "/home/nonroot/.claude/hooks/safety-hook.py"],
        }
        existing["hooks"]["PreToolUse"][0]["hooks"].append(unrelated)
        path.write_text(json.dumps(existing))
        for _ in range(2):
            subprocess.run(
                [PYTHON, "-E", "-s", str(HOOKS / "configure-claude.py")],
                env=self.env,
                check=True,
            )
        data = json.loads(path.read_text())
        self.assertEqual(data["hooks"]["Stop"], existing["hooks"]["Stop"])
        self.assertEqual(data["enabledPlugins"], existing["enabledPlugins"])
        self.assertIn(mixed, data["hooks"]["PreToolUse"][0]["hooks"])
        self.assertIn(unrelated, data["hooks"]["PreToolUse"][0]["hooks"])
        self.assertEqual(len(data["hooks"]["PreToolUse"]), 4)
        self.assertEqual(len(data["hooks"]["UserPromptSubmit"]), 1)
        for event in ("PreToolUse", "UserPromptSubmit"):
            for group in data["hooks"][event]:
                for hook in group["hooks"]:
                    if hook.get("args", [""])[-1].startswith(str(HOOKS) + "/"):
                        self.assertEqual(hook["onFailure"], "block")

    def test_user_opaque_merge_forms_fail_closed(self):
        """Given alternate API syntax / When merging / Then ambiguous targets are denied."""
        for command in [
            "gh --repo owner/repo pr merge 12",
            "gh api --method=PUT https://api.github.com/repos/owner/repo/pulls/12/merge",
            "gh api -XPUT repos/owner/repo/pulls/12/merge",
            "gh api -X GET -X PUT repos/owner/repo/pulls/12/merge",
            "gh api graphql -fquery=@payload.graphql",
            "GH_REPO=other/repo gh pr merge 12",
        ]:
            self.assertTrue(self.denied(self.invoke("merge", command)), command)

    def test_user_trash_alternative_preserves_recoverable_content(self):
        """Given an owned file / When trash-put runs / Then content remains recoverable."""
        item = self.root / "owned-file"
        item.write_text("recoverable marker")
        env = {**self.env, "XDG_DATA_HOME": str(self.root / "data")}
        subprocess.run(["trash-put", "--", str(item)], env=env, check=True)
        self.assertFalse(item.exists())
        saved = list((self.root / "data/Trash/files").iterdir())
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_text(), "recoverable marker")

    def test_user_pushes_use_prs_without_force(self):
        """Given a push / When it targets protected refs or forces / Then it is denied."""
        for command in [
            "git push origin main",
            "git push origin HEAD:refs/heads/master",
            "git push --tags origin main",
            "git push origin",
            "git push --all origin",
            'branch=main; git push origin "$branch"',
            'git push origin "$(printf main)"',
            'git push origin "`printf main`"',
        ]:
            self.assertTrue(self.denied(self.invoke("pre", command)), command)
        subprocess.run(
            ["git", "symbolic-ref", "HEAD", "refs/heads/feature"],
            cwd=self.root,
            check=True,
        )
        self.assertTrue(self.denied(self.invoke("pre", "git push --branches origin")))
        self.assertTrue(self.denied(self.invoke("pre", "git push origin")))
        self.assertTrue(
            self.denied(
                self.invoke("pre", "cd another-repo && git push origin feature")
            )
        )
        for command in [
            "git push -u origin feature",
            "git push -f origin feature",
            "git push --force-with-lease origin feature",
            "git push origin HEAD:refs/heads/new-feature",
            "echo 'git push origin main'",
            "git status",
        ]:
            self.assertFalse(self.denied(self.invoke("pre", command)), command)

    def test_user_configured_push_mapping_cannot_hide_protected_destination(self):
        """Given a source-only ref mapped to main / When pushed / Then require an explicit destination."""
        subprocess.run(
            [
                "git",
                "config",
                "remote.origin.push",
                "refs/heads/feature:refs/heads/main",
            ],
            cwd=self.root,
            check=True,
        )
        self.assertTrue(self.denied(self.invoke("pre", "git push origin feature")))
        self.assertFalse(
            self.denied(
                self.invoke("pre", "git push origin feature:refs/heads/feature")
            )
        )

    def test_user_push_and_merge_share_target_branch_protection(self):
        """Given default, common, or GitHub-protected refs / When written / Then use an authorized PR."""
        for branch in (
            "trunk",
            "main",
            "master",
            "prod",
            "production",
            "release/2026",
            "stable/1",
            "custom-protected",
        ):
            with self.subTest(branch=branch):
                self.assertTrue(
                    self.denied(
                        self.invoke("pre", f"git push origin HEAD:refs/heads/{branch}")
                    )
                )
        for number in (7, 8):
            command = f"gh pr merge {number} -R owner/repo"
            self.assertTrue(self.denied(self.invoke("merge", command)), command)
            self.prompt(f"允许合并 PR #{number}")
            self.assertFalse(self.denied(self.invoke("merge", command)), command)
        self.assertFalse(
            self.denied(self.invoke("pre", "git push --force origin feature"))
        )

    def test_user_development_and_staging_names_are_not_protected_by_default(self):
        """Given an ordinary dev or staging branch / When pushed / Then the name alone does not block it."""
        for branch in ("dev", "dev/work", "develop", "development", "staging"):
            with self.subTest(branch=branch):
                self.assertFalse(
                    self.denied(
                        self.invoke("pre", f"git push origin HEAD:refs/heads/{branch}")
                    )
                )
        self.env["GH_FIXTURE_DEFAULT"] = "staging"
        self.assertTrue(
            self.denied(self.invoke("pre", "git push origin HEAD:refs/heads/staging"))
        )
        self.env.pop("GH_FIXTURE_DEFAULT")
        self.env["GH_FIXTURE_PROTECTED"] = "develop"
        self.assertTrue(
            self.denied(self.invoke("pre", "git push origin HEAD:refs/heads/develop"))
        )

    def test_user_every_remote_push_destination_is_protected(self):
        """Given two push URLs / When one protects the target / Then no push is allowed."""
        subprocess.run(
            [
                "git",
                "remote",
                "set-url",
                "--add",
                "--push",
                "origin",
                "https://github.com/owner/repo.git",
            ],
            cwd=self.root,
            check=True,
        )
        subprocess.run(
            [
                "git",
                "remote",
                "set-url",
                "--add",
                "--push",
                "origin",
                "https://github.com/other/repo.git",
            ],
            cwd=self.root,
            check=True,
        )
        self.assertTrue(self.denied(self.invoke("pre", "git push origin feature")))

    def test_user_dev_servers_need_tmux(self):
        """Given a dev server / When outside tmux / Then require a tmux launch."""
        self.env.pop("TMUX", None)
        for command in [
            "npm run dev",
            "pnpm dev",
            "next dev",
            "uvicorn app:app",
            "fastapi run app.py",
            "npx serve .",
            "bunx serve .",
        ]:
            self.assertTrue(self.denied(self.invoke("pre", command)), command)
        for command in [
            "echo 'npm run dev'",
            "npm test",
            "vite build",
            "uvicorn --help",
            "tmux new-session -d -s dev 'npm run dev'",
        ]:
            self.assertFalse(self.denied(self.invoke("pre", command)), command)
        self.env["TMUX"] = "/tmp/tmux-fixture,1,0"
        self.assertFalse(self.denied(self.invoke("pre", "npm run dev")))

    def test_user_edit_diagnostics_preserve_status_and_complete_output(self):
        """Given a Python edit / When lint fails / Then complete diagnostics reach the agent."""
        file = self.root / "edited file.py"
        file.write_text("import os\n")
        result = self.invoke(
            "post",
            hook_event_name="PostToolUse",
            tool_name="Edit",
            tool_input={"file_path": str(file)},
        )
        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("exit 1", context)
        self.assertIn("F401", context)
        self.assertIn("edited file.py", context)
        file.write_text("print('valid')\n")
        self.assertEqual(
            self.invoke(
                "post",
                hook_event_name="PostToolUse",
                tool_name="Write",
                tool_input={"file_path": str(file)},
            ),
            {},
        )
        self.assertEqual(
            self.invoke(
                "post",
                hook_event_name="PostToolUse",
                tool_name="Edit",
                tool_input={"file_path": str(self.root / "file.txt")},
            ),
            {},
        )

    def test_user_previous_registration_is_replaced_by_independent_script(self):
        """Given the previous managed registration / When configured / Then disabled hooks do not survive migration."""
        directory = self.root / "config"
        directory.mkdir()
        path = directory / "settings.json"
        unrelated = {"type": "command", "command": "printf unrelated"}
        path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "Bash",
                                "hooks": [
                                    unrelated,
                                    {
                                        "type": "command",
                                        "command": "sh",
                                        "args": [str(HOOKS / "post-edit-check.sh")],
                                    },
                                ],
                            }
                        ]
                    }
                }
            )
        )
        subprocess.run(
            [
                PYTHON,
                "-E",
                "-s",
                str(HOOKS / "configure-claude.py"),
                "--disable",
                "post-edit-check",
            ],
            env={**self.env, "CLAUDE_CONFIG_DIR": str(directory)},
            check=True,
        )
        hooks = [
            hook
            for groups in json.loads(path.read_text())["hooks"].values()
            for group in groups
            for hook in group["hooks"]
        ]
        self.assertIn(unrelated, hooks)
        self.assertFalse(
            any(
                str(HOOKS / "post-edit-check.sh") in hook.get("args", [])
                for hook in hooks
            )
        )
        self.assertFalse(
            any(
                str(HOOKS / "post-edit-check.py") in hook.get("args", [])
                for hook in hooks
            )
        )

    def test_user_hook_checkout_path_is_not_shell_syntax(self):
        """Given a copied checkout with spaces and punctuation / When registered / Then the exact script runs."""
        import shutil

        directory = self.root / "copied hooks;literal"
        shutil.copytree(HOOKS, directory)
        config = self.root / "copy-config"
        env = {**self.env, "CLAUDE_CONFIG_DIR": str(config)}
        subprocess.run(
            [PYTHON, "-E", "-s", str(directory / "configure-claude.py")],
            env=env,
            check=True,
        )
        data = json.loads((config / "settings.json").read_text())
        hook = next(
            hook
            for group in data["hooks"]["PreToolUse"]
            for hook in group["hooks"]
            if str(directory / "block-rm.py") in hook.get("args", [])
        )
        payload = {"tool_name": "Bash", "tool_input": {"command": "rm file"}}
        result = subprocess.run(
            [hook["command"], *hook["args"]],
            input=json.dumps(payload),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.denied(json.loads(result.stdout)))

    def test_user_can_disable_one_role_without_disabling_other_guards(self):
        """Given independent hooks / When a role is disabled / Then other roles stay enabled."""
        env = {**self.env, "CLAUDE_CONFIG_DIR": str(self.root / "config")}
        command = [PYTHON, "-E", "-s", str(HOOKS / "configure-claude.py")]
        result = subprocess.run(
            [*command, "--disable", "require-tmux", "post-edit-check"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        path = Path(env["CLAUDE_CONFIG_DIR"]) / "settings.json"
        disabled = path.read_bytes()
        subprocess.run(command, env=env, check=True)
        self.assertEqual(path.read_bytes(), disabled)
        groups = json.loads(path.read_text())["hooks"]["PreToolUse"]
        scripts = {Path(group["hooks"][0]["args"][-1]).name for group in groups}
        self.assertEqual(scripts, {"block-rm.py", "protected-branches.py"})
        subprocess.run([*command, "--enable", "require-tmux"], env=env, check=True)
        groups = json.loads(path.read_text())["hooks"]["PreToolUse"]
        scripts = {Path(group["hooks"][0]["args"][-1]).name for group in groups}
        self.assertIn("require-tmux.py", scripts)
        self.assertNotIn("post-edit-check.py", scripts)


if __name__ == "__main__":
    unittest.main()
