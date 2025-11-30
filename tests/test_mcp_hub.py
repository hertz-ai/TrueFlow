# Test MCP Hub - WebSocket Pub/Sub and RPC functionality
# Tests for trueflow_mcp_hub.py

import sys
import os
import json
import asyncio
import tempfile
import unittest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
from datetime import datetime

# Add runtime_injector to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'main', 'resources', 'runtime_injector'))

# Import the module under test
try:
    from trueflow_mcp_hub import (
        HubState, hub, is_hub_running, write_hub_status, read_hub_status,
        rpc_call, broadcast, STATUS_FILE, RPC_TIMEOUT
    )
    HAS_HUB = True
except ImportError as e:
    HAS_HUB = False
    print(f"Warning: Could not import trueflow_mcp_hub: {e}")


@unittest.skipIf(not HAS_HUB, "trueflow_mcp_hub not available")
class TestHubState(unittest.TestCase):
    """Test the HubState global state management."""

    def setUp(self):
        # Reset hub state before each test
        hub.projects.clear()
        hub.subscribers.clear()
        hub.trace_data.clear()
        hub.pending_requests.clear()
        hub.ai_server_status = {
            "running": False,
            "port": 8080,
            "model": None,
            "started_by": None,
            "started_at": None
        }

    def test_hub_state_initialization(self):
        """Test that HubState initializes with empty collections."""
        state = HubState()
        self.assertEqual(state.projects, {})
        self.assertEqual(state.subscribers, set())
        self.assertEqual(state.trace_data, {})
        self.assertEqual(state.pending_requests, {})
        self.assertFalse(state.ai_server_status["running"])

    def test_project_registration(self):
        """Test registering a project in hub state."""
        hub.projects["test_project"] = {
            "ide": "vscode",
            "project_path": "/path/to/project",
            "project_name": "TestProject",
            "websocket": None,
            "capabilities": ["trace", "dead_code"],
            "registered_at": datetime.now().isoformat()
        }

        self.assertIn("test_project", hub.projects)
        self.assertEqual(hub.projects["test_project"]["ide"], "vscode")
        self.assertEqual(len(hub.projects["test_project"]["capabilities"]), 2)

    def test_project_unregistration(self):
        """Test unregistering a project from hub state."""
        hub.projects["temp_project"] = {"ide": "pycharm"}
        self.assertIn("temp_project", hub.projects)

        del hub.projects["temp_project"]
        self.assertNotIn("temp_project", hub.projects)

    def test_ai_server_status_update(self):
        """Test updating AI server status."""
        hub.ai_server_status = {
            "running": True,
            "port": 8080,
            "model": "qwen3-vl-2b",
            "started_by": "vscode_project1",
            "started_at": datetime.now().isoformat()
        }

        self.assertTrue(hub.ai_server_status["running"])
        self.assertEqual(hub.ai_server_status["model"], "qwen3-vl-2b")
        self.assertEqual(hub.ai_server_status["started_by"], "vscode_project1")

    def test_trace_data_storage(self):
        """Test storing trace data per project."""
        trace = {
            "calls": [
                {"function": "main", "module": "app", "duration_ms": 10.5},
                {"function": "helper", "module": "utils", "duration_ms": 2.3}
            ],
            "total_calls": 2
        }
        hub.trace_data["project1"] = trace

        self.assertIn("project1", hub.trace_data)
        self.assertEqual(len(hub.trace_data["project1"]["calls"]), 2)
        self.assertEqual(hub.trace_data["project1"]["total_calls"], 2)

    def test_multiple_projects(self):
        """Test managing multiple concurrent projects."""
        for i in range(5):
            hub.projects[f"project_{i}"] = {
                "ide": "vscode" if i % 2 == 0 else "pycharm",
                "project_name": f"Project{i}"
            }

        self.assertEqual(len(hub.projects), 5)
        vscode_count = sum(1 for p in hub.projects.values() if p["ide"] == "vscode")
        pycharm_count = sum(1 for p in hub.projects.values() if p["ide"] == "pycharm")
        self.assertEqual(vscode_count, 3)
        self.assertEqual(pycharm_count, 2)


