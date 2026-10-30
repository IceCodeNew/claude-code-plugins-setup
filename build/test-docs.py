"""Check runnable documentation entrypoints and repository-local navigation."""

import re
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

    def test_deleted_plugins_are_not_installed(self):
        """Given the image inventory / When a plugin is deleted / Then neither image nor docs re-add it."""
        dockerfile = (ROOT / "build/Dockerfile").read_text()
        inventory = (ROOT / "claude-plugins.tsv").read_text()
        setup = (ROOT / "claude-plugins-setup.md").read_text()
        deleted = (
            "feature-dev",
            "code-review",
            "pr-review-toolkit",
            "hookify",
            "skill-creator",
            "ralph-loop",
            "double-shot-latte",
            "redis-development",
        )
        for plugin in deleted:
            self.assertNotIn(f"claude plugin install {plugin}", dockerfile)
            self.assertNotIn(f"{plugin}@", inventory)
            self.assertNotIn(f"claude plugin install {plugin}", setup)


if __name__ == "__main__":
    unittest.main()
