import json
import os
import subprocess

import config

_WAIT_RESPONSE = {
    "decision":       "WAIT",
    "reasoning":      "parse_error",
    "entry_notes":    "",
    "sl":             0.0,
    "tp":             0.0,
    "confidence":     0.0,
    "ticket_to_close": None,
}

_OUTPUT_INSTRUCTION = """

---
Respond ONLY with a single valid JSON object. No markdown fences, no text outside the JSON.
Required structure:
{
  "decision": "BUY|SELL|CLOSE|HOLD|WAIT",
  "reasoning": "...",
  "entry_notes": "...",
  "sl": 0.00,
  "tp": 0.00,
  "confidence": 0.0,
  "ticket_to_close": null
}
"""


def call_agent(market_text: str, system_prompt: str, strategy_dir: str) -> dict:
    full_prompt = f"{system_prompt}\n\n{market_text}{_OUTPUT_INSTRUCTION}"

    try:
        result = subprocess.run(
            [config.CLAUDE_CLI, "--dangerously-skip-permissions", "--output-format", "json"],
            input=full_prompt,
            capture_output=True,
            text=True,
            cwd=os.path.abspath(strategy_dir),
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return {**_WAIT_RESPONSE, "reasoning": "agent_timeout"}
    except FileNotFoundError:
        return {**_WAIT_RESPONSE, "reasoning": "claude_cli_not_found"}

    raw = result.stdout.strip()

    # The claude CLI --output-format json wraps the response in a JSON envelope;
    # extract the "result" field which contains the agent text.
    try:
        envelope = json.loads(raw)
        agent_text = envelope.get("result", raw)
    except (json.JSONDecodeError, AttributeError):
        agent_text = raw

    # Strip optional markdown fence
    agent_text = agent_text.strip()
    if agent_text.startswith("```"):
        agent_text = agent_text.split("```")[1]
        if agent_text.startswith("json"):
            agent_text = agent_text[4:]
        agent_text = agent_text.strip()

    try:
        decision = json.loads(agent_text)
    except json.JSONDecodeError:
        return {**_WAIT_RESPONSE, "reasoning": f"json_parse_error: {agent_text[:200]}"}

    # Ensure all required keys are present
    for key, default in _WAIT_RESPONSE.items():
        decision.setdefault(key, default)

    return decision
