"""User registration behavior with a real Claude CLI and isolated configuration."""

import concurrent.futures
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ENTRYPOINT = Path(__file__).with_name("entrypoint.sh")


def executable(name):
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"Install {name} before this integration test")
    return path


# Resolve the real executable before temporary HOME hides mise's configuration.
CLAUDE = subprocess.check_output(["mise", "which", "claude"], text=True).strip()
FFF = executable("fff-mcp")


class UserRegistration(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ensure-fff-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.home = self.root / "home"
        self.home.mkdir()
        binary = self.home / ".local/bin/fff-mcp"
        binary.parent.mkdir(parents=True)
        binary.symlink_to(FFF)
        self.config_dir = self.root / "config"
        self.config_dir.mkdir()
        self.config = self.config_dir / ".claude.json"
        self.defaults = self.root / "mcp.json"
        self.defaults.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "fff": {
                            "type": "stdio",
                            "command": str(binary),
                        },
                        "second": {"type": "stdio", "command": "/bin/true"},
                    }
                }
            )
        )
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "CLAUDE_CONFIG_DIR": str(self.config_dir),
            "PATH": str(Path(CLAUDE).parent) + os.pathsep + os.environ["PATH"],
        }

    def run_helper(self):
        return subprocess.run(
            ["bash", str(ENTRYPOINT), "--init-mcp", str(self.defaults)],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def test_user_gets_registration_in_an_existing_home(self):
        """Given mounted home / When bootstrap runs / Then fff is user-scoped."""
        original = {
            "hasCompletedOnboarding": True,
            "mcpServers": {"other": {"type": "stdio", "command": "/bin/true"}},
            "projects": {"/project": {"disabledMcpServers": ["fff"]}},
        }
        self.config.write_text(json.dumps(original))
        self.config.chmod(0o600)
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = json.loads(self.config.read_text())
        server = actual["mcpServers"].pop("fff")
        self.assertEqual(actual["mcpServers"].pop("second")["command"], "/bin/true")
        for key, value in original.items():
            self.assertEqual(actual[key], value)
        self.assertEqual(server["command"], str(self.home / ".local/bin/fff-mcp"))
        self.assertEqual(server.get("args", []), [])
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)

    def test_user_custom_registration_is_not_replaced(self):
        """Given custom fff / When bootstrap repeats / Then bytes remain unchanged."""
        content = '{"mcpServers":{"fff":{"command":"/custom/fff","args":["--custom"]},"second":{"command":"/bin/true"}}}\n'
        self.config.write_text(content)
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.config.read_text(), content)

    def test_user_can_repeat_bootstrap(self):
        """Given a fresh configuration / When bootstrap repeats / Then it is inert."""
        first = self.run_helper()
        self.assertEqual(first.returncode, 0, first.stderr)
        content = self.config.read_bytes()
        second = self.run_helper()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.config.read_bytes(), content)

    def test_user_corrupt_configuration_is_not_overwritten(self):
        """Given corrupt JSON / When bootstrap runs / Then it fails without replacement."""
        for content in ("{broken", "[]", '{"mcpServers":[]}'):
            with self.subTest(content=content):
                self.config.write_text(content)
                result = self.run_helper()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.config.read_text(), content)
                self.assertIn("configuration", result.stderr)

    def test_user_can_disable_automatic_registration(self):
        """Given an explicit opt-out / When bootstrap runs / Then no config is created."""
        self.env["CLAUDE_DEV_SKIP_MCP"] = "fff second"
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.config.exists())

    def test_user_parallel_registrations_preserve_other_servers(self):
        """Given concurrent Claude writers / When bootstrap runs / Then no server is lost."""
        self.config.write_text('{"hasCompletedOnboarding":true}')

        def add_other(number):
            return subprocess.run(
                [
                    CLAUDE,
                    "mcp",
                    "add",
                    "--scope",
                    "user",
                    f"other-{number}",
                    "--",
                    "/bin/true",
                ],
                env=self.env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(add_other, n) for n in range(3)]
            futures.append(executor.submit(self.run_helper))
            for future in futures:
                result = future.result()
                self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(self.config.read_text())
        self.assertEqual(
            set(config["mcpServers"]),
            {"fff", "second", "other-0", "other-1", "other-2"},
        )
        self.assertTrue(config["hasCompletedOnboarding"])


if __name__ == "__main__":
    unittest.main()
