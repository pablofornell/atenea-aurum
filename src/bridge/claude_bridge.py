"""Bridge between AURUM and Claude Code CLI via subprocess."""
import json
import subprocess
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]


def call_claude(prompt: str) -> dict:
    result = subprocess.run(
        ["claude", "--dangerously-skip-permissions", "--output-format", "json"],
        input=prompt,
        capture_output=True,
        text=True,
        cwd=REPO_DIR,
    )
    return json.loads(result.stdout)
