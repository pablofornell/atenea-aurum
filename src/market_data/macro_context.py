"""Macro context provider: static macro principles for gold trading."""
import logging

logger = logging.getLogger(__name__)

FALLBACK_MACRO = """MACRO_CONTEXT (static principles — update weekly in strategy/CLAUDE.md if conditions change):
• DXY inverse correlation: DXY > 104 = significant headwind for gold; DXY < 100 = tailwind
• Fed policy: hawkish (higher-for-longer rates) = bearish gold; rate cuts / dovish pivot = bullish gold
• Risk-off / geopolitical tension: bullish gold (safe-haven demand spikes)
• Real yields: negative real yields = bullish gold; rising real yields (>2%) = bearish gold
• Institutional flow: gold regularly sweeps weekly liquidity levels before reversing — confirms SMC bias
• Structural support: gold in long-term uptrend (2020–2026); pullbacks to key HTF OBs tend to be bought"""


class MacroContextProvider:
    """Provides macro context for gold trading analysis.

    Currently returns static principles. For live data, update strategy/CLAUDE.md
    with current DXY level, Fed stance, and key macro events weekly.
    """

    def __init__(self, claude_cli_path: str = "claude", strategy_dir: str = None):
        pass  # parameters kept for interface compatibility with agent.py

    def fetch(self) -> str:
        return FALLBACK_MACRO

    def get_cached_or_fallback(self) -> str:
        return FALLBACK_MACRO
