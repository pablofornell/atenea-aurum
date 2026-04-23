"""Unit tests for the Claude bridge."""
import json
from unittest.mock import MagicMock, patch

from src.bridge.claude_bridge import call_claude


def test_call_claude_returns_parsed_action():
    action = {"action": "DONE", "reasoning": "no setup"}
    envelope = json.dumps({"type": "result", "result": json.dumps(action)})
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = envelope
    with patch("src.bridge.claude_bridge.subprocess.run", return_value=mock_result):
        response = call_claude("test prompt")
    assert response["ok"] is True
    assert response["action"] == action


def test_call_claude_handles_timeout():
    import subprocess
    with patch("src.bridge.claude_bridge.subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 120)):
        response = call_claude("test prompt")
    assert response["ok"] is False
    assert "timed out" in response["error"]


def test_call_claude_handles_nonzero_exit():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "permission denied"
    mock_result.stdout = ""
    with patch("src.bridge.claude_bridge.subprocess.run", return_value=mock_result):
        response = call_claude("test prompt")
    assert response["ok"] is False
