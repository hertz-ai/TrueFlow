#!/usr/bin/env python3
"""
TrueFlow MCP Hub - Unified MCP Server with WebSocket Pub/Sub + RPC

This is a SINGLE MCP server instance that:
1. Acts as an MCP server for Claude Code / AI agents
2. Provides WebSocket pub/sub for real-time IDE coordination
3. Maintains a registry of connected IDE instances (projects)
4. Routes MCP tool calls to the correct IDE/project with RPC response waiting

Architecture:
- Single instance runs on port 5679 (MCP) + 5680 (WebSocket)
- First IDE to start launches the hub
- All IDEs connect as clients to the hub
- AI agents connect via MCP protocol
- MCP calls wait for IDE responses (true RPC)

Usage:
    # First instance (from any IDE) starts the hub
    python trueflow_mcp_hub.py --start

    # Other IDEs connect as clients
    python trueflow_mcp_hub.py --connect --project "MyProject" --ide "vscode"
"""

import asyncio
import json
import sys
import os
import uuid
import socket
from datetime import datetime
from pathlib import Path
from typing import Dict, Set, Optional, Any
import logging

# MCP SDK imports
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    print("Warning: MCP SDK not installed. Run: pip install mcp", file=sys.stderr)

# WebSocket imports
try:
    import websockets
    from websockets.server import serve as ws_serve
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False
    print("Warning: websockets not installed. Run: pip install websockets", file=sys.stderr)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global state
class HubState:
    # Connected IDE instances: {project_id: {ide, project_path, websocket, capabilities}}
    projects: Dict[str, Dict] = {}

    # WebSocket connections for pub/sub
    subscribers: Set = set()

    # AI server status (shared across all IDEs)
    ai_server_status: Dict = {
        "running": False,
        "port": 8080,
        "model": None,
        "started_by": None,
        "started_at": None
    }

    # Trace data by project
    trace_data: Dict[str, Dict] = {}

    # Pending RPC requests: {request_id: asyncio.Future}
    pending_requests: Dict[str, asyncio.Future] = {}

hub = HubState()

# RPC timeout in seconds
RPC_TIMEOUT = 30

# Status file for cross-process coordination
STATUS_FILE = Path.home() / ".trueflow" / "hub_status.json"
LOCK_FILE = Path.home() / ".trueflow" / "hub.lock"

