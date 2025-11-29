#!/usr/bin/env python3
"""
End-to-end test for PyCharm plugin with mock trace data.
This script simulates the Python trace server and sends mock events to test the plugin.
"""

import socket
import json
import time
import threading
import random
from datetime import datetime

# Mock trace data configuration
TRACE_SERVER_HOST = "127.0.0.1"
TRACE_SERVER_PORT = 5678
NUM_EVENTS = 1000  # Total events to send
EVENTS_PER_SECOND = 50  # Event rate
CORRELATION_IDS = ["test_cycle_001", "test_cycle_002", "test_cycle_003"]

# Mock modules and functions
MODULES = [
    "crawl4ai.embodied_ai.learning.reality_grounded_learner",
    "crawl4ai.embodied_ai.learning.semantic_reasoner",
    "crawl4ai.embodied_ai.inference.realtime_agent",
    "crawl4ai.embodied_ai.models.qwen_vl_wrapper",
    "crawl4ai.embodied_ai.memory.episodic_memory"
]

FUNCTIONS = [
    "forward_pass", "backward_pass", "update_weights",
    "encode_perception", "compute_loss", "predict",
    "store_experience", "retrieve_memories", "reason_about_state"
]

LEARNING_PHASES = ["perception", "reasoning", "planning", "execution", "reflection"]

