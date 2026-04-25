"""Macro context provider: fetches gold-relevant news via Perplexity MCP through Claude CLI."""
import json
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

FALLBACK_MACRO = """MACRO_CONTEXT (static fallback — no live data available):
• Gold (XAUUSD) inversely correlated with USD strength (DXY)
• Hawkish Fed = bearish gold; dovish Fed / rate cuts = bullish gold
• Risk-off events (geopolitical tension, recession fears) = bullish gold
• DXY above 104: headwind for gold. DXY below 100: tailwind for gold
• Real yields negative = bullish gold; rising real yields = bearish gold"""

_CACHE_TTL_HOURS = 4


class MacroContextProvider:
    def __init__(self, claude_cli_path: str = "claude", strategy_dir: str = None):
        self._cli = claude_cli_path
        self._strategy_dir = strategy_dir
        self._cache: Optional[str] = None
        self._cache_ts: Optional[datetime] = None

    def fetch(self) -> str:
        if self._cache and not self.is_stale():
            return self._cache

        try:
            result = self._fetch_from_perplexity()
            self._cache = result
            self._cache_ts = datetime.utcnow()
            return self._cache
        except Exception as e:
            logger.warning(f"MacroContextProvider.fetch failed, using fallback: {e}")
            return FALLBACK_MACRO

    def _fetch_from_perplexity(self) -> str:
        now = datetime.utcnow()
        date_str = now.strftime("%Y-%m-%d")
        month_str = now.strftime("%B")
        year_str = now.strftime("%Y")

        prompt = (
            f"You are a financial news summarizer. Use the perplexity search tool to search for:\n"
            f'1. "XAUUSD gold price drivers {date_str}"\n'
            f'2. "USD DXY dollar index today {date_str}"\n'
            f'3. "Federal Reserve interest rates outlook {month_str} {year_str}"\n\n'
            f"Then synthesize the results into exactly 5 concise bullet points (max 20 words each) "
            f"about current macro factors affecting gold. "
            f'Format each bullet as: "• [factor]: [impact on gold]"\n'
            f"Output ONLY the 5 bullets, nothing else."
        )

        cwd = self._strategy_dir if self._strategy_dir else str(Path.cwd())

        try:
            result = subprocess.run(
                [self._cli, "--dangerously-skip-permissions", "--output-format", "json"],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=cwd,
                timeout=45,
            )
        except subprocess.TimeoutExpired:
            logger.error("MacroContextProvider: Claude CLI timed out after 45s")
            raise
        except subprocess.CalledProcessError as e:
            logger.error(f"MacroContextProvider: Claude CLI process error: {e}")
            raise

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout
            logger.error(f"MacroContextProvider: Claude CLI exit {result.returncode}: {error_msg}")
            raise RuntimeError(f"Claude CLI exit code {result.returncode}: {error_msg}")

        try:
            response_json = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            logger.error(f"MacroContextProvider: invalid JSON from Claude CLI: {result.stdout[:200]}")
            raise RuntimeError(f"Invalid JSON response: {e}") from e

        if response_json.get("type") != "result":
            raise RuntimeError(f"Unexpected response type: {response_json.get('type')}")

        raw = response_json.get("result", "")

        bullets = [line.strip() for line in raw.splitlines() if line.strip().startswith("•")]
        if not bullets:
            raise RuntimeError("No bullet points found in Perplexity response")

        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        return f"MACRO_CONTEXT (live, {timestamp}):\n" + "\n".join(bullets)

    def get_cached_or_fallback(self) -> str:
        return self._cache if self._cache else FALLBACK_MACRO

    def is_stale(self) -> bool:
        if not self._cache or not self._cache_ts:
            return True
        return datetime.utcnow() - self._cache_ts > timedelta(hours=_CACHE_TTL_HOURS)
