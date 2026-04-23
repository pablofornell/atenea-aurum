"""Bridge between AURUM and Claude Code CLI via subprocess."""
import json
import subprocess
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

REPO_DIR = Path(__file__).resolve().parents[2]


class ClaudeError(Exception):
    """Claude invocation or response parsing failed."""
    pass


def call_claude(
    prompt: str,
    screenshot_path: Optional[str] = None,
    session_history: Optional[List[Dict[str, Any]]] = None,
    system_prompt: Optional[str] = None
) -> dict:
    """Call Claude Code CLI with optional screenshot and session history.

    Args:
        prompt: Main analysis prompt to Claude
        screenshot_path: Path to MT4 screenshot (Claude will read it)
        session_history: Previous turns in this session (list of {role, content, ...})
        system_prompt: System instructions for Claude behavior

    Returns:
        Dict with keys:
        - 'ok' (bool): Success flag
        - 'action' (dict): Parsed action JSON from Claude (if ok=True)
        - 'raw' (str): Raw response from Claude (if ok=True)
        - 'error' (str): Error message (if ok=False)

    Raises:
        ClaudeError if subprocess fails or response cannot be parsed
    """

    # Build the full prompt with system instructions, history, and screenshot reference
    full_prompt = _build_prompt(
        system_prompt=system_prompt,
        screenshot_path=screenshot_path,
        session_history=session_history,
        analysis_prompt=prompt
    )

    logger.debug(f"Calling Claude CLI with {len(full_prompt)} chars of prompt")

    try:
        result = subprocess.run(
            ["claude", "--dangerously-skip-permissions", "--output-format", "json"],
            input=full_prompt,
            capture_output=True,
            text=True,
            encoding='utf-8',
            cwd=str(REPO_DIR),
            timeout=120,  # 120 second timeout
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            logger.error(f"Claude CLI failed: {error_msg}")
            return {
                "ok": False,
                "error": f"Claude CLI exit code {result.returncode}: {error_msg}"
            }

        # Parse Claude's JSON response (envelope format)
        try:
            response_json = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {result.stdout}")
            return {
                "ok": False,
                "error": f"Invalid JSON response from Claude: {e}"
            }

        # Extract the action from Claude's response
        # Claude's response format: {"type": "result", "result": "..."}
        if response_json.get("type") != "result":
            logger.warning(f"Unexpected Claude response type: {response_json.get('type')}")
            return {
                "ok": False,
                "error": f"Unexpected response type: {response_json.get('type')}"
            }

        raw_response = response_json.get("result", "")
        logger.debug(f"Raw Claude response: {raw_response[:200]}...")

        # Parse action JSON from Claude's text response
        try:
            action = _parse_action_json(raw_response)
            return {
                "ok": True,
                "action": action,
                "raw": raw_response
            }
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse action JSON from Claude response: {raw_response}")
            return {
                "ok": False,
                "error": f"Claude response is not valid JSON: {e}",
                "raw": raw_response
            }

    except subprocess.TimeoutExpired:
        logger.error("Claude CLI call timed out")
        return {
            "ok": False,
            "error": "Claude CLI call timed out after 60 seconds"
        }
    except Exception as e:
        logger.error(f"Unexpected error calling Claude: {e}")
        return {
            "ok": False,
            "error": f"Unexpected error: {e}"
        }


def _build_prompt(
    system_prompt: Optional[str],
    screenshot_path: Optional[str],
    session_history: Optional[List[Dict[str, Any]]],
    analysis_prompt: str
) -> str:
    """Build the full prompt to send to Claude CLI.

    Includes: system instructions, previous conversation history, screenshot reference, and analysis prompt.
    """
    parts = []

    # 1. System prompt
    if system_prompt:
        parts.append(system_prompt)
        parts.append("\n" + "="*80 + "\n")

    # 2. Session history (if any)
    if session_history:
        parts.append("## Previous Analysis in This Session\n")
        for i, turn in enumerate(session_history, 1):
            role = turn.get("role", "unknown")
            content = turn.get("content", "")
            screenshot = turn.get("screenshot_path", "")
            timeframe = turn.get("timeframe", "")

            parts.append(f"\n### Turn {i} ({role.upper()})")
            if timeframe:
                parts.append(f" — {timeframe}")
            parts.append("\n")

            if screenshot:
                parts.append(f"Screenshot: {screenshot}\n")
            if content:
                parts.append(f"{content}\n")

        parts.append("\n" + "="*80 + "\n")

    # 3. Current screenshot reference (Claude will read it)
    if screenshot_path:
        parts.append(f"## Current Chart Screenshot\n")
        parts.append(f"Location: {screenshot_path}\n")
        parts.append("Please analyze the chart above.\n\n")

    # 4. Main analysis prompt
    parts.append("## Your Task\n")
    parts.append(analysis_prompt)
    parts.append("\n")

    return "".join(parts)


def _parse_action_json(response: str) -> dict:
    """Extract and parse the JSON action from Claude's text response.

    Claude should respond with ONLY a JSON object, but sometimes there may
    be minimal preamble. Try to find valid JSON within the response.

    Args:
        response: Raw text response from Claude

    Returns:
        Parsed action dict

    Raises:
        json.JSONDecodeError if no valid JSON found
    """
    # Try direct parse first
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object within the response
    # Look for first '{' and match to closing '}'
    start = response.find("{")
    if start < 0:
        raise json.JSONDecodeError("No JSON object found in response", response, 0)

    # Find matching closing brace
    depth = 0
    end = -1
    for i in range(start, len(response)):
        if response[i] == "{":
            depth += 1
        elif response[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end < 0:
        raise json.JSONDecodeError("No matching closing brace found", response, start)

    json_str = response[start:end]
    return json.loads(json_str)