def is_hub_running() -> bool:
    """Check if hub is already running by trying to connect to its port."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect(("127.0.0.1", 5680))
            return True
    except (socket.error, socket.timeout):
        return False

def write_hub_status(running: bool, pid: int = None):
    """Write hub status to shared file."""
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    status = {
        "running": running,
        "pid": pid or os.getpid(),
        "mcp_port": 5679,
        "ws_port": 5680,
        "started_at": datetime.now().isoformat()
    }
    STATUS_FILE.write_text(json.dumps(status, indent=2))

def read_hub_status() -> Optional[Dict]:
    """Read hub status from shared file."""
    try:
        if STATUS_FILE.exists():
            return json.loads(STATUS_FILE.read_text())
    except Exception:
        pass
    return None

# ==================== RPC Helpers ====================

async def rpc_call(project_id: str, command: str, args: dict = None, timeout: float = RPC_TIMEOUT) -> Optional[Dict]:
    """
    Send RPC request to a project and wait for response.
    Returns the response data or None on timeout/error.
    """
    if project_id not in hub.projects:
        return None

    ws = hub.projects[project_id].get("websocket")
    if not ws:
        return None

    # Generate unique request ID
    request_id = str(uuid.uuid4())

    # Create future to wait for response
    future = asyncio.get_event_loop().create_future()
    hub.pending_requests[request_id] = future

    try:
        # Send request with ID
        await ws.send(json.dumps({
            "type": "rpc_request",
            "request_id": request_id,
            "command": command,
            "args": args or {}
        }))

        logger.info(f"RPC request {request_id} sent to {project_id}: {command}")

        # Wait for response with timeout
        response = await asyncio.wait_for(future, timeout=timeout)
        logger.info(f"RPC response {request_id} received from {project_id}")
        return response

    except asyncio.TimeoutError:
        logger.warning(f"RPC request {request_id} to {project_id} timed out")
        return None
    except Exception as e:
        logger.error(f"RPC request {request_id} failed: {e}")
        return None
    finally:
        # Clean up pending request
        hub.pending_requests.pop(request_id, None)

# ==================== WebSocket Pub/Sub ====================

async def broadcast(event_type: str, data: dict, exclude_ws=None):
    """Broadcast event to all connected subscribers."""
    message = json.dumps({
        "type": event_type,
        "timestamp": datetime.now().isoformat(),
        "data": data
    })

    dead_connections = set()
    for ws in hub.subscribers:
        if ws != exclude_ws:
            try:
                await ws.send(message)
            except websockets.exceptions.ConnectionClosed:
                dead_connections.add(ws)

    # Clean up dead connections
    hub.subscribers -= dead_connections

async def handle_ws_client(websocket):
    """Handle incoming WebSocket connection from IDE."""
    hub.subscribers.add(websocket)
    project_id = None

    try:
        logger.info(f"New WebSocket connection from {websocket.remote_address}")

        async for message in websocket:
            try:
                msg = json.loads(message)
                msg_type = msg.get("type")
                data = msg.get("data", {})

                if msg_type == "register":
                    # IDE registering itself
                    project_id = data.get("project_id") or f"project_{len(hub.projects)}"
                    hub.projects[project_id] = {
                        "ide": data.get("ide", "unknown"),
                        "project_path": data.get("project_path"),
                        "project_name": data.get("project_name"),
                        "websocket": websocket,
                        "capabilities": data.get("capabilities", []),
                        "registered_at": datetime.now().isoformat()
                    }
                    logger.info(f"Registered project: {project_id} ({data.get('ide')})")

                    # Broadcast project list update
                    await broadcast("projects_updated", {
                        "projects": list(hub.projects.keys())
                    })

                    # Send current AI server status to new client
                    await websocket.send(json.dumps({
                        "type": "ai_server_status",
                        "data": hub.ai_server_status
                    }))

                elif msg_type == "ai_server_started":
                    # AI server started by this IDE
                    hub.ai_server_status = {
                        "running": True,
                        "port": data.get("port", 8080),
                        "model": data.get("model"),
                        "started_by": data.get("started_by", project_id),
                        "started_at": datetime.now().isoformat()
                    }
                    await broadcast("ai_server_status", hub.ai_server_status, exclude_ws=websocket)
                    logger.info(f"AI server started by {project_id}")

                elif msg_type == "ai_server_stopped":
                    # AI server stopped
                    hub.ai_server_status = {
                        "running": False,
                        "port": 8080,
                        "model": None,
                        "started_by": None,
                        "started_at": None
                    }
                    await broadcast("ai_server_status", hub.ai_server_status, exclude_ws=websocket)
                    logger.info(f"AI server stopped by {project_id}")

                elif msg_type == "trace_update":
                    # Trace data from IDE - store it
                    if project_id:
                        hub.trace_data[project_id] = data
                    await broadcast("trace_update", {
                        "project_id": project_id,
                        **data
                    }, exclude_ws=websocket)

                elif msg_type == "rpc_response":
                    # Response to an RPC request
                    request_id = msg.get("request_id")
                    response_data = msg.get("data", {})

                    if request_id and request_id in hub.pending_requests:
                        future = hub.pending_requests[request_id]
                        if not future.done():
                            future.set_result(response_data)
                        logger.debug(f"RPC response received for {request_id}")

                elif msg_type == "request":
                    # Legacy request to specific project or broadcast
                    target_project = data.get("target_project")
                    if target_project and target_project in hub.projects:
                        target_ws = hub.projects[target_project].get("websocket")
                        if target_ws:
                            await target_ws.send(json.dumps({
                                "type": "request",
                                "from_project": project_id,
                                "data": data
                            }))
                    else:
                        await broadcast("request", {
                            "from_project": project_id,
                            **data
                        }, exclude_ws=websocket)

                elif msg_type == "response":
                    # Legacy response to a previous request
                    target_project = data.get("target_project")
                    if target_project and target_project in hub.projects:
                        target_ws = hub.projects[target_project].get("websocket")
                        if target_ws:
                            await target_ws.send(json.dumps({
                                "type": "response",
                                "from_project": project_id,
                                "data": data
                            }))

            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from {websocket.remote_address}")

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        hub.subscribers.discard(websocket)
        if project_id and project_id in hub.projects:
            del hub.projects[project_id]
            logger.info(f"Unregistered project: {project_id}")
            await broadcast("projects_updated", {
                "projects": list(hub.projects.keys())
            })

async def run_websocket_server():
    """Run WebSocket server for pub/sub."""
    async with ws_serve(handle_ws_client, "127.0.0.1", 5680):
        logger.info("WebSocket pub/sub server running on ws://127.0.0.1:5680")
        await asyncio.Future()  # Run forever

# ==================== MCP Server Tools ====================

if HAS_MCP:
    mcp_server = Server("trueflow-hub")

    @mcp_server.list_tools()
    async def list_tools():
        """List all available MCP tools."""
        return [
            Tool(
                name="list_projects",
                description="List all connected IDE projects with their capabilities",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="get_ai_server_status",
                description="Get current AI server status across all IDEs",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="start_ai_server",
                description="Start AI server from a specific project",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "Target project ID (optional, uses first available)"},
                        "model": {"type": "string", "description": "Model to load (optional)"}
                    }
                }
            ),
            Tool(
                name="stop_ai_server",
                description="Stop the running AI server",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="get_trace_data",
                description="Get execution trace data from an IDE project. Returns JSON with call traces, timing, etc.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "Project ID to get traces from"}
                    },
                    "required": ["project_id"]
                }
            ),
            Tool(
                name="get_dead_code",
                description="Get dead/unreachable code analysis from an IDE project. Returns JSON with dead functions list.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "Project ID to analyze"}
                    },
                    "required": ["project_id"]
                }
            ),
            Tool(
                name="get_performance_data",
                description="Get performance profiling data from an IDE project. Returns JSON with hotspots, timing stats.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "Project ID to get performance data from"}
                    },
                    "required": ["project_id"]
                }
            ),
            Tool(
                name="export_diagram",
                description="Export sequence diagram (PlantUML/Mermaid) from an IDE project.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "Project ID"},
                        "format": {"type": "string", "enum": ["plantuml", "mermaid"], "description": "Diagram format"}
                    },
                    "required": ["project_id"]
                }
            ),
            Tool(
                name="generate_manim_video",
                description="Generate Manim execution video for a project. Returns path to generated video.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "Project ID"},
                        "trace_id": {"type": "string", "description": "Trace/correlation ID (optional)"}
                    },
                    "required": ["project_id"]
                }
            ),
            Tool(
                name="send_command",
                description="Send a custom command to an IDE project and get the response.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "Target project ID"},
                        "command": {"type": "string", "description": "Command name"},
                        "args": {"type": "object", "description": "Command arguments"}
                    },
                    "required": ["project_id", "command"]
                }
            ),
            Tool(
                name="broadcast_message",
                description="Broadcast a message to all connected IDEs (fire-and-forget).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "Message to broadcast"},
                        "data": {"type": "object", "description": "Additional data"}
                    },
                    "required": ["message"]
                }
            )
        ]

    @mcp_server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """Handle MCP tool calls with RPC response waiting."""

        if name == "list_projects":
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
            return [TextContent(
                type="text",
                text=json.dumps({"projects": projects_info, "count": len(projects_info)}, indent=2)
            )]

        elif name == "get_ai_server_status":
            return [TextContent(
                type="text",
                text=json.dumps(hub.ai_server_status, indent=2)
            )]

        elif name == "start_ai_server":
            project_id = arguments.get("project_id")
            if not project_id or project_id not in hub.projects:
                # Pick first available project
                if hub.projects:
                    project_id = list(hub.projects.keys())[0]
                else:
                    return [TextContent(type="text", text=json.dumps({"error": "No projects connected"}))]

            # Send RPC request and wait for response
            response = await rpc_call(project_id, "start_ai_server", {"model": arguments.get("model")})
            if response:
                return [TextContent(type="text", text=json.dumps(response, indent=2))]
            return [TextContent(type="text", text=json.dumps({"status": "requested", "project": project_id}))]

        elif name == "stop_ai_server":
            # Broadcast stop command to all IDEs
            await broadcast("command", {"command": "stop_ai_server"})
            return [TextContent(type="text", text=json.dumps({"status": "broadcast_sent", "subscribers": len(hub.subscribers)}))]

        elif name == "get_trace_data":
            project_id = arguments.get("project_id")

            # First check if we have cached trace data
            if project_id in hub.trace_data:
                return [TextContent(
                    type="text",
                    text=json.dumps(hub.trace_data[project_id], indent=2)
                )]

            # Otherwise, request fresh data via RPC
            if project_id not in hub.projects:
                return [TextContent(type="text", text=json.dumps({"error": f"Project {project_id} not found"}))]

            response = await rpc_call(project_id, "get_trace_data", {})
            if response:
                return [TextContent(type="text", text=json.dumps(response, indent=2))]
            return [TextContent(type="text", text=json.dumps({"error": f"No trace data from {project_id} (timeout)"}))]

        elif name == "get_dead_code":
            project_id = arguments.get("project_id")
            if project_id not in hub.projects:
                return [TextContent(type="text", text=json.dumps({"error": f"Project {project_id} not found"}))]

            response = await rpc_call(project_id, "get_dead_code", {})
            if response:
                return [TextContent(type="text", text=json.dumps(response, indent=2))]
            return [TextContent(type="text", text=json.dumps({"error": f"No dead code data from {project_id} (timeout)"}))]

        elif name == "get_performance_data":
            project_id = arguments.get("project_id")
            if project_id not in hub.projects:
                return [TextContent(type="text", text=json.dumps({"error": f"Project {project_id} not found"}))]

            response = await rpc_call(project_id, "get_performance_data", {})
            if response:
                return [TextContent(type="text", text=json.dumps(response, indent=2))]
            return [TextContent(type="text", text=json.dumps({"error": f"No performance data from {project_id} (timeout)"}))]

        elif name == "export_diagram":
            project_id = arguments.get("project_id")
            diagram_format = arguments.get("format", "plantuml")

            if project_id not in hub.projects:
                return [TextContent(type="text", text=json.dumps({"error": f"Project {project_id} not found"}))]

            response = await rpc_call(project_id, "export_diagram", {"format": diagram_format})
            if response:
                return [TextContent(type="text", text=json.dumps(response, indent=2))]
            return [TextContent(type="text", text=json.dumps({"error": f"No diagram from {project_id} (timeout)"}))]

        elif name == "generate_manim_video":
            project_id = arguments.get("project_id")
            if project_id not in hub.projects:
                return [TextContent(type="text", text=json.dumps({"error": f"Project {project_id} not found"}))]

            response = await rpc_call(project_id, "generate_manim", {"trace_id": arguments.get("trace_id")}, timeout=120)
            if response:
                return [TextContent(type="text", text=json.dumps(response, indent=2))]
            return [TextContent(type="text", text=json.dumps({"error": f"Manim generation failed or timed out"}))]

        elif name == "send_command":
            project_id = arguments.get("project_id")
            command = arguments.get("command")
            args = arguments.get("args", {})

            if project_id not in hub.projects:
                return [TextContent(type="text", text=json.dumps({"error": f"Project {project_id} not found"}))]

            response = await rpc_call(project_id, command, args)
            if response:
                return [TextContent(type="text", text=json.dumps(response, indent=2))]
            return [TextContent(type="text", text=json.dumps({"error": f"Command {command} failed or timed out"}))]

        elif name == "broadcast_message":
            await broadcast("message", {
                "message": arguments.get("message"),
                "data": arguments.get("data", {})
            })
            return [TextContent(type="text", text=json.dumps({"status": "broadcast_sent", "subscribers": len(hub.subscribers)}))]

        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

# ==================== Main Entry Points ====================

async def run_hub():
    """Run both MCP server and WebSocket server."""
    write_hub_status(True)

    try:
        # Run WebSocket server in background
        ws_task = asyncio.create_task(run_websocket_server())

        # Run MCP server on stdio
        if HAS_MCP:
            logger.info("Starting MCP server on stdio...")
            async with stdio_server() as (read_stream, write_stream):
                await mcp_server.run(read_stream, write_stream, mcp_server.create_initialization_options())
        else:
            # Just run WebSocket if no MCP
            await ws_task
    finally:
        write_hub_status(False)

async def run_ws_only():
    """Run only WebSocket server (no MCP)."""
    write_hub_status(True)
    try:
        await run_websocket_server()
    finally:
        write_hub_status(False)

def main():
    """Main entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="TrueFlow MCP Hub")
    parser.add_argument("--start", action="store_true", help="Start the hub server")
    parser.add_argument("--ws-only", action="store_true", help="Run WebSocket server only (no MCP)")
    parser.add_argument("--connect", action="store_true", help="Connect to existing hub")
    parser.add_argument("--project", type=str, help="Project ID when connecting")
    parser.add_argument("--ide", type=str, default="unknown", help="IDE type (vscode/pycharm)")
    parser.add_argument("--status", action="store_true", help="Check hub status")
    args = parser.parse_args()

    if args.status:
        status = read_hub_status()
        if status:
            print(json.dumps(status, indent=2))
        else:
            print("Hub not running")
        return

    if args.start:
        if is_hub_running():
            print("Hub is already running on port 5680")
            return

        print("Starting TrueFlow MCP Hub...")
        try:
            if args.ws_only:
                asyncio.run(run_ws_only())
            else:
                asyncio.run(run_hub())
        except KeyboardInterrupt:
            print("\nShutting down...")

    elif args.ws_only:
        if is_hub_running():
            print("Hub is already running on port 5680")
            return

        print("Starting TrueFlow WebSocket Hub (no MCP)...")
        try:
            asyncio.run(run_ws_only())
        except KeyboardInterrupt:
            print("\nShutting down...")

    elif args.connect:
        # This mode is for IDEs to connect as clients
        # The actual connection logic would be in the IDE plugins
        print(f"Connect mode - project={args.project}, ide={args.ide}")
        print("Use the IDE plugin to connect to ws://127.0.0.1:5680")

if __name__ == "__main__":
    main()
