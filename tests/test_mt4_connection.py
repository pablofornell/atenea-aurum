#!/usr/bin/env python3
"""
Test the live connection with the MT4 Expert Advisor.
Run: python tests/test_mt4_connection.py

Requires MT4 running with AURUM_Bridge EA attached and listening.
Mirrors the call sequence and data volumes used by build_context() + executor.py.

NOTE: the EA only accepts one client at a time. If aurum.py is already running
and holding the connection, this test will fail. Stop the bot before running.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import config
from bridge.mt4_client import MT4Client, MT4ConnectionError

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = PASS if ok else FAIL
    line = f"  [{status}] {label}"
    if detail:
        line += f"  --  {detail}"
    print(line)
    return ok


def main() -> None:
    print(f"\nMT4 connection test  ({config.MT4_HOST}:{config.MT4_PORT})\n")
    all_ok = True
    mt4 = MT4Client(config.MT4_HOST, config.MT4_PORT)

    # 1. TCP connect
    try:
        mt4.connect()
        all_ok &= check("TCP connect", True, f"{config.MT4_HOST}:{config.MT4_PORT}")
    except MT4ConnectionError as e:
        check("TCP connect", False, str(e))
        print("\nCannot continue -- MT4 not reachable.\n")
        sys.exit(1)

    # 2. PING  (basic sanity, not used in production but validates protocol)
    try:
        ok = mt4.ping()
        all_ok &= check("PING -> PONG", ok)
    except Exception as e:
        all_ok &= check("PING -> PONG", False, str(e))

    # --- from here the order mirrors build_context() ---

    # 3. GET_PRICE
    try:
        price = mt4.get_price(config.SYMBOL)
        ok = (
            isinstance(price.get("bid"), float)
            and isinstance(price.get("ask"), float)
            and price["bid"] > 0
            and price["ask"] >= price["bid"]
        )
        detail = (
            f"bid={price['bid']:.2f}  ask={price['ask']:.2f}  spread={price['spread']:.2f}"
        ) if ok else str(price)
        all_ok &= check(f"GET_PRICE ({config.SYMBOL})", ok, detail)
    except Exception as e:
        all_ok &= check(f"GET_PRICE ({config.SYMBOL})", False, str(e))

    # 4. GET_ACCOUNT
    try:
        acc = mt4.get_account()
        ok = (
            isinstance(acc.get("balance"), float)
            and isinstance(acc.get("equity"), float)
            and isinstance(acc.get("free_margin"), float)
            and isinstance(acc.get("currency"), str)
            and acc["balance"] > 0
        )
        detail = (
            f"balance={acc['balance']:.2f} {acc['currency']}  "
            f"equity={acc['equity']:.2f}  margin={acc['free_margin']:.2f}"
        ) if ok else str(acc)
        all_ok &= check("GET_ACCOUNT", ok, detail)
    except Exception as e:
        all_ok &= check("GET_ACCOUNT", False, str(e))

    # 5. GET_ATR H1/14
    try:
        atr = mt4.get_atr(config.SYMBOL, 14, 60)
        ok = isinstance(atr, float) and atr > 0
        all_ok &= check("GET_ATR H1/14", ok, f"atr={atr:.4f}" if ok else str(atr))
    except Exception as e:
        all_ok &= check("GET_ATR H1/14", False, str(e))

    # 6. GET_DAY_OHLC
    try:
        ohlc = mt4.get_day_ohlc(config.SYMBOL)
        ok = isinstance(ohlc.get("prev_close"), float) and ohlc["prev_close"] > 0
        detail = (
            f"prev H:{ohlc['prev_high']:.2f} L:{ohlc['prev_low']:.2f} "
            f"C:{ohlc['prev_close']:.2f}  today O:{ohlc['today_open']:.2f}"
        ) if ok else str(ohlc)
        all_ok &= check("GET_DAY_OHLC", ok, detail)
    except Exception as e:
        all_ok &= check("GET_DAY_OHLC", False, str(e))

    # 7. GET_WEEK_HL
    try:
        week = mt4.get_week_hl(config.SYMBOL)
        ok = (
            isinstance(week.get("prev_high"), float)
            and isinstance(week.get("prev_low"), float)
            and isinstance(week.get("curr_high"), float)
            and isinstance(week.get("curr_low"), float)
            and week["prev_high"] >= week["prev_low"]
        )
        detail = (
            f"prev H:{week['prev_high']:.2f} L:{week['prev_low']:.2f}  "
            f"curr H:{week['curr_high']:.2f} L:{week['curr_low']:.2f}"
        ) if ok else str(week)
        all_ok &= check("GET_WEEK_HL", ok, detail)
    except Exception as e:
        all_ok &= check("GET_WEEK_HL", False, str(e))

    # 8. GET_POSITIONS (can legitimately be empty)
    try:
        positions = mt4.get_positions()
        ok = isinstance(positions, list)
        detail = f"{len(positions)} open position(s)"
        if positions:
            p = positions[0]
            detail += f"  -- #{p['ticket']} {p['type']} {p['lots']}L @ {p['open']:.2f}"
        all_ok &= check("GET_POSITIONS", ok, detail)
    except Exception as e:
        all_ok &= check("GET_POSITIONS", False, str(e))

    # 9. GET_CANDLES — all four timeframes with production counts
    for tf_min, tf_label, count in [
        (240, "H4",  config.CANDLES_H4),
        (60,  "H1",  config.CANDLES_H1),
        (15,  "M15", config.CANDLES_M15),
        (5,   "M5",  config.CANDLES_M5),
    ]:
        try:
            candles = mt4.get_candles(config.SYMBOL, tf_min, count)
            ok = len(candles) > 0 and all(
                "open" in c and "high" in c and "low" in c and "close" in c
                for c in candles
            )
            detail = (
                f"{len(candles)}/{count} bars  last C:{candles[-1]['close']:.2f}"
            ) if ok else str(candles)
            all_ok &= check(f"GET_CANDLES {tf_label} ({count} bars)", ok, detail)
        except Exception as e:
            all_ok &= check(f"GET_CANDLES {tf_label} ({count} bars)", False, str(e))

    # 10. GET_STOPLEVEL  (used by executor.py)
    try:
        sl = mt4.get_stoplevel(config.SYMBOL)
        ok = isinstance(sl, float) and sl >= 0
        all_ok &= check("GET_STOPLEVEL", ok, f"{sl:.1f} points" if ok else str(sl))
    except Exception as e:
        all_ok &= check("GET_STOPLEVEL", False, str(e))

    mt4.disconnect()

    print()
    if all_ok:
        print("All checks passed.\n")
        sys.exit(0)
    else:
        print("One or more checks failed.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
