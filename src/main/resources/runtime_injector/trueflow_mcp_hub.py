#!/usr/bin/env python3
"""
TrueFlow MCP Hub - Thin Routing Layer to IDE

This MCP server delegates analysis to the connected IDE (PyCharm/VS Code).
The IDE has the superior implementation with:
- Pre-parsed function registry from Python instrumentor
- Class inference for accurate dead code detection
- Branch tracking for "why not covered" analysis
- Real-time trace data

Architecture:
    Claude Code --MCP--> Hub --RPC--> IDE Plugin (analysis engine)
                              |
                              v
                         WebSocket (5680)

The hub does NOT duplicate analysis logic - it routes to IDE.
"""

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Set
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


# ============================================================================
# HUB STATE (coordination only, no analysis state)
# ============================================================================

@dataclass
class HubState:
    """State for hub coordination - delegates analysis to IDE."""
    # Project directory
    project_dir: Path = field(default_factory=lambda: Path(os.environ.get("TRUEFLOW_PROJECT_DIR", str(Path.cwd()))))

    # Connected IDE instances: {project_id: {ide, project_path, websocket, capabilities}}
    projects: Dict[str, Dict] = field(default_factory=dict)

    # WebSocket connections for pub/sub
    subscribers: Set = field(default_factory=set)

    # AI server status (shared across IDEs)
    ai_server_status: Dict = field(default_factory=lambda: {
        "running": False, "port": 8080, "model": None, "started_by": None, "started_at": None
    })
    ai_server_process: Optional[subprocess.Popen] = None

    # Pending RPC requests: {request_id: asyncio.Future}
    pending_requests: Dict[str, asyncio.Future] = field(default_factory=dict)


state = HubState()
RPC_TIMEOUT = 30
STATUS_FILE = Path.home() / ".trueflow" / "hub_status.json"


def is_hub_running() -> bool:
    """Check if hub is already running."""
    import socket as sock
    try:
        with sock.socket(sock.AF_INET, sock.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect(("127.0.0.1", 5680))
            return True
    except:
        return False


def write_hub_status(running: bool):
    """Write hub status to shared file."""
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps({
        "running": running, "pid": os.getpid(), "ws_port": 5680, "started_at": datetime.now().isoformat()
    }, indent=2))


# ============================================================================
# RPC TO IDE (the core routing mechanism)
# ============================================================================

async def rpc_to_ide(command: str, args: dict = None, timeout: float = RPC_TIMEOUT) -> Optional[Dict]:
    """
    Send RPC request to connected IDE and wait for response.
    This is the ONLY way analysis happens - via IDE delegation.
    """
    if not state.projects:
        return None

    # Use first connected IDE
    project_id = list(state.projects.keys())[0]
    ws = state.projects[project_id].get("websocket")
    if not ws:
        return None

    request_id = str(uuid.uuid4())
    future = asyncio.get_event_loop().create_future()
    state.pending_requests[request_id] = future

    try:
        await ws.send(json.dumps({
            "type": "rpc_request", "request_id": request_id, "command": command, "args": args or {}
        }))
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"RPC {command} timed out")
        return None
    except Exception as e:
        logger.warning(f"RPC {command} failed: {e}")
        return None
    finally:
        state.pending_requests.pop(request_id, None)


def require_ide(tool_name: str) -> str:
    """Return error message when IDE is required but not connected."""
    return json.dumps({
        "error": f"No IDE connected. {tool_name} requires PyCharm or VS Code with TrueFlow plugin.",
        "hint": "Open your project in PyCharm/VS Code with TrueFlow plugin installed and running.",
        "connected_ides": len(state.projects)
    }, indent=2)


async def broadcast(event_type: str, data: dict, exclude_ws=None):
    """Broadcast event to all connected subscribers."""
    message = json.dumps({"type": event_type, "timestamp": datetime.now().isoformat(), "data": data})
    dead = set()
    for ws in state.subscribers:
        if ws != exclude_ws:
            try:
                await ws.send(message)
            except:
                dead.add(ws)
    state.subscribers -= dead


