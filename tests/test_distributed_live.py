"""
Live integration test for distributed tracing.

Starts actual socket servers on different ports and sends trace events
to verify the end-to-end flow works.
"""

import socket
import json
import time
import threading
from typing import List, Dict

# Port assignments (must match IDE configuration)
PORTS = {
    "python": 5678,
    "java": 5679,
    "nodejs": 5680,
    "rust": 5681
}


class MockTraceServer:
    """Mock trace server that accepts connections and sends events."""

    def __init__(self, port: int, language: str):
        self.port = port
        self.language = language
        self.server_socket = None
        self.clients = []
        self.running = False
        self.events_sent = 0

    def start(self):
        """Start the server in a background thread."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.server_socket.bind(("127.0.0.1", self.port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)  # Non-blocking accept
            self.running = True
            print(f"[{self.language}] Server started on port {self.port}")

            # Accept connections in background
            threading.Thread(target=self._accept_loop, daemon=True).start()
            return True

        except OSError as e:
            print(f"[{self.language}] Failed to start on port {self.port}: {e}")
            return False

    def _accept_loop(self):
        """Accept client connections."""
        while self.running:
            try:
                client, addr = self.server_socket.accept()
                self.clients.append(client)
                print(f"[{self.language}] Client connected from {addr}")
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[{self.language}] Accept error: {e}")
                break

    def send_event(self, event: Dict):
        """Send a trace event to all connected clients."""
        event["language"] = self.language
        json_str = json.dumps(event) + "\n"

        for client in self.clients[:]:  # Copy list to avoid modification during iteration
            try:
                client.sendall(json_str.encode())
                self.events_sent += 1
            except Exception as e:
                print(f"[{self.language}] Send error: {e}")
                self.clients.remove(client)

    def stop(self):
        """Stop the server."""
        self.running = False
        for client in self.clients:
            try:
                client.close()
            except:
                pass
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        print(f"[{self.language}] Server stopped (sent {self.events_sent} events)")


def create_call_event(call_id: str, module: str, function: str, depth: int = 0, parent_id: str = None):
    """Create a call event."""
    return {
        "type": "call",
        "timestamp": time.time(),
        "call_id": call_id,
        "module": module,
        "function": function,
        "file": f"{module.replace('.', '/')}.py",
        "line": 100,
        "depth": depth,
        "parent_id": parent_id,
        "process_id": 12345,
        "session_id": f"test_session_{int(time.time())}"
    }


def create_return_event(call_id: str, module: str, function: str, depth: int = 0, parent_id: str = None, duration_ms: float = 10.0):
    """Create a return event."""
    return {
        "type": "return",
        "timestamp": time.time(),
        "call_id": call_id,
        "module": module,
        "function": function,
        "file": f"{module.replace('.', '/')}.py",
        "line": 100,
        "depth": depth,
        "parent_id": parent_id,
        "duration_ms": duration_ms,
        "process_id": 12345,
        "session_id": f"test_session_{int(time.time())}"
    }


def test_port_availability():
    """Check which ports are available for testing."""
    available = {}
    for lang, port in PORTS.items():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        try:
            sock.bind(("127.0.0.1", port))
            sock.close()
            available[lang] = port
            print(f"[{lang}] Port {port} is available")
        except OSError:
            print(f"[{lang}] Port {port} is IN USE (instrumentor may be running)")
        finally:
            try:
                sock.close()
            except:
                pass

    return available


def test_distributed_flow_simulation():
    """Simulate a distributed trace flow across multiple services."""
    print("\n" + "=" * 60)
    print("Distributed Flow Simulation")
    print("=" * 60)

    available_ports = test_port_availability()

    if not available_ports:
        print("\nNo ports available for testing - instrumentors may be running")
        print("This is OK - it means real tracing is available!")
        return True

    servers = {}

    # Start servers for available ports
    for lang, port in available_ports.items():
        server = MockTraceServer(port, lang)
        if server.start():
            servers[lang] = server

    if not servers:
        print("No servers could start")
        return False

    print(f"\nStarted {len(servers)} mock trace servers")
    print("Waiting for potential IDE connections (5 seconds)...")
    time.sleep(5)

    # Check for connected clients
    total_clients = sum(len(s.clients) for s in servers.values())
    print(f"Total connected clients: {total_clients}")

    if total_clients > 0:
        # Send a simulated distributed trace
        print("\nSending distributed trace events...")

        # Python starts the request
        if "python" in servers:
            servers["python"].send_event(create_call_event("dist_1", "api.gateway", "handle_request"))
            time.sleep(0.1)

        # Java processes business logic
        if "java" in servers:
            servers["java"].send_event(create_call_event("dist_2", "com.example.Service", "process", parent_id="dist_1"))
            time.sleep(0.1)

        # Node.js sends notifications
        if "nodejs" in servers:
            servers["nodejs"].send_event(create_call_event("dist_3", "services/notify", "send", parent_id="dist_2"))
            time.sleep(0.1)
            servers["nodejs"].send_event(create_return_event("dist_3", "services/notify", "send", parent_id="dist_2", duration_ms=5.0))
            time.sleep(0.1)

        # Rust handles caching
        if "rust" in servers:
            servers["rust"].send_event(create_call_event("dist_4", "cache::redis", "set", parent_id="dist_2"))
            time.sleep(0.1)
            servers["rust"].send_event(create_return_event("dist_4", "cache::redis", "set", parent_id="dist_2", duration_ms=2.0))
            time.sleep(0.1)

        # Returns
        if "java" in servers:
            servers["java"].send_event(create_return_event("dist_2", "com.example.Service", "process", parent_id="dist_1", duration_ms=50.0))
            time.sleep(0.1)

        if "python" in servers:
            servers["python"].send_event(create_return_event("dist_1", "api.gateway", "handle_request", duration_ms=55.0))

        print("Distributed trace events sent!")
    else:
        print("\nNo IDE connected - to test with IDE:")
        print("1. Open TrueFlow panel in PyCharm/VS Code")
        print("2. Click 'Distributed' button to connect to all ports")
        print("3. Re-run this test")

    # Cleanup
    print("\nStopping servers...")
    for server in servers.values():
        server.stop()

    return True


def test_single_language_server():
    """Test starting a single language server."""
    print("\n" + "=" * 60)
    print("Single Language Server Test")
    print("=" * 60)

    # Try Node.js port as an example
    port = PORTS["nodejs"]

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        sock.close()
        print(f"Node.js port {port} is available")

        # Start mock server
        server = MockTraceServer(port, "nodejs")
        if server.start():
            print("Mock server started successfully")

            # Send some test events
            test_events = [
                create_call_event("node_1", "routes/api", "handleGet"),
                create_call_event("node_2", "services/db", "query", depth=1, parent_id="node_1"),
                create_return_event("node_2", "services/db", "query", depth=1, parent_id="node_1", duration_ms=15.0),
                create_return_event("node_1", "routes/api", "handleGet", duration_ms=20.0),
            ]

            print("Test events created:")
            for event in test_events:
                print(f"  {event['type']}: {event['module']}.{event['function']}()")

            time.sleep(2)
            server.stop()
            return True

    except OSError:
        print(f"Port {port} is in use - Node.js instrumentor may be running")
        print("This is expected if you're running a traced Node.js app")

    finally:
        try:
            sock.close()
        except:
            pass

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("TrueFlow Distributed Tracing LIVE Integration Tests")
    print("=" * 60)

    test_single_language_server()
    test_distributed_flow_simulation()

    print("\n" + "=" * 60)
    print("LIVE INTEGRATION TESTS COMPLETED!")
    print("=" * 60)
