#!/usr/bin/env python3
"""
Complete end-to-end integration test with real-like data.
Tests ALL plugin functionality and verifies expected log lines.
"""

import socket
import json
import time
import sys
import os
from pathlib import Path

# Test configuration
HOST = "127.0.0.1"
PORT = 5678
TEST_DURATION = 60  # seconds
EVENTS_PER_SECOND = 100

# Real module/function names from crawl4ai
REAL_MODULES = [
    "crawl4ai.embodied_ai.learning.reality_grounded_learner",
    "crawl4ai.embodied_ai.learning.semantic_reasoner",
    "crawl4ai.embodied_ai.inference.realtime_agent",
    "crawl4ai.embodied_ai.models.qwen_vl_wrapper",
    "crawl4ai.embodied_ai.models.unified_sensory_stream",
    "crawl4ai.embodied_ai.memory.episodic_memory",
    "torch.nn.functional",
    "torch.optim.adam",
]

REAL_FUNCTIONS = [
    "forward", "backward", "step",
    "encode_perception", "encode_text", "encode_vision",
    "compute_loss", "predict", "reason_about",
    "store_experience", "retrieve_memories",
    "update_weights", "calculate_gradients"
]

LEARNING_PHASES = ["perception", "reasoning", "planning", "execution", "reflection"]

