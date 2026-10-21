"""User-visible Entire installation without repository capture or login."""

import json
import os
import subprocess
import tempfile
from pathlib import Path


def main():
    env = {**os.environ, "ENTIRE_TELEMETRY_OPTOUT": "1"}
    with tempfile.TemporaryDirectory(prefix="entire-smoke-") as directory:
        root = Path(directory)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        before = set(root.iterdir())
        version = subprocess.check_output(
            ["entire", "version"], cwd=root, env=env, text=True
        )
        assert "Entire CLI" in version, version
        assert set(root.iterdir()) == before, "Version check enabled repository capture"
        assert not (root / ".claude").exists()
        assert not (root / ".entire").exists()
    plugins = json.loads(
        subprocess.check_output(["claude", "plugin", "list", "--json"], text=True)
    )
    plugin = next(item for item in plugins if item["id"] == "entire@entire-skills")
    assert plugin["enabled"], plugin
    path = Path(plugin["installPath"])
    assert (path / "skills/using-entire/SKILL.md").is_file(), path
    assert (path / "skills/search/SKILL.md").is_file(), path
    assert (path / "skills/review/SKILL.md").is_file(), path
    print(
        "Entire smoke: CLI and official plugin work without enabling repository capture"
    )


if __name__ == "__main__":
    main()