# ============================================================================
# WEBSOCKET SERVER (IDE coordination)
# ============================================================================

async def handle_ws_client(websocket):
    """Handle WebSocket connection from IDE."""
    state.subscribers.add(websocket)
    project_id = None

    try:
        async for message in websocket:
            try:
                msg = json.loads(message)
                msg_type = msg.get("type")
                data = msg.get("data", {})

                if msg_type == "register":
                    project_id = data.get("project_id") or f"project_{len(state.projects)}"
                    state.projects[project_id] = {
                        "ide": data.get("ide", "unknown"),
                        "project_path": data.get("project_path"),
                        "project_name": data.get("project_name"),
                        "websocket": websocket,
                        "capabilities": data.get("capabilities", []),
                        "registered_at": datetime.now().isoformat()
                    }
                    logger.info(f"IDE registered: {project_id} ({data.get('ide')})")
                    await broadcast("projects_updated", {"projects": list(state.projects.keys())})

                elif msg_type == "ai_server_started":
                    state.ai_server_status = {
                        "running": True, "port": data.get("port", 8080), "model": data.get("model"),
                        "started_by": project_id, "started_at": datetime.now().isoformat()
                    }
                    await broadcast("ai_server_status", state.ai_server_status, exclude_ws=websocket)

                elif msg_type == "ai_server_stopped":
                    state.ai_server_status = {"running": False, "port": 8080, "model": None, "started_by": None, "started_at": None}
                    await broadcast("ai_server_status", state.ai_server_status, exclude_ws=websocket)

                elif msg_type == "rpc_response":
                    request_id = msg.get("request_id")
                    if request_id and request_id in state.pending_requests:
                        future = state.pending_requests[request_id]
                        if not future.done():
                            future.set_result(msg.get("data", {}))

            except json.JSONDecodeError:
                pass
    except:
        pass
    finally:
        state.subscribers.discard(websocket)
        if project_id and project_id in state.projects:
            del state.projects[project_id]
            logger.info(f"IDE disconnected: {project_id}")
            await broadcast("projects_updated", {"projects": list(state.projects.keys())})


async def run_websocket_server():
    """Run WebSocket server for IDE connections."""
    if not HAS_WEBSOCKETS:
        return
    async with ws_serve(handle_ws_client, "127.0.0.1", 5680):
        logger.info("Hub WebSocket server on ws://127.0.0.1:5680")
        await asyncio.Future()


# ============================================================================
# MCP TOOLS - All delegate to IDE
# ============================================================================