class MockTraceServer:
    """Mock trace server that sends realistic trace events."""

    def __init__(self, host=TRACE_SERVER_HOST, port=TRACE_SERVER_PORT):
        self.host = host
        self.port = port
        self.server_socket = None
        self.client_socket = None
        self.running = False
        self.events_sent = 0

    def start(self):
        """Start the mock trace server."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            print(f"[Server] Mock trace server started on {self.host}:{self.port}")
            print(f"[Server] Waiting for PyCharm plugin to connect...")

            self.client_socket, client_address = self.server_socket.accept()
            print(f"[Server] Plugin connected from {client_address}")

            self.running = True
            return True

        except Exception as e:
            print(f"[Server] Error starting server: {e}")
            return False

    def generate_trace_event(self, event_type, call_id, correlation_id, depth=0):
        """Generate a realistic trace event."""
        module = random.choice(MODULES)
        function = random.choice(FUNCTIONS)

        # Simulate file path
        file_path = f"C:/Users/sathi/PycharmProjects/crawl4ai/src/{module.replace('.', '/')}.py"
        line_number = random.randint(100, 500)

        event = {
            "type": event_type,  # "call" or "return"
            "timestamp": time.time(),
            "call_id": call_id,
            "module": module,
            "function": function,
            "file": file_path,
            "line": line_number,
            "depth": depth,
            "parent_id": f"parent_{call_id}" if depth > 0 else None,
            "process_id": 12345,
            "session_id": "test_session_001",
            "correlation_id": correlation_id,
            "learning_phase": random.choice(LEARNING_PHASES)
        }

        return event

    def send_event(self, event):
        """Send a trace event as JSON line."""
        try:
            json_line = json.dumps(event) + "\n"
            self.client_socket.sendall(json_line.encode('utf-8'))
            self.events_sent += 1
            return True
        except Exception as e:
            print(f"[Server] Error sending event: {e}")
            return False

    def send_test_sequence(self):
        """Send a test sequence of trace events."""
        print(f"\n[Test] Starting end-to-end test with {NUM_EVENTS} events at {EVENTS_PER_SECOND} events/sec")
        print(f"[Test] This will test: buffer management, UI updates, statistics, and video detection\n")

        interval = 1.0 / EVENTS_PER_SECOND
        call_stack = []

        for i in range(NUM_EVENTS):
            # Randomly select correlation ID (simulates different learning cycles)
            correlation_id = random.choice(CORRELATION_IDS)

            # Simulate call/return pairs
            if random.random() > 0.5 or not call_stack:
                # Generate a "call" event
                call_id = f"call_{i}"
                depth = len(call_stack)
                event = self.generate_trace_event("call", call_id, correlation_id, depth)
                call_stack.append(call_id)
            else:
                # Generate a "return" event
                call_id = call_stack.pop()
                depth = len(call_stack)
                event = self.generate_trace_event("return", call_id, correlation_id, depth)

            if not self.send_event(event):
                print(f"[Test] Failed to send event {i}, stopping test")
                break

            # Progress reporting
            if (i + 1) % 100 == 0:
                elapsed = (i + 1) / EVENTS_PER_SECOND
                print(f"[Progress] Sent {i + 1}/{NUM_EVENTS} events ({elapsed:.1f}s elapsed)")

            # Rate limiting
            time.sleep(interval)

        print(f"\n[Test] Completed! Sent {self.events_sent} events")
        print(f"[Test] Plugin should have processed events and updated all tabs")
        print(f"[Test] Check PyCharm plugin for:")
        print(f"  - Diagram tab: Should show PlantUML with {len(set(MODULES))} participants")
        print(f"  - Performance tab: Should show timing statistics for functions")
        print(f"  - Dead Code tab: Should show called functions")
        print(f"  - Statistics: Total calls, avg time, etc.")
        print(f"  - Correlation IDs detected: {CORRELATION_IDS}")

    def stop(self):
        """Stop the server and cleanup."""
        self.running = False
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        print("\n[Server] Mock trace server stopped")


def run_stress_test():
    """Run a stress test with high event rate."""
    print("\n" + "="*80)
    print("STRESS TEST: Testing buffer overflow and memory leak fixes")
    print("="*80)

    server = MockTraceServer()

    if not server.start():
        print("[Error] Failed to start server")
        return

    try:
        # Send events at high rate
        print(f"\n[Stress Test] Sending 10,000 events at 200 events/sec")
        print(f"[Stress Test] This tests the circular buffer (max 10,000 events)")

        for i in range(10000):
            correlation_id = random.choice(CORRELATION_IDS)
            call_id = f"stress_{i}"
            event = server.generate_trace_event("call", call_id, correlation_id, 0)

            if not server.send_event(event):
                break

            if (i + 1) % 1000 == 0:
                print(f"[Stress Test] {i + 1}/10000 events sent")

            time.sleep(1.0 / 200)  # 200 events/sec

        print(f"\n[Stress Test] Completed! Buffer should contain last 10,000 events")
        print(f"[Stress Test] Plugin memory usage should be stable (no leak)")

    except KeyboardInterrupt:
        print("\n[Stress Test] Interrupted by user")
    finally:
        server.stop()


def run_video_detection_test():
    """Test Manim video detection."""
    print("\n" + "="*80)
    print("VIDEO DETECTION TEST: Testing ManimAutoRenderer")
    print("="*80)

    server = MockTraceServer()

    if not server.start():
        print("[Error] Failed to start server")
        return

    try:
        # Send events with specific correlation IDs for video detection
        test_correlation_ids = ["video_test_001", "video_test_002"]

        print(f"\n[Video Test] Sending events with correlation IDs: {test_correlation_ids}")
        print(f"[Video Test] Plugin should detect these and look for videos")

        for correlation_id in test_correlation_ids:
            # Send 10 events per correlation ID
            for i in range(10):
                call_id = f"{correlation_id}_{i}"
                event = server.generate_trace_event("call", call_id, correlation_id, 0)
                server.send_event(event)
                time.sleep(0.1)

            print(f"[Video Test] Sent events for {correlation_id}")
            print(f"[Video Test] Plugin will search for videos for 30 seconds (extended timeout)")

        print(f"\n[Video Test] Waiting 35 seconds for video detection to complete...")
        time.sleep(35)

        print(f"[Video Test] Check plugin logs for video detection attempts")
        print(f"[Video Test] Expected: 'No video found' warnings (no actual videos created)")

    except KeyboardInterrupt:
        print("\n[Video Test] Interrupted by user")
    finally:
        server.stop()


def run_connection_stability_test():
    """Test socket connection stability."""
    print("\n" + "="*80)
    print("CONNECTION STABILITY TEST: Testing TCP keep-alive and reconnection")
    print("="*80)

    server = MockTraceServer()

    if not server.start():
        print("[Error] Failed to start server")
        return

    try:
        print(f"\n[Stability Test] Sending events with 5-second pauses")
        print(f"[Stability Test] TCP keep-alive should prevent connection timeout")

        for i in range(10):
            correlation_id = random.choice(CORRELATION_IDS)
            call_id = f"stability_{i}"
            event = server.generate_trace_event("call", call_id, correlation_id, 0)

            if not server.send_event(event):
                print(f"[Stability Test] Connection lost at event {i}")
                break

            print(f"[Stability Test] Sent event {i + 1}/10")

            # Long pause to test keep-alive
            print(f"[Stability Test] Waiting 5 seconds (testing keep-alive)...")
            time.sleep(5)

        print(f"\n[Stability Test] Connection should still be alive")
        print(f"[Stability Test] TCP keep-alive prevented timeout")

    except KeyboardInterrupt:
        print("\n[Stability Test] Interrupted by user")
    finally:
        server.stop()


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("PYCHARM PLUGIN END-TO-END TESTS")
    print("="*80)
    print(f"\nBefore running tests:")
    print(f"1. Open PyCharm with the crawl4ai project")
    print(f"2. Open the Learning Flow Visualizer tool window")
    print(f"3. Click 'Attach to Server' and enter: {TRACE_SERVER_HOST}:{TRACE_SERVER_PORT}")
    print(f"4. Wait for 'Connected' status")
    print(f"5. Run this script\n")

    input("Press ENTER when plugin is connected and ready...")

    # Test 1: Normal operation
    print("\n" + "="*80)
    print("TEST 1: Normal Operation")
    print("="*80)

    server = MockTraceServer()
    if server.start():
        try:
            server.send_test_sequence()

            # Keep server alive for inspection
            print(f"\n[Test] Keeping server alive for 30 seconds for inspection...")
            time.sleep(30)

        except KeyboardInterrupt:
            print("\n[Test] Interrupted by user")
        finally:
            server.stop()

    # Ask user if they want to run additional tests
    print("\n" + "="*80)
    choice = input("\nRun stress test? (y/n): ").lower()
    if choice == 'y':
        run_stress_test()

    choice = input("\nRun video detection test? (y/n): ").lower()
    if choice == 'y':
        run_video_detection_test()

    choice = input("\nRun connection stability test? (y/n): ").lower()
    if choice == 'y':
        run_connection_stability_test()

    print("\n" + "="*80)
    print("ALL TESTS COMPLETED")
    print("="*80)
    print("\nVerify in PyCharm plugin:")
    print("1. Diagram tab: Shows PlantUML with participants")
    print("2. Performance tab: Shows function call statistics")
    print("3. Dead Code tab: Shows called functions")
    print("4. Statistics panel: Shows total calls, avg time, etc.")
    print("5. No memory leaks (check plugin memory in Task Manager)")
    print("6. No connection drops (check status says 'Connected')")
    print("\nCheck logs at: .pycharm_plugin/logs/plugin_*.log")


if __name__ == "__main__":
    main()
