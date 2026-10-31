"""Check runnable documentation entrypoints and repository-local navigation."""

import re
import tomllib
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent


def anchors(text):
    result = set()
    counts = {}
    fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        if fenced or not re.match(r"^#{1,6} ", line):
            continue
        heading = re.sub(r"^#{1,6} +", "", line).strip().lower()
        slug = re.sub(r"[^\w\- ]", "", heading).replace(" ", "-")
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        result.add(slug + (f"-{count}" if count else ""))
    return result


class UserDocumentation(unittest.TestCase):
    def test_user_local_document_links_resolve(self):
        """Given a documentation link / When followed / Then its file and heading exist."""
        for name in ("README.md", "claude-plugins-setup.md"):
            document = ROOT / name
            for target in re.findall(r"\]\(([^\s)]+)\)", document.read_text()):
                if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                    continue
                path, _, anchor = unquote(target).partition("#")
                destination = document.parent / path if path else document
                with self.subTest(document=name, target=target):
                    self.assertTrue(destination.exists(), target)
                    if anchor:
                        self.assertTrue(destination.is_file(), target)
                        self.assertIn(anchor, anchors(destination.read_text()), target)

    def test_user_sees_runnable_image_usage_before_internal_details(self):
        """Given the README / When first opened / Then build and login precede internals."""
        text = (ROOT / "README.md").read_text()
        build = text.index("docker buildx build")
        login = text.index("ssh -p 8964")
        self.assertLess(build, login)
        self.assertLess(login, text.index("## 使用范围"))
        self.assertIn("claude-plugins-setup.md#5-登录与认证", text)

    def test_user_alias_instructions_match_the_image(self):
        """Given manual or image setup / When rm is configured / Then both use one reminder."""
        dockerfile = (ROOT / "build/Dockerfile").read_text()
        setup = (ROOT / "claude-plugins-setup.md").read_text()
        alias = dockerfile.split("<<'ALIASES'\n", 1)[1].split("\nALIASES", 1)[0]
        self.assertIn(alias, setup)
        self.assertIn("trash-put", alias)
        self.assertIn("false", alias)

    def test_manual_installs_every_required_waza_skill(self):
        """Given the manual / When Waza is installed / Then check, health and ui are present."""
        setup = (ROOT / "claude-plugins-setup.md").read_text()
        self.assertIn("tw93/Waza", setup)
        self.assertIn("for s in check health hunt learn read think ui write; do", setup)
        for skill in ("check", "health", "ui"):
            self.assertIn(f"`{skill}`", setup)

    def test_deleted_plugins_are_not_installed(self):
        """Given the image inventory / When a plugin is deleted / Then neither image nor docs re-add it."""
        dockerfile = (ROOT / "build/Dockerfile").read_text()
        inventory = (ROOT / "claude-plugins.tsv").read_text()
        setup = (ROOT / "claude-plugins-setup.md").read_text()
        deleted = (
            "feature-dev",
            "code-review",
            "pr-review-toolkit",
            "ralph-loop",
            "double-shot-latte",
            "session-report",
        )
        for plugin in deleted:
            self.assertNotIn(f"claude plugin install {plugin}", dockerfile)
            self.assertNotIn(f"{plugin}@", inventory)
            self.assertNotIn(f"claude plugin install {plugin}", setup)
        for plugin in ("hookify", "skill-creator", "redis-development"):
            self.assertIn(f"{plugin}@", inventory)

    def test_manual_tools_cover_every_post_edit_linter(self):
        """Given the manual mise config / When a file is edited / Then its linter is installed."""
        setup = (ROOT / "claude-plugins-setup.md").read_text()
        block = setup.split(
            "cat > ~/.config/mise/config.toml <<'EOF'\n", 1
        )[1].split("\nEOF", 1)[0]
        tools = tomllib.loads(block)["tools"]
        for tool in ("ruff", "npm:oxlint", "rust", "go"):
            self.assertIn(tool, tools, tool)

    def test_manual_plugin_totals_match_the_inventory(self):
        """Given the manual / When it states totals and the disabled set / Then both match the inventory."""
        setup = (ROOT / "claude-plugins-setup.md").read_text()
        rows = [
            line.split("\t")
            for line in (ROOT / "claude-plugins.tsv").read_text().splitlines()
            if line.strip()
        ]
        enabled = sum(1 for row in rows if row[3] == "true")
        disabled = [row[0].split("@")[0] for row in rows if row[3] == "false"]
        self.assertIn(
            f"{len(rows)} 个插件（{enabled} 启用、{len(disabled)} 禁用）", setup
        )
        ownership = setup.split("### 3.1 插件归属", 1)[1].split("## 4.", 1)[0]
        for name in disabled:
            self.assertIn(f"`{name}`", ownership, name)


if __name__ == "__main__":
    unittest.main()