if HAS_MCP:
    mcp_server = Server("trueflow-hub")

    @mcp_server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools - all delegate to IDE."""
        return [
            # Hub status
            Tool(name="list_projects", description="List connected IDE instances", inputSchema={"type": "object", "properties": {}, "required": []}),
            Tool(name="get_project_info", description="Get hub and project info", inputSchema={"type": "object", "properties": {}, "required": []}),

            # Analysis tools (delegate to IDE)
            Tool(name="analyze_dead_code", description="Find dead/unreachable code (requires IDE)", inputSchema={"type": "object", "properties": {"source_dir": {"type": "string", "default": "src"}}, "required": []}),
            Tool(name="analyze_performance", description="Analyze performance hotspots (requires IDE)", inputSchema={"type": "object", "properties": {"sort_by": {"type": "string", "default": "total_ms"}, "limit": {"type": "integer", "default": 20}}, "required": []}),
            Tool(name="analyze_call_tree", description="Generate call tree (requires IDE)", inputSchema={"type": "object", "properties": {"root_function": {"type": "string"}, "max_depth": {"type": "integer", "default": 5}}, "required": []}),

            # Explorer tools (delegate to IDE)
            Tool(name="explorer_get_callers", description="Get all callers of a function (requires IDE)", inputSchema={"type": "object", "properties": {"function_name": {"type": "string"}, "max_depth": {"type": "integer", "default": 3}}, "required": ["function_name"]}),
            Tool(name="explorer_get_callees", description="Get all callees of a function (requires IDE)", inputSchema={"type": "object", "properties": {"function_name": {"type": "string"}, "max_depth": {"type": "integer", "default": 3}}, "required": ["function_name"]}),
            Tool(name="explorer_search", description="Search functions by name (requires IDE)", inputSchema={"type": "object", "properties": {"query": {"type": "string"}, "search_type": {"type": "string", "default": "function"}}, "required": ["query"]}),
            Tool(name="explorer_get_call_chain", description="Get full call chain (requires IDE)", inputSchema={"type": "object", "properties": {"function_name": {"type": "string"}}, "required": ["function_name"]}),
            Tool(name="explorer_get_coverage_summary", description="Get coverage summary (requires IDE)", inputSchema={"type": "object", "properties": {}, "required": []}),
            Tool(name="explorer_find_path", description="Find path between functions (requires IDE)", inputSchema={"type": "object", "properties": {"source": {"type": "string"}, "target": {"type": "string"}}, "required": ["source", "target"]}),
            Tool(name="explorer_explain_function", description="AI explanation of a function (requires IDE)", inputSchema={"type": "object", "properties": {"function_name": {"type": "string"}}, "required": ["function_name"]}),

            # Export tools (delegate to IDE)
            Tool(name="export_diagram", description="Export PlantUML/Mermaid diagram (requires IDE)", inputSchema={"type": "object", "properties": {"format": {"type": "string", "default": "plantuml"}, "output_file": {"type": "string"}}, "required": []}),
            Tool(name="export_flamegraph", description="Export flamegraph JSON (requires IDE)", inputSchema={"type": "object", "properties": {"output_file": {"type": "string"}}, "required": []}),

            # Manim tools (delegate to IDE)
            Tool(name="manim_generate_video", description="Generate Manim video (requires IDE)", inputSchema={"type": "object", "properties": {"trace_file": {"type": "string"}, "quality": {"type": "string", "default": "low_quality"}}, "required": []}),
            Tool(name="manim_list_videos", description="List generated videos (requires IDE)", inputSchema={"type": "object", "properties": {}, "required": []}),

            # AI server tools (hub manages, IDE can start)
            Tool(name="ai_server_start", description="Start llama.cpp server", inputSchema={"type": "object", "properties": {"model_path": {"type": "string"}, "port": {"type": "integer", "default": 8080}}, "required": []}),
            Tool(name="ai_server_stop", description="Stop AI server", inputSchema={"type": "object", "properties": {}, "required": []}),
            Tool(name="ai_server_status", description="Get AI server status", inputSchema={"type": "object", "properties": {}, "required": []}),

            # Lazy tool loading (for low-throughput LLMs)
            Tool(name="get_tool_categories", description="Get tool categories for lazy loading", inputSchema={"type": "object", "properties": {}, "required": []}),
            Tool(name="smart_query", description="Auto-classify and route query to appropriate tool", inputSchema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
        ]

    @mcp_server.call_tool()
    async def call_tool(name: str, arguments: dict) -> Sequence[TextContent]:
        """Route tool calls to IDE."""
        try:
            result = await _route_tool(name, arguments)
            return [TextContent(type="text", text=result)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {e}")]


async def _route_tool(name: str, args: dict) -> str:
    """Route tool to IDE via RPC or handle locally."""

    # === Hub-local tools (no IDE needed) ===

    if name == "list_projects":
        return json.dumps({
            "projects": [{
                "id": pid,
                "ide": info.get("ide"),
                "project_name": info.get("project_name"),
                "project_path": info.get("project_path"),
                "capabilities": info.get("capabilities", []),
                "registered_at": info.get("registered_at")
            } for pid, info in state.projects.items()],
            "count": len(state.projects),
            "hub_status": "running"
        }, indent=2)

    if name == "get_project_info":
        return json.dumps({
            "hub_running": True,
            "project_dir": str(state.project_dir),
            "connected_ides": len(state.projects),
            "ai_server": state.ai_server_status
        }, indent=2)

    if name == "ai_server_status":
        return json.dumps(state.ai_server_status, indent=2)

    if name == "get_tool_categories":
        return json.dumps({
            "categories": {
                "analysis": {"tools": ["analyze_dead_code", "analyze_performance", "analyze_call_tree"], "requires_ide": True},
                "explorer": {"tools": ["explorer_get_callers", "explorer_get_callees", "explorer_search", "explorer_get_call_chain", "explorer_find_path"], "requires_ide": True},
                "export": {"tools": ["export_diagram", "export_flamegraph"], "requires_ide": True},
                "video": {"tools": ["manim_generate_video", "manim_list_videos"], "requires_ide": True},
                "ai": {"tools": ["ai_server_start", "ai_server_stop", "ai_server_status"], "requires_ide": False},
                "hub": {"tools": ["list_projects", "get_project_info"], "requires_ide": False}
            },
            "note": "Most tools require an IDE (PyCharm/VS Code) with TrueFlow plugin connected."
        }, indent=2)

    if name == "smart_query":
        return await _smart_query(args.get("query", ""))

    # === AI server tools (hub can manage directly) ===

    if name == "ai_server_start":
        return await _ai_server_start(args.get("model_path", ""), args.get("port", 8080))

    if name == "ai_server_stop":
        return await _ai_server_stop()

    # === Tools that REQUIRE IDE ===

    if not state.projects:
        return require_ide(name)

    # Map tool names to RPC commands
    rpc_commands = {
        "analyze_dead_code": "get_dead_code",
        "analyze_performance": "get_performance_data",
        "analyze_call_tree": "get_call_tree",
        "explorer_get_callers": "get_callers",
        "explorer_get_callees": "get_callees",
        "explorer_search": "search_functions",
        "explorer_get_call_chain": "get_call_chain",
        "explorer_get_coverage_summary": "get_coverage_summary",
        "explorer_find_path": "find_path",
        "explorer_explain_function": "explain_function",
        "export_diagram": "export_diagram",
        "export_flamegraph": "export_flamegraph",
        "manim_generate_video": "generate_manim",
        "manim_list_videos": "list_videos",
    }

    rpc_command = rpc_commands.get(name)
    if not rpc_command:
        return json.dumps({"error": f"Unknown tool: {name}"})

    # Send RPC to IDE
    response = await rpc_to_ide(rpc_command, args)

    if response is None:
        return json.dumps({
            "error": f"IDE did not respond to {name}",
            "hint": "Ensure TrueFlow plugin is running in your IDE"
        }, indent=2)

    return json.dumps(response, indent=2)


# ============================================================================
# AI SERVER MANAGEMENT (hub can do this directly)
# ============================================================================

async def _ai_server_start(model_path: str, port: int) -> str:
    """Start AI server - try IDE first, fallback to direct."""
    if state.ai_server_process and state.ai_server_process.poll() is None:
        return json.dumps({"status": "already_running", **state.ai_server_status}, indent=2)

    # Try IDE first (may have GPU configured)
    if state.projects:
        response = await rpc_to_ide("start_ai_server", {"model": model_path, "port": port})
        if response and response.get("status") == "started":
            state.ai_server_status = {"running": True, "port": port, "model": model_path, "started_at": datetime.now().isoformat()}
            return json.dumps({"status": "started_by_ide", **state.ai_server_status}, indent=2)

    # Direct start
    home = Path.home()
    llama = home / ".trueflow" / "llama.cpp" / "build" / "bin" / "Release" / "llama-server.exe"
    if not llama.exists():
        llama = home / ".trueflow" / "llama.cpp" / "build" / "bin" / "llama-server"
    if not llama.exists():
        return json.dumps({"error": "llama-server not found", "hint": "Install llama.cpp to ~/.trueflow/llama.cpp"})

    if not model_path:
        models = home / ".trueflow" / "models"
        if models.exists():
            for g in models.glob("*.gguf"):
                model_path = str(g)
                break
    if not model_path:
        return json.dumps({"error": "No model found", "hint": "Download a model to ~/.trueflow/models/"})

    try:
        state.ai_server_process = subprocess.Popen(
            [str(llama), "--model", model_path, "--port", str(port), "--ctx-size", "4096", "--host", "127.0.0.1"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        # Wait for server to be ready
        for _ in range(30):
            time.sleep(1)
            try:
                import urllib.request
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
                state.ai_server_status = {"running": True, "port": port, "model": model_path, "started_at": datetime.now().isoformat()}
                return json.dumps({"status": "started", **state.ai_server_status}, indent=2)
            except:
                continue
        return json.dumps({"status": "starting", "note": "Server still loading..."})
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _ai_server_stop() -> str:
    """Stop AI server."""
    if state.ai_server_process:
        try:
            state.ai_server_process.terminate()
            state.ai_server_process.wait(timeout=5)
        except:
            pass
        state.ai_server_process = None

    state.ai_server_status = {"running": False, "port": 8080, "model": None, "started_by": None, "started_at": None}

    # Also notify IDEs
    if state.projects:
        await rpc_to_ide("stop_ai_server", {})

    return json.dumps({"status": "stopped"})


# ============================================================================
# SMART QUERY (auto-routing for lazy loading)
# ============================================================================

TOOL_KEYWORDS = {
    "analyze_dead_code": ["dead", "unused", "unreachable", "uncalled"],
    "analyze_performance": ["slow", "performance", "bottleneck", "hotspot", "time"],
    "explorer_get_callers": ["who calls", "callers", "called by"],
    "explorer_get_callees": ["what does", "callees", "calls to"],
    "explorer_search": ["find", "search", "where is"],
    "export_diagram": ["diagram", "plantuml", "mermaid", "sequence"],
    "manim_generate_video": ["video", "animation", "manim"],
}


async def _smart_query(query: str) -> str:
    """Classify query and route to appropriate tool."""
    query_lower = query.lower()

    # Check for greetings
    if any(g in query_lower for g in ["hi", "hello", "hey", "help"]):
        return json.dumps({
            "response": "Hello! I'm TrueFlow. I can analyze your code for dead code, performance issues, and more. Ask me things like 'find dead code' or 'who calls step()'.",
            "requires_ide": True,
            "ide_connected": len(state.projects) > 0
        }, indent=2)

    # Find matching tool
    best_tool = None
    best_score = 0
    for tool, keywords in TOOL_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in query_lower)
        if score > best_score:
            best_score = score
            best_tool = tool

    if not best_tool:
        return json.dumps({
            "response": "I'm not sure what you're asking. Try: 'find dead code', 'show performance hotspots', or 'who calls <function>'",
            "available_tools": list(TOOL_KEYWORDS.keys())
        }, indent=2)

    if not state.projects:
        return require_ide(best_tool)

    # Extract function name if needed
    args = {}
    if "function" in best_tool or "callers" in best_tool or "callees" in best_tool:
        import re
        match = re.search(r'(?:calls?|function)\s+[`"\']?(\w+)[`"\']?', query_lower)
        if match:
            args["function_name"] = match.group(1)

    # Route to tool
    return await _route_tool(best_tool, args)


# ============================================================================
# MAIN
# ============================================================================

async def run_hub():
    """Run the hub."""
    write_hub_status(True)
    try:
        if HAS_WEBSOCKETS:
            ws_task = asyncio.create_task(run_websocket_server())
        if HAS_MCP:
            logger.info("TrueFlow Hub starting (delegates to IDE for analysis)...")
            async with stdio_server() as (read, write):
                await mcp_server.run(read, write, mcp_server.create_initialization_options())
        elif HAS_WEBSOCKETS:
            await ws_task
    finally:
        write_hub_status(False)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="TrueFlow MCP Hub")
    parser.add_argument("--start", action="store_true", help="Start the hub")
    parser.add_argument("--status", action="store_true", help="Check status")
    parser.add_argument("--ws-only", action="store_true", help="WebSocket only mode (no MCP)")
    args = parser.parse_args()

    if args.status:
        if STATUS_FILE.exists():
            print(STATUS_FILE.read_text())
        else:
            print("Hub not running")
        return

    if is_hub_running():
        print("Hub already running on port 5680")
        return

    print("Starting TrueFlow Hub...")
    try:
        asyncio.run(run_hub())
    except KeyboardInterrupt:
        print("\nShutdown")


if __name__ == "__main__":
    main()
