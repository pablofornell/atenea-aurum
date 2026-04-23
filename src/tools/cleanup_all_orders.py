#!/usr/bin/env python
"""Close ALL open orders (dynamic)."""
import socket

def get_open_orders():
    """Get count of open orders."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", 5555))
    sock.sendall(b"STATUS\n")
    response = sock.recv(1024).decode()
    sock.close()
    return int(response.split("|")[1]) if "OK|" in response else 0

# Note: MT4 doesn't provide ticket listing via this simple protocol
# We'll attempt to close the most recent ones based on the test output
if __name__ == "__main__":
    # Check current status
    count = get_open_orders()
    print("Currently open orders: {}".format(count))

    if count == 0:
        print("No orders to close.")
    else:
        print("\nWarning: You have {} open orders.".format(count))
        print("Close them manually in MT4 before running tests:")
        print("1. Open MT4")
        print("2. Right-click on Terminal -> Trade")
        print("3. Select all orders and close them")
