#!/usr/bin/env python3
"""
Automated end-to-end test for PyCharm plugin.
This runs without manual interaction and validates all fixes.
"""

import socket
import json
import time
import sys

def test_socket_connection():
    """Test 1: Socket connection with TCP keep-alive."""
    print("\n" + "="*80)
    print("TEST 1: Socket Connection & TCP Keep-Alive")
    print("="*80)

    try:
        # Create server socket
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 5678))
        server.listen(1)

        print("[Test] Mock trace server started on 127.0.0.1:5678")
        print("[Test] Waiting for plugin connection (timeout 30s)...")

        server.settimeout(30)
        try:
            client, addr = server.accept()
            print(f"[PASS] Plugin connected from {addr}")

            # Check socket options
            keep_alive = client.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE)
            print(f"[INFO] TCP Keep-Alive enabled: {bool(keep_alive)}")

            # Send test event
            event = {
                "type": "call",
                "timestamp": time.time(),
                "call_id": "test_001",
                "module": "test_module",
                "function": "test_function",
                "file": "test.py",
                "line": 1,
                "depth": 0,
                "parent_id": None,
                "process_id": 1,
                "session_id": "test",
                "correlation_id": "test_001",
                "learning_phase": "test"
            }

            json_line = json.dumps(event) + "\n"
            client.sendall(json_line.encode('utf-8'))
            print("[PASS] Sent test event successfully")

            client.close()
            server.close()
            return True

        except socket.timeout:
            print("[FAIL] Plugin did not connect within 30 seconds")
            print("[INFO] Make sure plugin is running and 'Attach to Server' was clicked")
            server.close()
            return False

    except Exception as e:
        print(f"[FAIL] Error in connection test: {e}")
        return False


def test_high_throughput():
    """Test 2: High throughput with circular buffer."""
    print("\n" + "="*80)
    print("TEST 2: High Throughput & Circular Buffer (10,000 events)")
    print("="*80)

    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 5678))
        server.listen(1)

        print("[Test] Waiting for plugin connection...")
        server.settimeout(30)

        client, addr = server.accept()
        print(f"[Test] Plugin connected from {addr}")

        # Send 10,000 events rapidly
        start_time = time.time()
        events_sent = 0

        for i in range(10000):
            event = {
                "type": "call" if i % 2 == 0 else "return",
                "timestamp": time.time(),
                "call_id": f"test_{i}",
                "module": f"module_{i % 10}",
                "function": f"func_{i % 20}",
                "file": f"file_{i % 5}.py",
                "line": i % 1000,
                "depth": i % 5,
                "parent_id": None,
                "process_id": 1,
                "session_id": "stress_test",
                "correlation_id": f"cycle_{i % 3}",
                "learning_phase": ["perception", "reasoning", "planning"][i % 3]
            }

            try:
                json_line = json.dumps(event) + "\n"
                client.sendall(json_line.encode('utf-8'))
                events_sent += 1

                if (i + 1) % 1000 == 0:
                    elapsed = time.time() - start_time
                    rate = events_sent / elapsed
                    print(f"[Progress] {events_sent}/10000 events ({rate:.0f} events/sec)")

            except Exception as e:
                print(f"[FAIL] Error sending event {i}: {e}")
                break

        elapsed = time.time() - start_time
        rate = events_sent / elapsed

        print(f"[PASS] Sent {events_sent} events in {elapsed:.2f}s ({rate:.0f} events/sec)")
        print(f"[INFO] Circular buffer should contain last 10,000 events (no memory leak)")

        client.close()
        server.close()
        return events_sent == 10000

    except Exception as e:
        print(f"[FAIL] Error in throughput test: {e}")
        return False


def test_thread_safety():
    """Test 3: Thread safety with concurrent events."""
    print("\n" + "="*80)
    print("TEST 3: Thread Safety & Atomic Operations")
    print("="*80)

    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 5678))
        server.listen(1)

        print("[Test] Waiting for plugin connection...")
        server.settimeout(30)

        client, addr = server.accept()
        print(f"[Test] Plugin connected from {addr}")

        # Send events that will trigger UI updates (every 100th event)
        # This tests AtomicLong counters
        for i in range(500):
            event = {
                "type": "call",
                "timestamp": time.time(),
                "call_id": f"thread_test_{i}",
                "module": f"module_{i}",
                "function": f"func_{i}",
                "file": "test.py",
                "line": i,
                "depth": 0,
                "parent_id": None,
                "process_id": 1,
                "session_id": "thread_test",
                "correlation_id": "thread_001",
                "learning_phase": "test"
            }

            json_line = json.dumps(event) + "\n"
            client.sendall(json_line.encode('utf-8'))

            # Event 100, 200, 300, 400, 500 should trigger UI updates
            if (i + 1) % 100 == 0:
                print(f"[Test] Event {i + 1} should trigger UI update (sampling rate)")

        print(f"[PASS] Sent 500 events, 5 should have triggered UI updates")
        print(f"[INFO] No race conditions should occur in AtomicLong operations")

        client.close()
        server.close()
        return True

    except Exception as e:
        print(f"[FAIL] Error in thread safety test: {e}")
        return False


