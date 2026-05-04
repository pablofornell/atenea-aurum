import json
import os
import subprocess

import config

_WAIT_RESPONSE = {
    "decision":            "WAIT",
    "reasoning":           "parse_error",
    "entry_notes":         "",
    "sl":                  0.0,
    "tp":                  0.0,
    "confidence":          0.0,
    "ticket_to_close":     None,
    "next_check_minutes":  None,
    "_bot_managed_state":  None,
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
  "ticket_to_close": null,
  "next_check_minutes": null,
  "bot_managed_state": {
    "h4_bias": "bullish|bearish|ranging|unclear",
    "h4_bias_since": "ISO-8601 or null",
    "h4_bias_justification": "string",
    "h1_bias": "bullish|bearish|ranging|unclear",
    "h1_bias_justification": "string",
    "pending_setup": {
      "active": false,
      "type": null,
      "context": "",
      "target_poi_id": null,
      "target_liquidity_price": null,
      "expected_direction": null,
      "since": null,
      "invalidate_above": null,
      "invalidate_below": null,
      "invalidate_after": null
    },
    "narrative": "string"
  }
}
"""


def call_agent(market_text: str, system_prompt: str, strategy_dir: str) -> dict:
    full_prompt = f"{system_prompt}\n\n{market_text}{_OUTPUT_INSTRUCTION}"

    env = os.environ.copy()
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"

    try:
        result = subprocess.run(
            [config.CLAUDE_CLI, "-p", full_prompt,
             "--dangerously-skip-permissions", "--output-format", "json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=os.path.abspath(strategy_dir),
            env=env,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return {**_WAIT_RESPONSE, "reasoning": "agent_timeout"}
    except FileNotFoundError:
        return {**_WAIT_RESPONSE, "reasoning": "claude_cli_not_found"}

    returncode = result.returncode
    raw        = result.stdout.strip()
    stderr     = result.stderr.strip()

    def _fail(reason: str) -> dict:
        return {
            **_WAIT_RESPONSE,
            "reasoning": reason,
            "_debug": {
                "returncode": returncode,
                "stderr":     stderr[:500],
                "raw_stdout": raw[:500],
            },
        }

    if not raw:
        return _fail(f"empty_stdout rc={returncode} stderr={stderr[:200]!r}")

    envelope   = None
    agent_text = raw
    try:
        envelope   = json.loads(raw)
        agent_text = envelope.get("result") or ""
        if not agent_text:
            is_err = envelope.get("is_error", False)
            return _fail(f"empty_result in envelope is_error={is_err} keys={list(envelope.keys())}")
    except json.JSONDecodeError:
        agent_text = raw

    agent_text = agent_text.strip()
    if agent_text.startswith("```"):
        agent_text = agent_text.split("```")[1]
        if agent_text.startswith("json"):
            agent_text = agent_text[4:]
        agent_text = agent_text.strip()

    try:
        decision = json.loads(agent_text)
    except json.JSONDecodeError as exc:
        return _fail(f"json_parse_error: {exc} | text={agent_text[:300]!r}")

    # Extract bot_managed_state before filling defaults
    bot_managed = decision.pop("bot_managed_state", None)

    for key, default in _WAIT_RESPONSE.items():
        if key != "_debug":
            decision.setdefault(key, default)

    # Store bot_managed_state under internal key for orchestrator to consume
    decision["_bot_managed_state"] = bot_managed

    return decision