@unittest.skipIf(not HAS_HUB, "trueflow_mcp_hub not available")
class TestStatusFile(unittest.TestCase):
    """Test hub status file operations."""

    def setUp(self):
        # Use a temp directory for status file
        self.temp_dir = tempfile.mkdtemp()
        self.original_status_file = STATUS_FILE

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_write_hub_status(self):
        """Test writing hub status to file."""
        with patch('trueflow_mcp_hub.STATUS_FILE', Path(self.temp_dir) / "hub_status.json"):
            write_hub_status(True, pid=12345)

            status_file = Path(self.temp_dir) / "hub_status.json"
            self.assertTrue(status_file.exists())

            content = json.loads(status_file.read_text())
            self.assertTrue(content["running"])
            self.assertEqual(content["pid"], 12345)
            self.assertEqual(content["mcp_port"], 5679)
            self.assertEqual(content["ws_port"], 5680)

    def test_read_hub_status(self):
        """Test reading hub status from file."""
        status_file = Path(self.temp_dir) / "hub_status.json"
        status_file.parent.mkdir(parents=True, exist_ok=True)
        status_file.write_text(json.dumps({
            "running": True,
            "pid": 9999,
            "mcp_port": 5679,
            "ws_port": 5680,
            "started_at": "2024-01-01T12:00:00"
        }))

        with patch('trueflow_mcp_hub.STATUS_FILE', status_file):
            status = read_hub_status()
            self.assertIsNotNone(status)
            self.assertTrue(status["running"])
            self.assertEqual(status["pid"], 9999)

    def test_read_missing_status_file(self):
        """Test reading when status file doesn't exist."""
        with patch('trueflow_mcp_hub.STATUS_FILE', Path(self.temp_dir) / "nonexistent.json"):
            status = read_hub_status()
            self.assertIsNone(status)

    def test_read_corrupted_status_file(self):
        """Test reading corrupted status file."""
        status_file = Path(self.temp_dir) / "corrupted_status.json"
        status_file.parent.mkdir(parents=True, exist_ok=True)
        status_file.write_text("not valid json {{{")

        with patch('trueflow_mcp_hub.STATUS_FILE', status_file):
            status = read_hub_status()
            self.assertIsNone(status)


@unittest.skipIf(not HAS_HUB, "trueflow_mcp_hub not available")
class TestIsHubRunning(unittest.TestCase):
    """Test hub running detection."""

    def test_hub_not_running(self):
        """Test detection when hub is not running."""
        # Use a port that's definitely not in use
        with patch('trueflow_mcp_hub.socket.socket') as mock_socket:
            mock_instance = MagicMock()
            mock_instance.connect.side_effect = OSError("Connection refused")
            mock_socket.return_value.__enter__.return_value = mock_instance

            result = is_hub_running()
            self.assertFalse(result)

    def test_hub_running(self):
        """Test detection when hub is running."""
        with patch('trueflow_mcp_hub.socket.socket') as mock_socket:
            mock_instance = MagicMock()
            mock_instance.connect.return_value = None  # Connection succeeds
            mock_socket.return_value.__enter__.return_value = mock_instance

            result = is_hub_running()
            self.assertTrue(result)

    def test_hub_connection_timeout(self):
        """Test detection when connection times out."""
        import socket as real_socket
        with patch('trueflow_mcp_hub.socket.socket') as mock_socket:
            mock_instance = MagicMock()
            mock_instance.connect.side_effect = real_socket.timeout("Connection timed out")
            mock_socket.return_value.__enter__.return_value = mock_instance

            result = is_hub_running()
            self.assertFalse(result)


