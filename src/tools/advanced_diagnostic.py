#!/usr/bin/env python
"""Advanced MT4 diagnostic - test different order parameters."""
import socket

def test_order(symbol, lots, sl, tp):
    """Test a complete order."""
    host = "127.0.0.1"
    port = 5555

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        sock.connect((host, port))

        cmd = "BUY|{}|{}|{}|{}\n".format(symbol, lots, sl, tp)
        sock.sendall(cmd.encode('utf-8'))
        response = sock.recv(1024).decode().strip()

        sock.close()
        return response

    except Exception as e:
        return "EXCEPTION: {}".format(e)

if __name__ == "__main__":
    print("="*70)
    print("Advanced MT4 Order Parameter Diagnostic")
    print("="*70)

    # Test 1: Different symbols
    print("\n[1] Testing different symbols with 0.01 lot, SL=100, TP=200...")
    symbols = ["XAUUSD", "GOLD", "AU", "EURUSD", "GBPUSD"]
    for sym in symbols:
        response = test_order(sym, 0.01, 1800.0, 1950.0)
        print("    {} -> {}".format(sym, response.split("|")[0] + "|" + response.split("|")[1][:30] if "|" in response else response[:40]))

    # Test 2: Same symbol, different SL/TP
    print("\n[2] Testing same symbol (XAUUSD), 0.01 lot, different SL/TP...")
    test_cases = [
        (1800.0, 1950.0, "Original"),
        (0.0, 0.0, "No SL/TP"),
        (1900.0, 1850.0, "Reversed SL/TP"),
        (1750.0, 2000.0, "Wide SL/TP"),
    ]
    for sl, tp, desc in test_cases:
        response = test_order("XAUUSD", 0.01, sl, tp)
        print("    SL={}, TP={} ({}) -> {}".format(sl, tp, desc, response.split("|")[0] + "|" + response.split("|")[1][:20] if "|" in response else response[:40]))

    # Test 3: Different lot sizes
    print("\n[3] Testing different lot sizes (XAUUSD, SL=0, TP=0)...")
    lots = [0.001, 0.01, 0.1, 1.0, 10.0]
    for lot in lots:
        response = test_order("XAUUSD", lot, 0.0, 0.0)
        print("    Lot {} -> {}".format(lot, response.split("|")[0] + "|" + response.split("|")[1][:20] if "|" in response else response[:40]))

    # Test 4: Check if EA is parsing commands correctly
    print("\n[4] Testing command parsing...")
    test_cmds = [
        ("PING", "PING"),
        ("STATUS", "STATUS"),
        ("BUY|XAUUSD|0.01", "Incomplete BUY (missing SL/TP)"),
        ("INVALID_CMD", "Invalid command"),
    ]

    host = "127.0.0.1"
    port = 5555

    for cmd, desc in test_cmds:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect((host, port))
            sock.sendall((cmd + "\n").encode())
            response = sock.recv(1024).decode().strip()
            sock.close()
            print("    {} -> {}".format(desc, response[:50]))
        except Exception as e:
            print("    {} -> ERROR: {}".format(desc, str(e)[:30]))

    print("\n" + "="*70)
    print("NEXT STEPS:")
    print("="*70)
    print("1. Check in MT4 what symbols are available")
    print("2. Check account settings for minimum lot size")
    print("3. Check MT4 Logs tab for specific error messages")
    print("4. Verify account is not in 'Trading Disabled' mode")
    print("5. If 'unknown_symbol' appears, use correct symbol name")
    print("6. Check if SL/TP are required or causing issues")
