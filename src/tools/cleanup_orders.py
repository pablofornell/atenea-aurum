#!/usr/bin/env python
"""Close all open orders."""
import socket

def get_status():
    """Get count of open orders."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", 5555))
    sock.sendall(b"STATUS\n")
    response = sock.recv(1024).decode()
    sock.close()
    return int(response.split("|")[1]) if "OK|" in response else 0

def close_all_orders():
    """Close all open orders by ticket."""
    tickets = [73552598, 73552599, 73552600, 73552601]

    for ticket in tickets:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("127.0.0.1", 5555))
        cmd = "CLOSE|{}\n".format(ticket)
        sock.sendall(cmd.encode())
        response = sock.recv(1024).decode().strip()
        print("CLOSE {} -> {}".format(ticket, response))
        sock.close()

if __name__ == "__main__":
    print("Checking open orders...")
    count = get_status()
    print("Open orders: {}".format(count))

    if count > 0:
        print("\nClosing all orders...")
        close_all_orders()
        print("\nVerifying...")
        count = get_status()
        print("Open orders now: {}".format(count))
    else:
        print("No orders to close.")