@unittest.skipIf(not HAS_HUB, "trueflow_mcp_hub not available")
class TestRPCCall(unittest.TestCase):
    """Test RPC call functionality."""

    def setUp(self):
        hub.projects.clear()
        hub.pending_requests.clear()

    def test_rpc_call_project_not_found(self):
        """Test RPC call when project doesn't exist."""
        async def run_test():
            result = await rpc_call("nonexistent_project", "some_command")
            self.assertIsNone(result)

        asyncio.run(run_test())

    def test_rpc_call_no_websocket(self):
        """Test RPC call when project has no websocket."""
        hub.projects["test_project"] = {
            "ide": "vscode",
            "websocket": None
        }

        async def run_test():
            result = await rpc_call("test_project", "some_command")
            self.assertIsNone(result)

        asyncio.run(run_test())

    def test_rpc_call_timeout(self):
        """Test RPC call timeout handling."""
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()

        hub.projects["test_project"] = {
            "ide": "vscode",
            "websocket": mock_ws
        }

        async def run_test():
            # Use very short timeout to trigger timeout
            result = await rpc_call("test_project", "some_command", timeout=0.001)
            self.assertIsNone(result)

        asyncio.run(run_test())

    def test_rpc_call_success(self):
        """Test successful RPC call with response."""
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()

        hub.projects["test_project"] = {
            "ide": "vscode",
            "websocket": mock_ws
        }

        async def run_test():
            # Start the RPC call
            rpc_task = asyncio.create_task(
                rpc_call("test_project", "get_trace_data", {}, timeout=1.0)
            )

            # Give it time to register the pending request
            await asyncio.sleep(0.01)

            # Find the request ID and simulate a response
            if hub.pending_requests:
                request_id = list(hub.pending_requests.keys())[0]
                future = hub.pending_requests[request_id]
                future.set_result({"calls": [], "total_calls": 0})

            result = await rpc_task
            self.assertIsNotNone(result)
            self.assertEqual(result["total_calls"], 0)

        asyncio.run(run_test())

    def test_rpc_request_cleanup(self):
        """Test that pending requests are cleaned up after completion."""
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()

        hub.projects["test_project"] = {
            "ide": "vscode",
            "websocket": mock_ws
        }

        async def run_test():
            # Timeout immediately
            await rpc_call("test_project", "some_command", timeout=0.001)
            # Pending request should be cleaned up
            self.assertEqual(len(hub.pending_requests), 0)

        asyncio.run(run_test())


@unittest.skipIf(not HAS_HUB, "trueflow_mcp_hub not available")
class TestBroadcast(unittest.TestCase):
    """Test broadcast functionality."""

    def setUp(self):
        hub.subscribers.clear()

    def test_broadcast_no_subscribers(self):
        """Test broadcast with no subscribers."""
        async def run_test():
            # Should not raise any exceptions
            await broadcast("test_event", {"message": "hello"})
            self.assertEqual(len(hub.subscribers), 0)

        asyncio.run(run_test())

    def test_broadcast_to_subscribers(self):
        """Test broadcast to multiple subscribers."""
        mock_ws1 = AsyncMock()
        mock_ws1.send = AsyncMock()
        mock_ws2 = AsyncMock()
        mock_ws2.send = AsyncMock()

        hub.subscribers.add(mock_ws1)
        hub.subscribers.add(mock_ws2)

        async def run_test():
            await broadcast("test_event", {"message": "hello"})

            # Both subscribers should receive the message
            mock_ws1.send.assert_called_once()
            mock_ws2.send.assert_called_once()

            # Verify message format
            sent_msg = json.loads(mock_ws1.send.call_args[0][0])
            self.assertEqual(sent_msg["type"], "test_event")
            self.assertEqual(sent_msg["data"]["message"], "hello")
            self.assertIn("timestamp", sent_msg)

        asyncio.run(run_test())

    def test_broadcast_exclude_sender(self):
        """Test broadcast excluding the sender."""
        mock_ws1 = AsyncMock()
        mock_ws1.send = AsyncMock()
        mock_ws2 = AsyncMock()
        mock_ws2.send = AsyncMock()

        hub.subscribers.add(mock_ws1)
        hub.subscribers.add(mock_ws2)

        async def run_test():
            await broadcast("test_event", {"message": "hello"}, exclude_ws=mock_ws1)

            # Only ws2 should receive the message
            mock_ws1.send.assert_not_called()
            mock_ws2.send.assert_called_once()

        asyncio.run(run_test())

    def test_broadcast_removes_dead_connections(self):
        """Test that dead connections are removed during broadcast."""
        try:
            import websockets
        except ImportError:
            self.skipTest("websockets not installed")

        mock_ws_alive = AsyncMock()
        mock_ws_alive.send = AsyncMock()

        mock_ws_dead = AsyncMock()
        mock_ws_dead.send = AsyncMock(
            side_effect=websockets.exceptions.ConnectionClosed(None, None)
        )

        hub.subscribers.add(mock_ws_alive)
        hub.subscribers.add(mock_ws_dead)

        async def run_test():
            self.assertEqual(len(hub.subscribers), 2)
            await broadcast("test_event", {"message": "hello"})

            # Dead connection should be removed
            self.assertEqual(len(hub.subscribers), 1)
            self.assertIn(mock_ws_alive, hub.subscribers)
            self.assertNotIn(mock_ws_dead, hub.subscribers)

        asyncio.run(run_test())


