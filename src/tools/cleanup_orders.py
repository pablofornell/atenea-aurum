"""Emergency order cleanup — closes ALL open AURUM positions via MT4 bridge."""
import sys
import socket
import time


MT4_HOST = "127.0.0.1"
MT4_PORT = 5555
TIMEOUT = 5.0


def send_cmd(sock, cmd: str) -> str:
    sock.sendall((cmd + "\n").encode())
    data = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
        if b"\n" in chunk:
            break
    return data.decode().strip()


def main():
    print(f"Connecting to MT4 at {MT4_HOST}:{MT4_PORT}...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        sock.connect((MT4_HOST, MT4_PORT))
    except socket.error as e:
        print(f"ERROR: Cannot connect to MT4: {e}")
        print("Make sure AURUM_Bridge EA is active in MetaTrader 4.")
        sys.exit(1)

    print("Connected. Fetching open positions...")

    try:
        # Get all open positions
        response = send_cmd(sock, "GET_POSITIONS")
        if not response.startswith("OK"):
            print(f"ERROR: GET_POSITIONS failed: {response}")
            sys.exit(1)

        data_part = response[3:] if response.startswith("OK|") else ""
        if not data_part:
            print("No open positions found. Nothing to close.")
            sys.exit(0)

        # Parse positions
        tickets = []
        for pos_str in data_part.split(";"):
            if not pos_str.strip():
                continue
            parts = pos_str.split(",")
            if len(parts) >= 1:
                try:
                    tickets.append(int(parts[0]))
                except ValueError:
                    pass

        if not tickets:
            print("No open positions found. Nothing to close.")
            sys.exit(0)

        print(f"Found {len(tickets)} open position(s): {tickets}")
        print("Closing all positions...")

        closed = 0
        failed = 0
        for ticket in tickets:
            try:
                resp = send_cmd(sock, f"CLOSE|{ticket}")
                if resp.startswith("OK"):
                    print(f"  ✓ Closed ticket #{ticket}")
                    closed += 1
                else:
                    print(f"  ✗ Failed to close #{ticket}: {resp}")
                    failed += 1
                time.sleep(0.2)  # brief pause between closes
            except Exception as e:
                print(f"  ✗ Error closing #{ticket}: {e}")
                failed += 1

        print(f"\nDone: {closed} closed, {failed} failed.")

    finally:
        try:
            sock.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
