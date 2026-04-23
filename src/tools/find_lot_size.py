#!/usr/bin/env python
"""Find valid lot size for MT4 account."""
import socket

def test_lot(lot_size):
    """Test a specific lot size."""
    host = "127.0.0.1"
    port = 5555

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        sock.connect((host, port))

        buy_cmd = "BUY|XAUUSD|{}|1800.0|1950.0\n".format(lot_size)
        sock.sendall(buy_cmd.encode('utf-8'))
        response = sock.recv(1024).decode().strip()

        if "OK|" in response:
            ticket = int(response.split("|")[1])
            print("[SUCCESS] Lot {} = VALID (ticket: {})".format(lot_size, ticket))

            # Close the position
            close_cmd = "CLOSE|{}\n".format(ticket)
            sock.sendall(close_cmd.encode('utf-8'))
            sock.recv(1024)

            sock.close()
            return ticket
        else:
            error_code = response.split("|")[1] if len(response.split("|")) > 1 else "unknown"
            print("[FAIL] Lot {} = ERROR {}".format(lot_size, error_code))
            sock.close()
            return None

    except Exception as e:
        print("[ERROR] Lot {}: {}".format(lot_size, e))
        return None

if __name__ == "__main__":
    print("="*60)
    print("Finding valid lot size for XAUUSD...")
    print("="*60 + "\n")

    # Test common lot sizes
    lot_sizes = [
        0.001,  # 1 microlot
        0.01,   # 1 minilot
        0.1,    # 1 lot
        0.5,
        1.0,
        5.0,
        10.0,
    ]

    found = False
    for lot in lot_sizes:
        if test_lot(lot):
            found = True
            break

    if not found:
        print("\nNo valid lot found. Trying custom sizes...")
        for lot in [0.002, 0.005, 0.02, 0.05, 0.2, 0.3, 0.4]:
            if test_lot(lot):
                break