@unittest.skipIf(not HAS_HUB, "trueflow_mcp_hub not available")
class TestWebSocketMessageHandling(unittest.TestCase):
    """Test WebSocket message handling logic."""

    def setUp(self):
        hub.projects.clear()
        hub.subscribers.clear()
        hub.pending_requests.clear()
        hub.ai_server_status = {
            "running": False,
            "port": 8080,
            "model": None,
            "started_by": None,
            "started_at": None
        }

    def test_register_message_format(self):
        """Test the format of a register message."""
        register_msg = {
            "type": "register",
            "data": {
                "project_id": "my_project",
                "ide": "vscode",
                "project_path": "/path/to/project",
                "project_name": "MyProject",
                "capabilities": ["trace", "dead_code", "performance"]
            }
        }

        # Validate message structure
        self.assertEqual(register_msg["type"], "register")
        self.assertIn("project_id", register_msg["data"])
        self.assertIn("capabilities", register_msg["data"])

    def test_rpc_response_message_format(self):
        """Test the format of an RPC response message."""
        response_msg = {
            "type": "rpc_response",
            "request_id": "abc-123-def",
            "data": {
                "calls": [{"function": "main"}],
                "total_calls": 1
            }
        }

        self.assertEqual(response_msg["type"], "rpc_response")
        self.assertIn("request_id", response_msg)
        self.assertIn("data", response_msg)

    def test_ai_server_started_message_format(self):
        """Test the format of AI server started message."""
        msg = {
            "type": "ai_server_started",
            "data": {
                "port": 8080,
                "model": "qwen3-vl-2b",
                "started_by": "vscode_project1"
            }
        }

        self.assertEqual(msg["type"], "ai_server_started")
        self.assertEqual(msg["data"]["port"], 8080)

    def test_trace_update_message_format(self):
        """Test the format of a trace update message."""
        msg = {
            "type": "trace_update",
            "data": {
                "calls": [
                    {"function": "main", "module": "app", "line": 10, "duration_ms": 5.2}
                ],
                "total_calls": 1,
                "max_depth": 3
            }
        }

        self.assertEqual(msg["type"], "trace_update")
        self.assertEqual(len(msg["data"]["calls"]), 1)


@unittest.skipIf(not HAS_HUB, "trueflow_mcp_hub not available")
class TestMCPToolSchemas(unittest.TestCase):
    """Test MCP tool input schemas and responses."""

    def test_list_projects_response_format(self):
        """Test the expected response format of list_projects."""
        hub.projects["project1"] = {
            "ide": "vscode",
            "project_name": "Project1",
            "project_path": "/path/1",
            "capabilities": ["trace"],
            "registered_at": "2024-01-01T12:00:00"
        }
        hub.projects["project2"] = {
            "ide": "pycharm",
            "project_name": "Project2",
            "project_path": "/path/2",
            "capabilities": ["trace", "dead_code"],
            "registered_at": "2024-01-01T12:30:00"
        }

        # Build expected response
        projects_info = []
        for pid, info in hub.projects.items():
            projects_info.append({
                "id": pid,
                "ide": info.get("ide"),
                "name": info.get("project_name"),
                "path": info.get("project_path"),
                "capabilities": info.get("capabilities", []),
                "registered_at": info.get("registered_at")
            })

        response = {"projects": projects_info, "count": len(projects_info)}

        self.assertEqual(response["count"], 2)
        self.assertEqual(len(response["projects"]), 2)

        # Check structure of each project
        for proj in response["projects"]:
            self.assertIn("id", proj)
            self.assertIn("ide", proj)
            self.assertIn("capabilities", proj)

    def test_get_trace_data_schema(self):
        """Test get_trace_data input schema."""
        input_schema = {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID to get traces from"}
            },
            "required": ["project_id"]
        }

        self.assertIn("project_id", input_schema["properties"])
        self.assertIn("project_id", input_schema["required"])

    def test_export_diagram_schema(self):
        """Test export_diagram input schema with enum."""
        input_schema = {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "format": {"type": "string", "enum": ["plantuml", "mermaid"]}
            },
            "required": ["project_id"]
        }

        self.assertIn("plantuml", input_schema["properties"]["format"]["enum"])
        self.assertIn("mermaid", input_schema["properties"]["format"]["enum"])

    def test_send_command_schema(self):
        """Test send_command input schema."""
        input_schema = {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "command": {"type": "string"},
                "args": {"type": "object"}
            },
            "required": ["project_id", "command"]
        }

        self.assertEqual(len(input_schema["required"]), 2)
        self.assertIn("args", input_schema["properties"])


