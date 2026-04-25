"""MarketDataProvider — assembles a structured text block for LLM consumption."""
import logging
from datetime import datetime
from typing import Optional

from src.market_data.levels import (
    find_swing_highs, find_swing_lows, detect_structure,
    calc_atr, find_ssl_bsl, check_ssl_swept,
)

logger = logging.getLogger(__name__)

CANDLE_COUNTS = {"H1": 48, "H4": 12, "D1": 7, "W1": 4}


class MarketDataProvider:
    def __init__(self, mt4_bridge):
        self.mt4 = mt4_bridge

    def fetch_all_candles(self) -> dict:
        result = {}
        for tf, count in CANDLE_COUNTS.items():
            try:
                candles = self.mt4.get_candles("XAUUSD", tf, count)
                result[tf] = candles if candles is not None else []
            except Exception as e:
                logger.warning(f"fetch_all_candles: {tf} failed: {e}")
                result[tf] = []
        return result

    def build_text_block(
        self,
        market_context: dict,
        candles: dict,
        macro_context: str = None,
    ) -> str:
        try:
            lines = []

            price = market_context.get("price") or {}
            bid = price.get("bid", 0.0)
            ask = price.get("ask", 0.0)
            spread = price.get("spread", 0.0)

            account = market_context.get("account") or {}
            balance = account.get("balance", 0.0)
            equity = account.get("equity", 0.0)
            free_margin = account.get("free_margin", 0.0)

            server_time = market_context.get("server_time") or ""
            session_label = market_context.get("session_label", "Unknown")

            date_str = ""
            time_str = ""
            if server_time:
                try:
                    dt = datetime.strptime(server_time, "%Y.%m.%d %H:%M:%S")
                    date_str = dt.strftime("%Y-%m-%d")
                    time_str = dt.strftime("%H:%M")
                except (ValueError, TypeError):
                    date_str = server_time[:10] if len(server_time) >= 10 else server_time
                    time_str = server_time[11:16] if len(server_time) >= 16 else ""

            h1_candles = candles.get("H1", [])
            h4_candles = candles.get("H4", [])
            d1_candles = candles.get("D1", [])
            w1_candles = candles.get("W1", [])

            atr_h1 = calc_atr(h1_candles) if h1_candles else 0.0
            atr_h4 = calc_atr(h4_candles) if h4_candles else 0.0

            atr_h1_str = f"{atr_h1:.1f}" if atr_h1 > 0.0 else "N/A"
            atr_h4_str = f"{atr_h4:.1f}" if atr_h4 > 0.0 else "N/A"

            lines.append(
                f"XAUUSD {date_str} {time_str} UTC | "
                f"bid={bid:.2f} spread={spread:.2f}pts | {session_label}"
            )
            lines.append(
                f"Account: ${balance:.2f} | Equity: ${equity:.2f} | Free: ${free_margin:.2f}"
            )
            lines.append(f"ATR_H1={atr_h1_str} ATR_H4={atr_h4_str}")
            lines.append("")

            lines.append(f"━━ H1 [{len(h1_candles)} candles, oldest→newest] ━━")
            if h1_candles:
                lines.append(self._format_candles(h1_candles, per_line=8, mark_last=False))
            else:
                lines.append("[unavailable]")
            lines.append("")

            lines.append(f"━━ H4 [{len(h4_candles)} candles, oldest→newest] ━━")
            if h4_candles:
                lines.append(self._format_candles(h4_candles, per_line=8, mark_last=False))
            else:
                lines.append("[unavailable]")
            lines.append("")

            lines.append(f"━━ D1 [{len(d1_candles)} candles, oldest→newest] ━━")
            if d1_candles:
                lines.append(self._format_candles(d1_candles, per_line=8, mark_last=True))
            else:
                lines.append("[unavailable]")
            lines.append("")

            lines.append(f"━━ W1 [{len(w1_candles)} candles, oldest→newest] ━━")
            if w1_candles:
                lines.append(self._format_candles(w1_candles, per_line=8, mark_last=True))
            else:
                lines.append("[unavailable]")
            lines.append("")

            levels = find_ssl_bsl(h1_candles, d1_candles, w1_candles)
            weekly_ssl = levels.get("weekly_ssl")
            weekly_bsl = levels.get("weekly_bsl")
            daily_ssl = levels.get("daily_ssl")
            daily_bsl = levels.get("daily_bsl")
            daily_open = levels.get("daily_open")

            ssl_swept_tag = ""
            if weekly_ssl is not None and h1_candles:
                swept = check_ssl_swept(h1_candles, weekly_ssl)
                if swept.get("swept"):
                    candles_ago = swept.get("candles_ago", 0)
                    pts_below = swept.get("pts_below", 0.0)
                    ssl_swept_tag = f" SSL_SWEPT({candles_ago}bars,{pts_below:.1f}pts_below)"

            weekly_ssl_v = weekly_ssl if weekly_ssl is not None else 0.0
            weekly_bsl_v = weekly_bsl if weekly_bsl is not None else 0.0
            daily_ssl_v = daily_ssl if daily_ssl is not None else 0.0
            daily_bsl_v = daily_bsl if daily_bsl is not None else 0.0
            daily_open_v = daily_open if daily_open is not None else 0.0

            ssl_nearest = max(weekly_ssl_v, daily_ssl_v)
            bsl_nearest = min(
                weekly_bsl_v if weekly_bsl_v > 0.0 else float("inf"),
                daily_bsl_v if daily_bsl_v > 0.0 else float("inf"),
            )
            if bsl_nearest == float("inf"):
                bsl_nearest = 0.0

            h1_structure = detect_structure(h1_candles).get("description", "RANGING") if h1_candles else "RANGING"
            d1_structure = detect_structure(d1_candles).get("description", "RANGING") if d1_candles else "RANGING"

            atr_h1_ref = atr_h1 if atr_h1 > 0.0 else 0.0

            lines.append("KEY LEVELS:")
            lines.append(
                f"W: H={weekly_bsl_v:.2f} L={weekly_ssl_v:.2f}{ssl_swept_tag}"
            )
            lines.append(
                f"D: PDH={daily_bsl_v:.2f} PDL={daily_ssl_v:.2f} | TodayO={daily_open_v:.2f}"
            )
            lines.append(f"Structure: H1={h1_structure} D1={d1_structure}")
            lines.append(
                f"SSL_nearest={ssl_nearest:.2f} | BSL_nearest={bsl_nearest:.2f}"
            )
            lines.append(f"SuggestedSL_ref={atr_h1_ref:.1f}pts (1×ATR_H1)")
            lines.append("")

            positions = market_context.get("positions", [])
            lines.append(f"OPEN POSITIONS: {self._format_positions(positions)}")

            if macro_context is not None:
                lines.append("")
                lines.append(macro_context)

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"build_text_block failed: {e}", exc_info=True)
            return f"[MarketDataProvider error: {e}]"

    def _format_candles(
        self, candles: list, per_line: int = 8, mark_last: bool = False
    ) -> str:
        if not candles:
            return "[unavailable]"

        formatted = []
        for i, c in enumerate(candles):
            o = f"{c['open']:.2f}"
            h = f"{c['high']:.2f}"
            l = f"{c['low']:.2f}"
            cl = f"{c['close']:.2f}"
            cell = f"{o}/{h}/{l}/{cl}"
            if mark_last and i == len(candles) - 1:
                cell += "*"
            formatted.append(cell)

        lines = []
        for i in range(0, len(formatted), per_line):
            lines.append(" | ".join(formatted[i : i + per_line]))
        return "\n".join(lines)

    def _format_positions(self, positions: list) -> str:
        if not positions:
            return "None"
        parts = []
        for p in positions:
            ticket = p.get("ticket", 0)
            side = p.get("type", "?")
            lots = p.get("lots", 0.0)
            entry = p.get("open_price", 0.0)
            sl = p.get("sl", 0.0)
            tp = p.get("tp", 0.0)
            pnl = p.get("profit", 0.0)
            parts.append(
                f"#{ticket} {side} {lots}L @{entry:.2f} SL={sl:.2f} TP={tp:.2f} PnL={pnl:+.2f}"
            )
        return " | ".join(parts)