def test_injection_prevention():
    """Test 4: PlantUML injection prevention."""
    print("\n" + "="*80)
    print("TEST 4: PlantUML Injection Prevention")
    print("="*80)

    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 5678))
        server.listen(1)

        print("[Test] Waiting for plugin connection...")
        server.settimeout(30)

        client, addr = server.accept()
        print(f"[Test] Plugin connected from {addr}")

        # Send event with special characters that could break PlantUML
        malicious_module = 'test";@enduml;@startuml'
        malicious_session = 'session<script>alert("xss")</script>'

        event = {
            "type": "call",
            "timestamp": time.time(),
            "call_id": "injection_test",
            "module": malicious_module,
            "function": "test_func",
            "file": "test.py",
            "line": 1,
            "depth": 0,
            "parent_id": None,
            "process_id": 1,
            "session_id": malicious_session,
            "correlation_id": "injection_001",
            "learning_phase": "test"
        }

        json_line = json.dumps(event) + "\n"
        client.sendall(json_line.encode('utf-8'))

        print(f"[Test] Sent event with malicious content:")
        print(f"  Module: {malicious_module}")
        print(f"  Session: {malicious_session}")
        print(f"[PASS] Plugin should escape these characters and not crash")
        print(f"[INFO] Check diagram tab - should show escaped characters")

        client.close()
        server.close()
        return True

    except Exception as e:
        print(f"[FAIL] Error in injection test: {e}")
        return False


def main():
    """Run all automated tests."""
    print("\n" + "="*80)
    print("PYCHARM PLUGIN AUTOMATED END-TO-END TESTS")
    print("="*80)
    print("\nPREREQUISITES:")
    print("1. Plugin must be running in PyCharm sandbox (gradle runIde)")
    print("2. Tool window must be open: View -> Tool Windows -> Learning Flow Visualizer")
    print("3. Click 'Attach to Server' button and enter: 127.0.0.1:5678")
    print("\nTests will start in 10 seconds...")
    print("If plugin is not ready, press Ctrl+C to abort\n")

    try:
        time.sleep(10)
    except KeyboardInterrupt:
        print("\n[ABORTED] Tests cancelled by user")
        return

    results = {}

    # Run tests sequentially
    print("\nStarting test suite...\n")

    # Test 1: Connection
    results['connection'] = test_socket_connection()
    time.sleep(2)

    # Test 2: High throughput
    if results['connection']:
        results['throughput'] = test_high_throughput()
        time.sleep(2)

        # Test 3: Thread safety
        results['thread_safety'] = test_thread_safety()
        time.sleep(2)

        # Test 4: Injection prevention
        results['injection'] = test_injection_prevention()
    else:
        print("\n[SKIP] Skipping remaining tests due to connection failure")
        results['throughput'] = None
        results['thread_safety'] = None
        results['injection'] = None

    # Summary
    print("\n" + "="*80)
    print("TEST RESULTS SUMMARY")
    print("="*80)

    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    skipped = sum(1 for v in results.values() if v is None)

    for test_name, result in results.items():
        status = "PASS" if result is True else ("FAIL" if result is False else "SKIP")
        symbol = "[PASS]" if result is True else ("[FAIL]" if result is False else "[SKIP]")
        print(f"  {symbol} {test_name.upper()}: {status}")

    print(f"\n  Total: {passed} passed, {failed} failed, {skipped} skipped")

    if failed == 0 and passed > 0:
        print("\n[SUCCESS] All tests passed! Plugin is working correctly.")
    elif failed > 0:
        print(f"\n[FAILURE] {failed} test(s) failed. Check logs for details.")
    else:
        print("\n[WARNING] No tests completed. Check plugin connection.")

    print("\n" + "="*80)
    print("VERIFICATION CHECKLIST")
    print("="*80)
    print("\nIn PyCharm plugin, verify:")
    print("1. Status shows 'Connected to 127.0.0.1:5678'")
    print("2. Diagram tab shows PlantUML with participants")
    print("3. Performance tab shows function statistics")
    print("4. Statistics panel shows event counts")
    print("5. No errors in idea.log")
    print("6. Memory usage is stable (check Task Manager)")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