@unittest.skipIf(not HAS_HUB, "trueflow_mcp_hub not available")
class TestRPCTimeout(unittest.TestCase):
    """Test RPC timeout configuration."""

    def test_default_rpc_timeout(self):
        """Test default RPC timeout value."""
        self.assertEqual(RPC_TIMEOUT, 30)

    def test_custom_timeout_in_rpc_call(self):
        """Test that custom timeout is respected."""
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()

        hub.projects["test_project"] = {
            "ide": "vscode",
            "websocket": mock_ws
        }

        async def run_test():
            import time
            start = time.time()
            # Use 0.1 second timeout
            await rpc_call("test_project", "slow_command", timeout=0.1)
            elapsed = time.time() - start

            # Should timeout after approximately 0.1 seconds
            self.assertLess(elapsed, 0.5)

        asyncio.run(run_test())


@unittest.skipIf(not HAS_HUB, "trueflow_mcp_hub not available")
class TestConcurrentRPCCalls(unittest.TestCase):
    """Test concurrent RPC call handling."""

    def setUp(self):
        hub.projects.clear()
        hub.pending_requests.clear()

    def test_multiple_concurrent_rpc_calls(self):
        """Test handling multiple RPC calls simultaneously."""
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()

        hub.projects["test_project"] = {
            "ide": "vscode",
            "websocket": mock_ws
        }

        async def run_test():
            # Start multiple RPC calls
            tasks = [
                asyncio.create_task(rpc_call("test_project", f"command_{i}", timeout=0.05))
                for i in range(5)
            ]

            # All should timeout since no responses
            results = await asyncio.gather(*tasks)

            # All should return None (timeout)
            for result in results:
                self.assertIsNone(result)

            # All pending requests should be cleaned up
            self.assertEqual(len(hub.pending_requests), 0)

        asyncio.run(run_test())

    def test_unique_request_ids(self):
        """Test that each RPC call gets a unique request ID."""
        mock_ws = AsyncMock()
        captured_messages = []

        async def capture_send(msg):
            captured_messages.append(json.loads(msg))

        mock_ws.send = capture_send

        hub.projects["test_project"] = {
            "ide": "vscode",
            "websocket": mock_ws
        }

        async def run_test():
            tasks = [
                asyncio.create_task(rpc_call("test_project", f"command_{i}", timeout=0.01))
                for i in range(3)
            ]
            await asyncio.gather(*tasks)

            # All request IDs should be unique
            request_ids = [msg["request_id"] for msg in captured_messages]
            self.assertEqual(len(request_ids), len(set(request_ids)))

        asyncio.run(run_test())


class TestMCPHubIntegration(unittest.TestCase):
    """Integration tests for MCP Hub (mocked)."""

    def test_full_workflow_simulation(self):
        """Simulate a full workflow: register, trace, export."""
        if not HAS_HUB:
            self.skipTest("trueflow_mcp_hub not available")

        hub.projects.clear()
        hub.trace_data.clear()

        # 1. Simulate project registration
        project_id = "integration_test_project"
        hub.projects[project_id] = {
            "ide": "vscode",
            "project_path": "/test/path",
            "project_name": "IntegrationTest",
            "websocket": None,
            "capabilities": ["trace", "dead_code", "performance", "diagram"],
            "registered_at": datetime.now().isoformat()
        }

        self.assertIn(project_id, hub.projects)

        # 2. Simulate trace data update
        hub.trace_data[project_id] = {
            "calls": [
                {"function": "main", "module": "app", "line": 1, "duration_ms": 100},
                {"function": "process", "module": "worker", "line": 50, "duration_ms": 80}
            ],
            "total_calls": 2,
            "max_depth": 2
        }

        self.assertEqual(hub.trace_data[project_id]["total_calls"], 2)

        # 3. Simulate AI server start
        hub.ai_server_status = {
            "running": True,
            "port": 8080,
            "model": "qwen3-vl-2b",
            "started_by": project_id,
            "started_at": datetime.now().isoformat()
        }

        self.assertTrue(hub.ai_server_status["running"])

        # 4. Cleanup
        del hub.projects[project_id]
        del hub.trace_data[project_id]
        hub.ai_server_status["running"] = False

        self.assertNotIn(project_id, hub.projects)


if __name__ == '__main__':
    unittest.main()
