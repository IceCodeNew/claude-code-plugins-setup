"""Exercise the installed user-scope fff server in isolated Git repositories."""

import json
import os
import select
import subprocess
import tempfile
import time
from pathlib import Path


class Client:
    def __init__(self, process):
        self.process = process
        self.buffer = bytearray()

    def send(self, message):
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        self.process.stdin.flush()

    def request(self, request_id, method, params):
        self.send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        deadline = time.monotonic() + 30
        while True:
            while b"\n" in self.buffer:
                line, _, rest = self.buffer.partition(b"\n")
                self.buffer = bytearray(rest)
                response = json.loads(line)
                if response.get("id") == request_id:
                    if "error" in response:
                        raise RuntimeError(response["error"])
                    return response["result"]
            remaining = deadline - time.monotonic()
            if (
                remaining <= 0
                or not select.select([self.process.stdout], [], [], remaining)[0]
            ):
                raise TimeoutError(f"fff did not answer {method}")
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError(f"fff exited during {method}")
            self.buffer.extend(chunk)


def check_repository(server, root, marker, other_marker, from_subdirectory):
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    filename = "fixture.txt"
    (root / filename).write_text(marker + "\n")
    subdirectory = root / "src"
    subdirectory.mkdir()
    with subprocess.Popen(
        [server["command"], *server.get("args", [])],
        cwd=subdirectory if from_subdirectory else root,
        env={**os.environ, **server.get("env", {})},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    ) as process:
        try:
            client = Client(process)
            client.request(
                1,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "fff-smoke", "version": "1"},
                },
            )
            client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            cases = [
                ("find_files", {"query": filename, "maxResults": 20}),
                ("grep", {"query": marker, "maxResults": 20}),
                (
                    "multi_grep",
                    {
                        "patterns": [marker, other_marker],
                        "constraints": "*.txt",
                        "maxResults": 20,
                    },
                ),
            ]
            for request_id, (tool, arguments) in enumerate(cases, start=2):
                result = client.request(
                    request_id, "tools/call", {"name": tool, "arguments": arguments}
                )
                assert not result.get("isError"), result
                text = "\n".join(c.get("text", "") for c in result["content"])
                assert filename in text, (tool, text)
                assert other_marker not in text, (tool, text)
                if tool != "find_files":
                    assert marker in text, (tool, text)
            missing = client.request(
                5,
                "tools/call",
                {
                    "name": "grep",
                    "arguments": {"query": other_marker, "maxResults": 20},
                },
            )
            assert not missing.get("isError"), missing
            text = "\n".join(c.get("text", "") for c in missing["content"])
            assert filename not in text, text
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    config_directory = os.environ.get("CLAUDE_CONFIG_DIR")
    config_path = (
        Path(config_directory) / ".claude.json"
        if config_directory
        else Path.home() / ".claude.json"
    )
    server = json.loads(config_path.read_text())["mcpServers"]["fff"]
    with tempfile.TemporaryDirectory(prefix="fff-smoke-") as directory:
        root = Path(directory)
        cases = [
            ("fff_alpha_marker", "fff_beta_marker", False),
            ("fff_beta_marker", "fff_alpha_marker", True),
        ]
        for number, (marker, other, from_subdirectory) in enumerate(cases):
            check_repository(
                server, root / f"repo-{number}", marker, other, from_subdirectory
            )
    print(
        "fff smoke: file/content searches stay within each Git root, including subdirectory startup"
    )


if __name__ == "__main__":
    main()