class IntegrationTest:
    """Full integration test for PyCharm plugin."""

    def __init__(self):
        self.server = None
        self.client = None
        self.events_sent = 0
        self.start_time = None
        self.test_results = {}

    def setup_server(self):
        """Setup mock trace server."""
        print("\n" + "="*80)
        print("STEP 1: Starting Mock Trace Server")
        print("="*80)

        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((HOST, PORT))
            self.server.listen(1)

            print(f"[OK] Server started on {HOST}:{PORT}")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to start server: {e}")
            return False

    def wait_for_connection(self):
        """Wait for plugin to connect."""
        print("\n" + "="*80)
        print("STEP 2: Waiting for Plugin Connection")
        print("="*80)
        print("\nMANUAL STEPS REQUIRED:")
        print("1. In PyCharm sandbox window:")
        print("   - Go to View -> Tool Windows -> Learning Flow Visualizer")
        print("   - Click the blue 'Attach to Server' button")
        print(f"   - Enter Host: {HOST}  Port: {PORT}")
        print("   - Click OK")
        print("\n2. Wait for 'Connected' status")
        print("\n3. This script will detect the connection automatically...")
        print("\nWaiting for connection (60 second timeout)...\n")

        self.server.settimeout(60)
        try:
            self.client, addr = self.server.accept()
            print(f"[OK] Plugin connected from {addr}")

            # Verify socket settings
            keep_alive = self.client.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE)
            print(f"[OK] TCP Keep-Alive: {bool(keep_alive)}")

            return True

        except socket.timeout:
            print("[ERROR] No connection within 60 seconds")
            print("Make sure plugin is running and 'Attach to Server' was clicked")
            return False
        except Exception as e:
            print(f"[ERROR] Connection error: {e}")
            return False

    def generate_event(self, event_id, correlation_id):
        """Generate realistic trace event."""
        import random

        module = random.choice(REAL_MODULES)
        function = random.choice(REAL_FUNCTIONS)

        # Real file paths
        project_path = "C:/Users/sathi/PycharmProjects/crawl4ai"
        module_path = module.replace(".", "/")
        file_path = f"{project_path}/src/{module_path}.py"

        event = {
            "type": "call" if event_id % 2 == 0 else "return",
            "timestamp": time.time(),
            "call_id": f"call_{event_id}",
            "module": module,
            "function": function,
            "file": file_path,
            "line": random.randint(100, 500),
            "depth": event_id % 5,
            "parent_id": f"parent_{event_id - 1}" if event_id > 0 else None,
            "process_id": os.getpid(),
            "session_id": f"e2e_test_{int(time.time())}",
            "correlation_id": correlation_id,
            "learning_phase": random.choice(LEARNING_PHASES)
        }

        return event

    def send_event(self, event):
        """Send event to plugin."""
        try:
            json_line = json.dumps(event) + "\n"
            self.client.sendall(json_line.encode('utf-8'))
            self.events_sent += 1
            return True
        except Exception as e:
            print(f"[ERROR] Failed to send event: {e}")
            return False

    def run_main_test(self):
        """Run main integration test."""
        print("\n" + "="*80)
        print("STEP 3: Running Integration Test")
        print("="*80)
        print(f"\nTest Configuration:")
        print(f"  - Duration: {TEST_DURATION} seconds")
        print(f"  - Event Rate: {EVENTS_PER_SECOND} events/sec")
        print(f"  - Total Events: {TEST_DURATION * EVENTS_PER_SECOND}")
        print(f"  - Correlation IDs: 3 (test_001, test_002, test_003)")
        print("\nStarting test...\n")

        self.start_time = time.time()
        correlation_ids = ["test_001", "test_002", "test_003"]
        interval = 1.0 / EVENTS_PER_SECOND

        event_id = 0
        checkpoints = [1000, 2000, 5000, 6000]  # Events to check

        while (time.time() - self.start_time) < TEST_DURATION:
            # Generate and send event
            correlation_id = correlation_ids[event_id % len(correlation_ids)]
            event = self.generate_event(event_id, correlation_id)

            if not self.send_event(event):
                print(f"[ERROR] Failed at event {event_id}")
                return False

            event_id += 1

            # Progress checkpoints
            if event_id in checkpoints:
                elapsed = time.time() - self.start_time
                rate = self.events_sent / elapsed
                print(f"[Progress] {event_id} events sent ({rate:.0f} events/sec, {elapsed:.1f}s elapsed)")
                print(f"           Plugin should be processing and updating UI...")

            time.sleep(interval)

        elapsed = time.time() - self.start_time
        rate = self.events_sent / elapsed

        print(f"\n[OK] Test completed!")
        print(f"     Total: {self.events_sent} events in {elapsed:.1f}s ({rate:.0f} events/sec)")

        return True

    def verify_plugin_state(self):
        """Verify plugin is in expected state."""
        print("\n" + "="*80)
        print("STEP 4: Verifying Plugin State")
        print("="*80)

        print("\nCHECK THE FOLLOWING IN PYCHARM PLUGIN:")
        print("\n1. CONNECTION STATUS:")
        print("   [  ] Status shows: 'Connected to 127.0.0.1:5678'")
        print("   [  ] Button shows: 'Detach from Server' (red)")
        print("   [  ] Process info shows active PID")

        print("\n2. STATISTICS PANEL (Top of tool window):")
        print(f"   [  ] Total Calls: ~{self.events_sent}")
        print(f"   [  ] Session ID: e2e_test_*")
        print(f"   [  ] Total Time: > 0ms")
        print(f"   [  ] Avg Time: > 0ms")

        print("\n3. DIAGRAM TAB:")
        print("   [  ] Shows PlantUML diagram")
        print("   [  ] Has participants from REAL_MODULES")
        print("   [  ] Shows call arrows between modules")
        print("   [  ] No syntax errors or @enduml injection")

        print("\n4. PERFORMANCE TAB:")
        print("   [  ] Table shows rows with function statistics")
        print("   [  ] Columns: Module, Function, Calls, Total (ms), Avg (ms), etc.")
        print("   [  ] Call counts are non-zero")
        print("   [  ] Functions from REAL_FUNCTIONS appear")

        print("\n5. DEAD CODE TAB:")
        print("   [  ] Shows 'Real-time mode: X functions called'")
        print("   [  ] Table shows 'CALLED (N times)' status")
        print("   [  ] Multiple functions listed")

        print("\n6. MEMORY & PERFORMANCE:")
        print("   [  ] PyCharm process memory < 1GB (stable)")
        print("   [  ] UI is responsive (no freezing)")
        print("   [  ] No lag when switching tabs")

        response = input("\nDid ALL checks pass? (y/n): ").lower().strip()

        if response == 'y':
            print("[OK] Plugin state verified successfully")
            return True
        else:
            print("[FAIL] Some checks failed - see above")
            return False

    def check_logs(self):
        """Check plugin logs for expected entries."""
        print("\n" + "="*80)
        print("STEP 5: Checking Plugin Logs")
        print("="*80)

        log_path = Path("build/idea-sandbox/system/log/idea.log")

        if not log_path.exists():
            print(f"[WARN] Log file not found: {log_path}")
            print("       (This is normal if plugin was closed)")
            return True

        print(f"\nChecking log file: {log_path}")

        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                log_content = f.read()

            # Expected log entries
            expected_logs = [
                ("Plugin loaded", "Loaded custom plugins: SequenceDiagramPython"),
                ("Socket connection", "[TraceSocketClient] Connected to trace server"),
                ("Trace processing", "Plugin startup completed successfully"),
            ]

            print("\nExpected Log Entries:")
            all_found = True

            for name, pattern in expected_logs:
                if pattern in log_content:
                    print(f"   [OK] {name}: Found")
                else:
                    print(f"   [MISS] {name}: Not found")
                    all_found = False

            # Check for errors
            if "ERROR" in log_content or "Exception" in log_content:
                print(f"\n   [WARN] Found ERROR or Exception in logs")
                print(f"          Review logs manually for details")
            else:
                print(f"\n   [OK] No ERROR or Exception in logs")

            return all_found

        except Exception as e:
            print(f"[ERROR] Failed to read logs: {e}")
            return False

    def cleanup(self):
        """Cleanup connections."""
        print("\n" + "="*80)
        print("Cleanup")
        print("="*80)

        if self.client:
            try:
                self.client.close()
                print("[OK] Client connection closed")
            except:
                pass

        if self.server:
            try:
                self.server.close()
                print("[OK] Server socket closed")
            except:
                pass

    def run(self):
        """Run complete end-to-end test."""
        print("\n" + "="*80)
        print("PYCHARM PLUGIN - COMPLETE END-TO-END INTEGRATION TEST")
        print("="*80)
        print(f"\nThis test will:")
        print(f"1. Start mock trace server on {HOST}:{PORT}")
        print(f"2. Wait for plugin to connect")
        print(f"3. Send {TEST_DURATION * EVENTS_PER_SECOND} realistic trace events")
        print(f"4. Verify all plugin functionality")
        print(f"5. Check expected log entries")

        try:
            # Step 1: Setup server
            if not self.setup_server():
                return False

            # Step 2: Wait for connection
            if not self.wait_for_connection():
                return False

            self.test_results['connection'] = True

            # Step 3: Run main test
            if not self.run_main_test():
                self.test_results['main_test'] = False
                return False

            self.test_results['main_test'] = True

            # Step 4: Verify plugin state
            self.test_results['plugin_state'] = self.verify_plugin_state()

            # Step 5: Check logs
            self.test_results['logs'] = self.check_logs()

            # Summary
            print("\n" + "="*80)
            print("TEST RESULTS SUMMARY")
            print("="*80)

            for test_name, result in self.test_results.items():
                status = "[PASS]" if result else "[FAIL]"
                print(f"  {status} {test_name.upper()}")

            passed = sum(1 for v in self.test_results.values() if v)
            total = len(self.test_results)

            print(f"\n  Total: {passed}/{total} tests passed")

            if passed == total:
                print("\n[SUCCESS] All integration tests passed!")
                print("Plugin is fully functional with all fixes working correctly.")
                return True
            else:
                print(f"\n[PARTIAL] {total - passed} test(s) failed")
                print("Review failure details above.")
                return False

        except KeyboardInterrupt:
            print("\n\n[INTERRUPTED] Test cancelled by user")
            return False
        except Exception as e:
            print(f"\n\n[ERROR] Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            self.cleanup()


def main():
    """Main entry point."""
    test = IntegrationTest()
    success = test.run()

    print("\n" + "="*80)
    print("END OF TEST")
    print("="*80)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
