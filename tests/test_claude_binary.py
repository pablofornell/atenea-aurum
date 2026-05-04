#!/usr/bin/env python3
"""
Test that the claude CLI binary is findable and callable.
Run: python tests/test_claude_binary.py
No MT4, no API credits consumed.
"""
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import config

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = PASS if ok else FAIL
    line = f"  [{status}] {label}"
    if detail:
        line += f"  —  {detail}"
    print(line)
    return ok


def main() -> None:
    print(f"\nClaude binary check  (config.CLAUDE_CLI = {config.CLAUDE_CLI!r})\n")
    all_ok = True

    # 1. Binary on PATH
    path = shutil.which(config.CLAUDE_CLI)
    all_ok &= check("Binary on PATH", path is not None, path or "not found")

    # 2. --version returns exit code 0
    if path:
        try:
            result = subprocess.run(
                [config.CLAUDE_CLI, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            version = (result.stdout + result.stderr).strip().splitlines()[0]
            all_ok &= check(
                "--version exits 0",
                result.returncode == 0,
                f"rc={result.returncode}  output={version!r}",
            )
        except subprocess.TimeoutExpired:
            all_ok &= check("--version exits 0", False, "timed out after 10s")
        except FileNotFoundError:
            all_ok &= check("--version exits 0", False, "FileNotFoundError")
    else:
        all_ok &= check("--version exits 0", False, "skipped — binary not found")

    # 3. -p with --output-format json returns parseable JSON (no API call — just checks flag support)
    if path:
        try:
            result = subprocess.run(
                [config.CLAUDE_CLI, "-p", "Reply with the single word: pong",
                 "--output-format", "json", "--dangerously-skip-permissions"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(Path(__file__).parent.parent / config.STRATEGY_DIR),
            )
            import json
            ok = False
            detail = f"rc={result.returncode}"
            if result.stdout.strip():
                try:
                    data = json.loads(result.stdout.strip())
                    ok = isinstance(data, dict)
                    detail += f"  keys={list(data.keys())}"
                except json.JSONDecodeError as exc:
                    detail += f"  json_error={exc}"
            else:
                detail += f"  stderr={result.stderr.strip()[:120]!r}"
            all_ok &= check("-p --output-format json returns JSON dict", ok, detail)
        except subprocess.TimeoutExpired:
            all_ok &= check("-p --output-format json returns JSON dict", False, "timed out after 60s")
        except FileNotFoundError:
            all_ok &= check("-p --output-format json returns JSON dict", False, "FileNotFoundError")
    else:
        all_ok &= check("-p --output-format json returns JSON dict", False, "skipped — binary not found")

    print()
    if all_ok:
        print("All checks passed.\n")
        sys.exit(0)
    else:
        print("One or more checks failed.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
