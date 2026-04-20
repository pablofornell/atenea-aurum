"""Unit tests for the Claude bridge."""
from unittest.mock import MagicMock, patch

from src.bridge.claude_bridge import call_claude


def test_call_claude_returns_parsed_json():
    mock_result = MagicMock()
    mock_result.stdout = '{"result": "ok"}'
    with patch("src.bridge.claude_bridge.subprocess.run", return_value=mock_result):
        response = call_claude("test prompt")
    assert response == {"result": "ok"}
