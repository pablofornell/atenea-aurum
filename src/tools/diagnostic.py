#!/usr/bin/env python
"""Diagnostic script to test MT4 connection and identify issues."""
import socket
import time
import sys

def test_mt4_connection():
    """Test basic connectivity to MT4."""
    host = "127.0.0.1"
    port = 5555

    print("="*60)
    print("MT4 Connection Diagnostic Tool")
    print("="*60)

    # Test 1: Basic TCP connection
    print("\n[1] Testing TCP connection...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((host, port))
        print("[OK] Connected to {}:{}".format(host, port))
    except Exception as e:
        print("[ERROR] Connection failed: {}".format(e))
        return False

    try:
        # Test 2: PING command
        print("\n[2] Testing PING command...")
        sock.sendall(b"PING\n")
        response = sock.recv(1024).decode()
        print("[OK] PING response: {}".format(response.strip()))

        # Test 3: STATUS command
        print("\n[3] Testing STATUS command...")
        sock.sendall(b"STATUS\n")
        response = sock.recv(1024).decode()
        print("[OK] STATUS response: {}".format(response.strip()))

        # Test 4: Check for existing positions
        orders_count = int(response.split("|")[1]) if "OK" in response else 0
        print("    Open positions: {}".format(orders_count))

        if orders_count > 0:
            print("\n[WARNING] Found {} existing positions!".format(orders_count))
            print("    Close all positions before running tests.")
            sock.close()
            return False

        # Test 5: BUY order (start with smaller lot)
        print("\n[4] Testing BUY order...")
        buy_cmd = "BUY|XAUUSD|0.001|1800.0|1950.0\n"
        print("    Sending: {}".format(buy_cmd.strip()))
        sock.sendall(buy_cmd.encode('utf-8'))

        # Try to receive response with timeout
        sock.settimeout(3.0)
        try:
            response = sock.recv(1024).decode()
            print("[OK] BUY response: {}".format(response.strip()))

            if "OK|" in response:
                ticket = int(response.split("|")[1])
                print("    Order opened with ticket: {}".format(ticket))

                # Test 6: Query STATUS after order
                print("\n[5] Testing STATUS after order...")
                sock.sendall(b"STATUS\n")
                response = sock.recv(1024).decode()
                print("[OK] STATUS response: {}".format(response.strip()))

                # Test 7: Close order
                print("\n[6] Testing CLOSE order {}...".format(ticket))
                close_cmd = "CLOSE|{}\n".format(ticket)
                print("    Sending: {}".format(close_cmd.strip()))
                sock.sendall(close_cmd.encode('utf-8'))
                response = sock.recv(1024).decode()
                print("[OK] CLOSE response: {}".format(response.strip()))

                # Test 8: Final STATUS
                print("\n[7] Testing final STATUS...")
                sock.sendall(b"STATUS\n")
                response = sock.recv(1024).decode()
                print("[OK] Final STATUS: {}".format(response.strip()))

        except socket.timeout:
            print("[ERROR] Timeout waiting for response (connection may be closed)")
            print("    This indicates MT4 is dropping the connection after order.")
            return False
        except Exception as e:
            print("[ERROR] Error: {}".format(e))
            print("    Error type: {}".format(type(e).__name__))
            return False

        # Test 9: Test multiple commands without closing
        print("\n[8] Testing command sequence (no reconnect)...")
        for i in range(3):
            print("    PING #{}: ".format(i+1), end="")
            sock.sendall(b"PING\n")
            try:
                response = sock.recv(1024).decode()
                print("[OK] {}".format(response.strip()))
            except Exception as e:
                print("[ERROR] {}".format(e))
                return False

        print("\n[OK] All tests passed!")
        return True

    except Exception as e:
        print("[ERROR] Error during tests: {}".format(e))
        import traceback
        traceback.print_exc()
        return False
    finally:
        sock.close()
        print("\nConnection closed.")

def test_mt4_in_linux_mode():
    """Test if MT4 is expecting different line endings."""
    print("\n" + "="*60)
    print("Testing different line ending modes...")
    print("="*60)

    host = "127.0.0.1"
    port = 5555

    # Test with different line endings
    line_endings = [
        (b"PING\n", "LF (\\n)"),
        (b"PING\r\n", "CRLF (\\r\\n)"),
    ]

    for cmd, ending_name in line_endings:
        print("\nTesting with {}...".format(ending_name))
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            sock.connect((host, port))
            sock.sendall(cmd)
            response = sock.recv(1024).decode()
            print("[OK] Response: {}".format(response.strip()))
            sock.close()
        except Exception as e:
            print("[ERROR] Error: {}".format(e))

if __name__ == "__main__":
    success = test_mt4_connection()

    if not success:
        test_mt4_in_linux_mode()
        print("\n" + "="*60)
        print("DIAGNOSIS TIPS:")
        print("="*60)
        print("1. Verify AURUM_Bridge.mq4 is running in MT4")
        print("2. Check MT4 Logs tab for error messages")
        print("3. Verify account has sufficient balance for 0.01 lot XAUUSD")
        print("4. Check if MT4 is in 'not trading' or 'demo forbidden' mode")
        print("5. Try reducing lot size (0.001 instead of 0.01)")
        print("6. Restart MT4 platform completely")
        sys.exit(1)
    else:
        print("\n[OK] MT4 is working correctly with real orders!")
        sys.exit(0)
