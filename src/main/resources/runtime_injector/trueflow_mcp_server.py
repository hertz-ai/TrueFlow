#!/usr/bin/env python3
"""
TrueFlow MCP Server - Model Context Protocol server for AI agent integration.

This server exposes all TrueFlow plugin functionality as MCP tools that can be
invoked by AI agents (Claude, GPT, etc.) to:
- Start/stop trace collection
- Generate Manim videos
- Analyze dead code and performance
- Export diagrams
- Manage AI server
- Query trace data

Usage:
    python trueflow_mcp_server.py

Configuration (environment variables):
    TRUEFLOW_PROJECT_DIR - Project directory to trace (default: current dir)
    TRUEFLOW_TRACE_PORT - Socket port for trace server (default: 5678)
    TRUEFLOW_API_PORT - Port for AI server (default: 8080)

Compatible with MCP SDK 1.x (list_tools/call_tool API)
"""

import ast
import asyncio
import json
import logging
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Sequence

# MCP SDK imports
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("MCP SDK not installed. Install with: pip install mcp", file=sys.stderr)
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("trueflow-mcp")

# Server instance
server = Server("trueflow")


@dataclass
class TrueFlowState:
    """Global state for TrueFlow MCP server."""
    project_dir: Path = field(default_factory=lambda: Path(os.environ.get("TRUEFLOW_PROJECT_DIR", str(Path.cwd()))))
    trace_socket: Optional[socket.socket] = None
    trace_connected: bool = False
    trace_events: list = field(default_factory=list)
    ai_server_process: Optional[subprocess.Popen] = None
    manim_videos: list = field(default_factory=list)
    performance_data: dict = field(default_factory=dict)
    dead_code_data: dict = field(default_factory=dict)
    call_trace_data: list = field(default_factory=list)
    call_graph: dict = field(default_factory=dict)
    reverse_call_graph: dict = field(default_factory=dict)
    covered_functions: set = field(default_factory=set)
    function_info: dict = field(default_factory=dict)
    _call_stack: list = field(default_factory=list)


# Global state
state = TrueFlowState()


# ============================================================================
# TOOL DEFINITIONS (MCP SDK 1.x compatible)
# ============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools."""
    return [
        # Trace Collection Tools
        Tool(
            name="trace_connect",
            description="Connect to a running TrueFlow trace server on port 5678. Returns connection status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "host": {"type": "string", "description": "Trace server host", "default": "127.0.0.1"},
                    "port": {"type": "integer", "description": "Trace server port", "default": 5678}
                },
                "required": []
            }
        ),
        Tool(
            name="trace_disconnect",
            description="Disconnect from the trace server.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="trace_status",
            description="Get current trace collection status including event count and connection state.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="trace_get_events",
            description="Get collected trace events with optional filtering.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max events to return", "default": 100},
                    "filter_module": {"type": "string", "description": "Filter by module name"},
                    "filter_function": {"type": "string", "description": "Filter by function name"}
                },
                "required": []
            }
        ),
        Tool(
            name="trace_clear",
            description="Clear all collected trace events.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        # Analysis Tools
        Tool(
            name="analyze_dead_code",
            description="Analyze dead/unreachable code by comparing static AST with runtime traces. Shows functions defined but never executed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_dir": {"type": "string", "description": "Source directory to analyze", "default": "src/crawl4ai/embodied_ai"}
                },
                "required": []
            }
        ),
        Tool(
            name="analyze_performance",
            description="Analyze performance metrics from traces - call counts, execution times, bottlenecks.",
            inputSchema={
                "type": "object",
                "properties": {
                    "sort_by": {"type": "string", "description": "Sort by: total_ms, calls, avg_ms, max_ms", "default": "total_ms"},
                    "limit": {"type": "integer", "description": "Number of top functions", "default": 20}
                },
                "required": []
            }
        ),
        Tool(
            name="analyze_call_tree",
            description="Generate a call tree showing function call hierarchy.",
            inputSchema={
                "type": "object",
                "properties": {
                    "root_function": {"type": "string", "description": "Starting function (empty for all entry points)"},
                    "max_depth": {"type": "integer", "description": "Maximum tree depth", "default": 5}
                },
                "required": []
            }
        ),
        # Explorer Tools
        Tool(
            name="explorer_get_callers",
            description="Get all functions that call a specific function (upstream call chain).",
            inputSchema={
                "type": "object",
                "properties": {
                    "function_name": {"type": "string", "description": "Function to find callers for"},
                    "max_depth": {"type": "integer", "description": "How deep to trace", "default": 3}
                },
                "required": ["function_name"]
            }
        ),
        Tool(
            name="explorer_get_callees",
            description="Get all functions called by a specific function (downstream call chain).",
            inputSchema={
                "type": "object",
                "properties": {
                    "function_name": {"type": "string", "description": "Function to find callees for"},
                    "max_depth": {"type": "integer", "description": "How deep to trace", "default": 3}
                },
                "required": ["function_name"]
            }
        ),
        Tool(
            name="explorer_search",
            description="Search for functions by name pattern in trace data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (partial match)"},
                    "search_type": {"type": "string", "description": "What to search: function, module, file, all", "default": "function"}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="explorer_get_call_chain",
            description="Get complete call chain for a function - both upstream and downstream.",
            inputSchema={
                "type": "object",
                "properties": {
                    "function_name": {"type": "string", "description": "Function to analyze"},
                    "source_dir": {"type": "string", "description": "Source directory", "default": "src/crawl4ai/embodied_ai"}
                },
                "required": ["function_name"]
            }
        ),
        Tool(
            name="explorer_get_coverage_summary",
            description="Get code coverage summary from trace data.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="explorer_find_path",
            description="Find the call path between two functions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Starting function"},
                    "target": {"type": "string", "description": "Target function"}
                },
                "required": ["source", "target"]
            }
        ),
        Tool(
            name="explorer_get_function_details",
            description="Get detailed information about a specific function including file, line, calls, performance metrics, callers and callees.",
            inputSchema={
                "type": "object",
                "properties": {
                    "function_name": {"type": "string", "description": "Full or partial function name to look up"}
                },
                "required": ["function_name"]
            }
        ),
        Tool(
            name="explorer_get_hot_paths",
            description="Get the most frequently executed code paths (hot paths) for performance analysis.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of hot paths to return", "default": 10}
                },
                "required": []
            }
        ),
        Tool(
            name="explorer_get_call_graph",
            description="Get the full call graph structure showing caller->callees relationships.",
            inputSchema={
                "type": "object",
                "properties": {
                    "module_filter": {"type": "string", "description": "Optional filter to only include functions from specific module"}
                },
                "required": []
            }
        ),
        Tool(
            name="analyze_sql_queries",
            description="Analyze SQL queries from traces to detect N+1 problems and slow queries.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        # Manim Tools
        Tool(
            name="manim_generate_video",
            description="Generate a Manim 3D animation video from trace data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "trace_file": {"type": "string", "description": "Path to trace JSON file (uses current trace if empty)"},
                    "quality": {"type": "string", "description": "Video quality - low_quality, medium_quality, high_quality", "default": "low_quality"},
                    "scene_type": {"type": "string", "description": "Type of visualization - execution_flow, architecture, error_propagation", "default": "execution_flow"}
                },
                "required": []
            }
        ),
        Tool(
            name="manim_list_videos",
            description="List all generated Manim videos.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        # Diagram Export Tools
        Tool(
            name="export_diagram",
            description="Export execution flow as a diagram (plantuml, mermaid, json).",
            inputSchema={
                "type": "object",
                "properties": {
                    "format": {"type": "string", "description": "Output format - plantuml, mermaid, json", "default": "plantuml"},
                    "output_file": {"type": "string", "description": "Output file path (auto-generated if empty)"}
                },
                "required": []
            }
        ),
        Tool(
            name="export_flamegraph",
            description="Export performance data as a flamegraph-compatible JSON for speedscope.app.",
            inputSchema={
                "type": "object",
                "properties": {
                    "output_file": {"type": "string", "description": "Output file path (auto-generated if empty)"}
                },
                "required": []
            }
        ),
        # AI Server Tools
        Tool(
            name="ai_server_start",
            description="Start the local AI server (llama.cpp) for code explanations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "model_path": {"type": "string", "description": "Path to GGUF model file (uses default if empty)"},
                    "port": {"type": "integer", "description": "Server port", "default": 8080}
                },
                "required": []
            }
        ),
        Tool(
            name="ai_server_stop",
            description="Stop the local AI server.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="ai_server_status",
            description="Check AI server status.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="ai_server_update",
            description="Update llama.cpp to latest build. Required for Qwen3.5 models (need b8148+).",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="ai_server_version",
            description="Get the installed llama.cpp build version number.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="ai_download_model",
            description="Download an AI model from HuggingFace. Presets: Qwen3-VL-2B-Instruct-Q4_K_XL (1.5GB), Qwen3-2B-Instruct-Q4_K_M (1.1GB), Qwen3.5-2B-Q4_K_M (1.28GB), Qwen3.5-4B-Q4_K_M (2.74GB)",
            inputSchema={
                "type": "object",
                "properties": {
                    "model_name": {"type": "string", "description": "Model preset name", "default": "Qwen3-VL-2B-Instruct-Q4_K_XL"}
                },
                "required": []
            }
        ),
        Tool(
            name="ai_explain_code",
            description="Ask the AI to explain code behavior using collected trace context.",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Your question about the code"},
                    "context_type": {"type": "string", "description": "Context to include: all, performance, dead_code, call_trace, none", "default": "all"}
                },
                "required": ["question"]
            }
        ),
        # Project Management Tools
        Tool(
            name="set_project_dir",
            description="Set the project directory for TrueFlow operations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Path to project directory"}
                },
                "required": ["directory"]
            }
        ),
        Tool(
            name="get_project_info",
            description="Get information about the current project.",
            inputSchema={"type": "object", "properties": {}, "required": []}
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> Sequence[TextContent]:
    """Handle tool calls."""
    try:
        if name == "trace_connect":
            result = await trace_connect(arguments.get("host", "127.0.0.1"), arguments.get("port", 5678))
        elif name == "trace_disconnect":
            result = await trace_disconnect()
        elif name == "trace_status":
            result = await trace_status()
        elif name == "trace_get_events":
            result = await trace_get_events(arguments.get("limit", 100), arguments.get("filter_module", ""), arguments.get("filter_function", ""))
        elif name == "trace_clear":
            result = await trace_clear()
        elif name == "analyze_dead_code":
            result = await analyze_dead_code(arguments.get("source_dir", "src/crawl4ai/embodied_ai"))
        elif name == "analyze_performance":
            result = await analyze_performance(arguments.get("sort_by", "total_ms"), arguments.get("limit", 20))
        elif name == "analyze_call_tree":
            result = await analyze_call_tree(arguments.get("root_function", ""), arguments.get("max_depth", 5))
        elif name == "explorer_get_callers":
            result = await explorer_get_callers(arguments.get("function_name", ""), arguments.get("max_depth", 3))
        elif name == "explorer_get_callees":
            result = await explorer_get_callees(arguments.get("function_name", ""), arguments.get("max_depth", 3))
        elif name == "explorer_search":
            result = await explorer_search(arguments.get("query", ""), arguments.get("search_type", "function"))
        elif name == "explorer_get_call_chain":
            result = await explorer_get_call_chain(arguments.get("function_name", ""), arguments.get("source_dir", "src/crawl4ai/embodied_ai"))
        elif name == "explorer_get_coverage_summary":
            result = await explorer_get_coverage_summary()
        elif name == "explorer_find_path":
            result = await explorer_find_path(arguments.get("source", ""), arguments.get("target", ""))
        elif name == "explorer_get_function_details":
            result = await explorer_get_function_details(arguments.get("function_name", ""))
        elif name == "explorer_get_hot_paths":
            result = await explorer_get_hot_paths(arguments.get("limit", 10))
        elif name == "explorer_get_call_graph":
            result = await explorer_get_call_graph(arguments.get("module_filter", ""))
        elif name == "analyze_sql_queries":
            result = await analyze_sql_queries()
        elif name == "manim_generate_video":
            result = await manim_generate_video(arguments.get("trace_file", ""), arguments.get("quality", "low_quality"), arguments.get("scene_type", "execution_flow"))
        elif name == "manim_list_videos":
            result = await manim_list_videos()
        elif name == "export_diagram":
            result = await export_diagram(arguments.get("format", "plantuml"), arguments.get("output_file", ""))
        elif name == "export_flamegraph":
            result = await export_flamegraph(arguments.get("output_file", ""))
        elif name == "ai_server_start":
            result = await ai_server_start(arguments.get("model_path", ""), arguments.get("port", 8080))
        elif name == "ai_server_stop":
            result = await ai_server_stop()
        elif name == "ai_server_status":
            result = await ai_server_status()
        elif name == "ai_server_update":
            result = await ai_server_update()
        elif name == "ai_server_version":
            result = await ai_server_version()
        elif name == "ai_download_model":
            result = await ai_download_model(arguments.get("model_name", "Qwen3-VL-2B-Instruct-Q4_K_XL"))
        elif name == "ai_explain_code":
            result = await ai_explain_code(arguments.get("question", ""), arguments.get("context_type", "all"))
        elif name == "set_project_dir":
            result = await set_project_dir(arguments.get("directory", ""))
        elif name == "get_project_info":
            result = await get_project_info()
        else:
            result = f"Unknown tool: {name}"
        return [TextContent(type="text", text=result)]
    except Exception as e:
        return [TextContent(type="text", text=f"Error in {name}: {str(e)}")]


# ============================================================================
# TRACE COLLECTION IMPLEMENTATIONS
# ============================================================================

async def trace_connect(host: str = "127.0.0.1", port: int = 5678) -> str:
    """Connect to trace server."""
    global state
    if state.trace_connected:
        return "Already connected to trace server"
    try:
        state.trace_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        state.trace_socket.settimeout(5.0)
        state.trace_socket.connect((host, port))
        state.trace_connected = True
        state.trace_events = []
        asyncio.create_task(_read_trace_events())
        return f"Connected to trace server at {host}:{port}"
    except Exception as e:
        state.trace_connected = False
        return f"Failed to connect: {str(e)}. Make sure the trace server is running."


async def trace_disconnect() -> str:
    """Disconnect from trace server."""
    global state
    if not state.trace_connected:
        return "Not connected to trace server"
    try:
        if state.trace_socket:
            state.trace_socket.close()
        state.trace_socket = None
        state.trace_connected = False
        return "Disconnected from trace server"
    except Exception as e:
        return f"Error disconnecting: {str(e)}"


async def trace_status() -> str:
    """Get trace collection status."""
    global state
    status = {
        "connected": state.trace_connected,
        "event_count": len(state.trace_events),
        "covered_functions": len(state.covered_functions),
        "call_graph_edges": sum(len(v) for v in state.call_graph.values()),
        "recent_events": state.trace_events[-5:] if state.trace_events else []
    }
    return json.dumps(status, indent=2)


async def trace_get_events(limit: int = 100, filter_module: str = "", filter_function: str = "") -> str:
    """Get collected trace events."""
    global state
    events = state.trace_events
    if filter_module:
        events = [e for e in events if filter_module.lower() in e.get("module", "").lower()]
    if filter_function:
        events = [e for e in events if filter_function.lower() in e.get("function", "").lower()]
    return json.dumps(events[-limit:], indent=2)


async def trace_clear() -> str:
    """Clear all trace data."""
    global state
    count = len(state.trace_events)
    state.trace_events = []
    state.performance_data = {}
    state.dead_code_data = {}
    state.call_trace_data = []
    state.call_graph = {}
    state.reverse_call_graph = {}
    state.covered_functions = set()
    state._call_stack = []
    return f"Cleared {count} trace events and all analytics"


async def _read_trace_events():
    """Background task to read trace events from socket."""
    global state
    buffer = ""
    while state.trace_connected and state.trace_socket:
        try:
            data = state.trace_socket.recv(4096).decode('utf-8')
            if not data:
                break
            buffer += data
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                if line.strip():
                    try:
                        event = json.loads(line)
                        state.trace_events.append(event)
                        _update_analytics(event)
                    except json.JSONDecodeError:
                        pass
        except socket.timeout:
            continue
        except Exception as e:
            logger.error(f"Error reading trace events: {e}")
            break
    state.trace_connected = False


def _update_analytics(event: dict):
    """Update performance and call graph from event."""
    global state
    func_key = f"{event.get('module', 'unknown')}.{event.get('function', 'unknown')}"
    event_type = event.get("type", "")
    call_id = event.get("call_id")

    if func_key not in state.performance_data:
        state.performance_data[func_key] = {
            "calls": 0, "total_ms": 0, "min_ms": float('inf'), "max_ms": 0,
            "file": event.get("file", ""), "line": event.get("line", 0)
        }

    if func_key not in state.function_info:
        state.function_info[func_key] = {
            "file": event.get("file", ""), "line": event.get("line", 0), "module": event.get("module", "unknown")
        }

    perf = state.performance_data[func_key]

    if event_type == "call":
        perf["calls"] += 1
        state.covered_functions.add(func_key)
        if state._call_stack:
            caller = state._call_stack[-1][1]
            if caller not in state.call_graph:
                state.call_graph[caller] = []
            if func_key not in state.call_graph[caller]:
                state.call_graph[caller].append(func_key)
            if func_key not in state.reverse_call_graph:
                state.reverse_call_graph[func_key] = []
            if caller not in state.reverse_call_graph[func_key]:
                state.reverse_call_graph[func_key].append(caller)
        state._call_stack.append((call_id, func_key))

    elif event_type == "return":
        if "duration_ms" in event:
            duration = event["duration_ms"]
            perf["total_ms"] += duration
            perf["min_ms"] = min(perf["min_ms"], duration)
            perf["max_ms"] = max(perf["max_ms"], duration)
        if state._call_stack and state._call_stack[-1][0] == call_id:
            state._call_stack.pop()


# ============================================================================
# ANALYSIS IMPLEMENTATIONS
# ============================================================================

async def analyze_dead_code(source_dir: str = "src/crawl4ai/embodied_ai") -> str:
    """Analyze dead code comparing static AST with runtime coverage."""
    global state
    source_path = state.project_dir / source_dir

    if not source_path.exists():
        return f"Source directory not found: {source_path}"

    # Static analysis - get all defined functions
    defined_functions = set()
    defined_classes = set()
    file_definitions = {}

    for py_file in source_path.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        try:
            content = py_file.read_text(encoding='utf-8')
            tree = ast.parse(content)
            rel_path = py_file.relative_to(source_path.parent)
            module_name = str(rel_path).replace(os.sep, '.').replace('/', '.').replace('.py', '')

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    full_name = f"{module_name}.{node.name}"
                    defined_classes.add(full_name)
                    file_definitions[full_name] = {"file": str(py_file), "line": node.lineno}

                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    full_name = f"{module_name}.{node.name}"
                    defined_functions.add(full_name)
                    file_definitions[full_name] = {"file": str(py_file), "line": node.lineno}
        except Exception as e:
            logger.warning(f"Error parsing {py_file}: {e}")

    # Compare with runtime coverage
    runtime_covered = state.covered_functions if state.covered_functions else set()

    # Find dead code
    dead_functions = []
    for func in defined_functions:
        func_name = func.split('.')[-1]
        if func_name.startswith('_'):
            continue  # Skip private
        # Check if covered in runtime
        is_covered = any(func_name in covered for covered in runtime_covered)
        if not is_covered:
            info = file_definitions.get(func, {})
            dead_functions.append({
                "function": func,
                "file": info.get("file", "unknown"),
                "line": info.get("line", 0)
            })

    # Build result
    result = {
        "source_dir": str(source_path),
        "static_analysis": {
            "total_functions": len(defined_functions),
            "total_classes": len(defined_classes)
        },
        "runtime_coverage": {
            "connected": state.trace_connected,
            "covered_functions": len(runtime_covered),
            "coverage_percent": round(len(runtime_covered) / len(defined_functions) * 100, 1) if defined_functions else 0
        },
        "dead_functions_count": len(dead_functions),
        "dead_functions": dead_functions,
        "note": "Connect to trace server and run code to improve accuracy" if not state.trace_connected else "Based on runtime execution data"
    }

    return json.dumps(result, indent=2)


async def analyze_performance(sort_by: str = "total_ms", limit: int = 20) -> str:
    """Analyze performance from trace data."""
    global state
    if not state.performance_data:
        return json.dumps({"error": "No performance data. Connect to trace server first."})

    results = []
    for func, data in state.performance_data.items():
        avg_ms = data["total_ms"] / data["calls"] if data["calls"] > 0 else 0
        results.append({
            "function": func,
            "calls": data["calls"],
            "total_ms": round(data["total_ms"], 2),
            "avg_ms": round(avg_ms, 2),
            "min_ms": round(data["min_ms"], 2) if data["min_ms"] != float('inf') else 0,
            "max_ms": round(data["max_ms"], 2),
            "file": data["file"],
            "line": data["line"]
        })

    results.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
    return json.dumps({"total_functions": len(results), "sort_by": sort_by, "hotspots": results[:limit]}, indent=2)


async def analyze_call_tree(root_function: str = "", max_depth: int = 5) -> str:
    """Generate call tree from trace data."""
    global state
    if not state.call_trace_data and not state.call_graph:
        return json.dumps({"error": "No call trace data. Connect and collect traces first."})

    # Find entry points
    entry_points = [f for f in state.covered_functions if f not in state.reverse_call_graph or not state.reverse_call_graph[f]]

    def build_tree(func: str, depth: int, visited: set) -> dict:
        if depth > max_depth or func in visited:
            return {"function": func, "truncated": True}
        visited.add(func)
        children = state.call_graph.get(func, [])
        return {
            "function": func,
            "calls": state.performance_data.get(func, {}).get("calls", 0),
            "children": [build_tree(c, depth + 1, visited.copy()) for c in children[:10]]
        }

    if root_function:
        matching = [f for f in state.covered_functions if root_function.lower() in f.lower()]
        if matching:
            tree = [build_tree(matching[0], 0, set())]
        else:
            tree = []
    else:
        tree = [build_tree(ep, 0, set()) for ep in entry_points[:5]]

    return json.dumps({"entry_points": entry_points[:20], "tree": tree}, indent=2)


# ============================================================================
# EXPLORER IMPLEMENTATIONS
# ============================================================================

def _find_matching_function(name: str) -> str:
    """Find matching function in covered functions."""
    if name in state.covered_functions:
        return name
    for func in state.covered_functions:
        if name.lower() in func.lower():
            return func
    return ""


async def explorer_get_callers(function_name: str, max_depth: int = 3) -> str:
    """Get all callers of a function."""
    global state

    # Also build from static analysis if no runtime data
    if not state.reverse_call_graph:
        call_graph, reverse_graph, func_info = build_call_graph_static("src/crawl4ai/embodied_ai")
    else:
        reverse_graph = state.reverse_call_graph
        func_info = state.function_info

    # Find matching functions
    matches = [f for f in func_info.keys() if function_name.lower() in f.lower()]
    if not matches:
        return json.dumps({"error": f"Function '{function_name}' not found"})

    results = []
    for func in matches[:5]:
        def trace_up(target: str, depth: int, visited: set) -> list:
            if depth > max_depth or target in visited:
                return []
            visited.add(target)
            callers = reverse_graph.get(target, []) or reverse_graph.get(target.split('.')[-1], [])
            result = []
            for caller in callers[:10]:
                result.append({"caller": caller, "depth": depth, "callers": trace_up(caller, depth + 1, visited.copy())})
            return result

        callers = reverse_graph.get(func, []) or reverse_graph.get(func.split('.')[-1], [])
        results.append({
            "function": func,
            "file": func_info.get(func, {}).get("file", "unknown"),
            "direct_callers": callers[:20],
            "caller_tree": trace_up(func, 1, set())
        })

    return json.dumps({"matches": results, "total": len(matches)}, indent=2)


async def explorer_get_callees(function_name: str, max_depth: int = 3) -> str:
    """Get all callees of a function."""
    global state

    if not state.call_graph:
        call_graph, reverse_graph, func_info = build_call_graph_static("src/crawl4ai/embodied_ai")
    else:
        call_graph = state.call_graph
        func_info = state.function_info

    matches = [f for f in func_info.keys() if function_name.lower() in f.lower()]
    if not matches:
        return json.dumps({"error": f"Function '{function_name}' not found"})

    results = []
    for func in matches[:5]:
        def trace_down(source: str, depth: int, visited: set) -> list:
            if depth > max_depth or source in visited:
                return []
            visited.add(source)
            callees = call_graph.get(source, [])
            result = []
            for callee in callees[:10]:
                result.append({"callee": callee, "depth": depth, "callees": trace_down(callee, depth + 1, visited.copy())})
            return result

        callees = call_graph.get(func, [])
        results.append({
            "function": func,
            "file": func_info.get(func, {}).get("file", "unknown"),
            "direct_callees": callees[:30],
            "callee_tree": trace_down(func, 1, set())
        })

    return json.dumps({"matches": results, "total": len(matches)}, indent=2)


async def explorer_search(query: str, search_type: str = "function") -> str:
    """Search for functions by pattern."""
    global state

    if not state.function_info:
        _, _, func_info = build_call_graph_static("src/crawl4ai/embodied_ai")
    else:
        func_info = state.function_info

    results = []
    query_lower = query.lower()

    for func_key, info in func_info.items():
        match = False
        if search_type in ["function", "all"] and query_lower in func_key.split('.')[-1].lower():
            match = True
        if search_type in ["module", "all"] and query_lower in func_key.rsplit('.', 1)[0].lower():
            match = True
        if search_type in ["file", "all"] and query_lower in info.get("file", "").lower():
            match = True

        if match:
            callers = state.reverse_call_graph.get(func_key, [])
            callees = state.call_graph.get(func_key, [])
            results.append({
                "function": func_key,
                "file": info.get("file", "unknown"),
                "line": info.get("line", 0),
                "callers_count": len(callers),
                "callees_count": len(callees),
                "is_dead": len(callers) == 0 and not func_key.split('.')[-1].startswith('_'),
                "is_covered": func_key in state.covered_functions
            })

    results.sort(key=lambda x: (-x.get("callers_count", 0), x["function"]))
    return json.dumps({"query": query, "results": results[:50], "total": len(results)}, indent=2)


async def explorer_get_call_chain(function_name: str, source_dir: str = "src/crawl4ai/embodied_ai") -> str:
    """Get complete call chain for a function."""
    global state

    if not state.call_graph:
        call_graph, reverse_graph, func_info = build_call_graph_static(source_dir)
    else:
        call_graph = state.call_graph
        reverse_graph = state.reverse_call_graph
        func_info = state.function_info

    matches = [f for f in func_info.keys() if function_name.lower() in f.lower()]
    if not matches:
        return json.dumps({"error": f"Function '{function_name}' not found"})

    func = matches[0]

    def trace_up(target: str, visited: set) -> list:
        if target in visited:
            return []
        visited.add(target)
        callers = reverse_graph.get(target, []) or reverse_graph.get(target.split('.')[-1], [])
        result = list(callers)
        for caller in callers:
            result.extend(trace_up(caller, visited.copy()))
        return list(set(result))

    def trace_down(source: str, visited: set) -> list:
        if source in visited:
            return []
        visited.add(source)
        callees = call_graph.get(source, [])
        result = list(callees)
        for callee in callees:
            result.extend(trace_down(callee, visited.copy()))
        return list(set(result))

    upstream = trace_up(func, set())
    downstream = trace_down(func, set())
    root_callers = [f for f in upstream if not reverse_graph.get(f, [])]

    return json.dumps({
        "function": func,
        "file": func_info.get(func, {}).get("file", "unknown"),
        "upstream": {"all_callers": upstream[:50], "root_callers": root_callers[:10], "total": len(upstream)},
        "downstream": {"all_callees": downstream[:50], "total": len(downstream)},
        "is_dead": len(upstream) == 0 and not func.split('.')[-1].startswith('_')
    }, indent=2)


async def explorer_get_coverage_summary() -> str:
    """Get coverage summary from trace data."""
    global state

    if not state.covered_functions:
        return json.dumps({"error": "No coverage data. Connect to trace server and run code first."})

    modules = {}
    for func in state.covered_functions:
        module = func.rsplit('.', 1)[0] if '.' in func else "unknown"
        if module not in modules:
            modules[module] = {"count": 0, "total_ms": 0}
        modules[module]["count"] += 1
        modules[module]["total_ms"] += state.performance_data.get(func, {}).get("total_ms", 0)

    entry_points = [f for f in state.covered_functions if f not in state.reverse_call_graph]

    return json.dumps({
        "summary": {
            "total_covered": len(state.covered_functions),
            "total_calls": sum(d.get("calls", 0) for d in state.performance_data.values()),
            "total_ms": round(sum(d.get("total_ms", 0) for d in state.performance_data.values()), 2),
            "modules_count": len(modules),
            "entry_points_count": len(entry_points)
        },
        "entry_points": entry_points[:20],
        "modules": [{"module": m, **d} for m, d in sorted(modules.items(), key=lambda x: -x[1]["count"])][:20]
    }, indent=2)


async def explorer_find_path(source: str, target: str) -> str:
    """Find call path between two functions."""
    global state

    if not state.call_graph:
        call_graph, reverse_graph, func_info = build_call_graph_static("src/crawl4ai/embodied_ai")
    else:
        call_graph = state.call_graph
        func_info = state.function_info

    source_func = next((f for f in func_info if source.lower() in f.lower()), None)
    target_func = next((f for f in func_info if target.lower() in f.lower()), None)

    if not source_func:
        return json.dumps({"error": f"Source '{source}' not found"})
    if not target_func:
        return json.dumps({"error": f"Target '{target}' not found"})

    # BFS for path
    queue = [(source_func, [source_func])]
    visited = {source_func}

    while queue:
        current, path = queue.pop(0)
        if current == target_func:
            return json.dumps({
                "source": source_func, "target": target_func,
                "path": path, "length": len(path) - 1,
                "path_string": " -> ".join(path)
            }, indent=2)
        for callee in call_graph.get(current, []):
            if callee not in visited:
                visited.add(callee)
                queue.append((callee, path + [callee]))

    return json.dumps({"source": source_func, "target": target_func, "reachable": False, "message": "No path found"}, indent=2)


async def explorer_get_function_details(function_name: str) -> str:
    """Get detailed information about a specific function."""
    global state

    if not state.call_graph and not state.performance_data:
        build_call_graph_static("src/crawl4ai/embodied_ai")

    matches = []
    for func_key in state.function_info.keys():
        if function_name.lower() in func_key.lower():
            perf_data = state.performance_data.get(func_key, {})
            func_info = state.function_info.get(func_key, {})
            callees = state.call_graph.get(func_key, [])
            callers = state.reverse_call_graph.get(func_key, [])
            avg_ms = perf_data.get("total_ms", 0) / perf_data.get("calls", 1) if perf_data.get("calls", 0) > 0 else 0

            matches.append({
                "function": func_key,
                "file": func_info.get("file", perf_data.get("file", "unknown")),
                "line": func_info.get("line", perf_data.get("line", 0)),
                "module": func_info.get("module", ""),
                "calls": perf_data.get("calls", 0),
                "total_ms": round(perf_data.get("total_ms", 0), 2),
                "avg_ms": round(avg_ms, 2),
                "max_ms": round(perf_data.get("max_ms", 0), 2),
                "callees": callees[:20],
                "callers": callers[:20],
                "callees_count": len(callees),
                "callers_count": len(callers),
                "is_entry_point": len(callers) == 0,
                "is_covered": func_key in state.covered_functions
            })

    if not matches:
        return json.dumps({"error": f"No function matching '{function_name}' found"})

    matches.sort(key=lambda x: x["calls"], reverse=True)
    return json.dumps({"query": function_name, "matches": matches[:10], "total_matches": len(matches)}, indent=2)


async def explorer_get_hot_paths(limit: int = 10) -> str:
    """Get the most frequently executed code paths."""
    global state

    if not state.call_graph:
        build_call_graph_static("src/crawl4ai/embodied_ai")

    entry_points = [f for f in state.covered_functions if not state.reverse_call_graph.get(f, [])]
    paths = []

    for entry in entry_points[:20]:
        def collect_paths(func: str, current_path: list, visited: set):
            if func in visited or len(current_path) > 10:
                return
            visited.add(func)
            current_path.append(func)

            callees = state.call_graph.get(func, [])
            if not callees:
                path_total_ms = sum(state.performance_data.get(f, {}).get("total_ms", 0) for f in current_path)
                path_min_calls = min((state.performance_data.get(f, {}).get("calls", 0) for f in current_path), default=0)
                paths.append({
                    "entry_point": entry,
                    "path": " -> ".join(current_path[:5]) + ("..." if len(current_path) > 5 else ""),
                    "functions": current_path.copy(),
                    "depth": len(current_path),
                    "path_total_ms": round(path_total_ms, 2),
                    "min_calls_in_path": path_min_calls
                })
            else:
                for callee in callees[:5]:
                    collect_paths(callee, current_path.copy(), visited.copy())

        collect_paths(entry, [], set())

    paths.sort(key=lambda x: x["min_calls_in_path"], reverse=True)
    return json.dumps({"hot_paths": paths[:limit], "total_paths": len(paths), "entry_points": entry_points[:20]}, indent=2)


async def explorer_get_call_graph(module_filter: str = "") -> str:
    """Get the full call graph structure."""
    global state

    if not state.call_graph:
        build_call_graph_static("src/crawl4ai/embodied_ai")

    if module_filter:
        filter_lower = module_filter.lower()
        filtered_call_graph = {
            caller: [c for c in callees if filter_lower in c.lower()]
            for caller, callees in state.call_graph.items()
            if filter_lower in caller.lower()
        }
        filtered_reverse = {
            callee: [c for c in callers if filter_lower in c.lower()]
            for callee, callers in state.reverse_call_graph.items()
            if filter_lower in callee.lower()
        }
        filtered_functions = [f for f in state.function_info.keys() if filter_lower in f.lower()]
    else:
        filtered_call_graph = dict(state.call_graph)
        filtered_reverse = dict(state.reverse_call_graph)
        filtered_functions = list(state.function_info.keys())

    entry_points = [f for f in filtered_functions if f not in filtered_reverse or not filtered_reverse[f]]
    leaf_nodes = [f for f in filtered_functions if f not in filtered_call_graph or not filtered_call_graph[f]]

    return json.dumps({
        "call_graph": {k: v for k, v in list(filtered_call_graph.items())[:100]},
        "reverse_call_graph": {k: v for k, v in list(filtered_reverse.items())[:100]},
        "functions": filtered_functions[:100],
        "total_functions": len(filtered_functions),
        "total_edges": sum(len(v) for v in filtered_call_graph.values()),
        "entry_points": entry_points[:20],
        "leaf_nodes": leaf_nodes[:20],
        "module_filter": module_filter or "none"
    }, indent=2)


async def analyze_sql_queries() -> str:
    """Analyze SQL queries from traces to detect N+1 problems."""
    global state

    sql_events = [e for e in state.trace_events if
                  'sql' in e.get('function', '').lower() or
                  'query' in e.get('function', '').lower() or
                  'execute' in e.get('function', '').lower() or
                  e.get('trace_data', {}).get('type') == 'sql']

    if not sql_events:
        return json.dumps({
            "status": "No SQL queries detected in traces",
            "hint": "Ensure database operations are being traced"
        })

    query_patterns = {}
    for event in sql_events:
        pattern = event.get('function', 'unknown')
        if pattern not in query_patterns:
            query_patterns[pattern] = {"count": 0, "total_ms": 0}
        query_patterns[pattern]["count"] += 1
        query_patterns[pattern]["total_ms"] += event.get("duration_ms", 0)

    n_plus_1 = [{"pattern": p, **data} for p, data in query_patterns.items() if data["count"] > 10]

    return json.dumps({
        "total_queries": len(sql_events),
        "unique_patterns": len(query_patterns),
        "potential_n_plus_1": n_plus_1,
        "all_patterns": query_patterns
    }, indent=2)


# ============================================================================
# MANIM VIDEO IMPLEMENTATIONS
# ============================================================================

async def manim_generate_video(trace_file: str = "", quality: str = "low_quality", scene_type: str = "execution_flow") -> str:
    """Generate a Manim 3D animation video from trace data."""
    global state

    plugin_dir = state.project_dir / ".pycharm_plugin" / "runtime_injector"
    visualizer_script = plugin_dir / "ultimate_architecture_viz.py"

    if not visualizer_script.exists():
        alt_paths = [
            state.project_dir / "pycharm-plugin" / "runtime_injector" / "ultimate_architecture_viz.py",
            Path(__file__).parent / "ultimate_architecture_viz.py"
        ]
        for alt in alt_paths:
            if alt.exists():
                visualizer_script = alt
                break
        else:
            return "Manim visualizer not found. Ensure TrueFlow is properly installed."

    if not trace_file:
        traces_dir = state.project_dir / ".pycharm_plugin" / "manim" / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trace_file = str(traces_dir / f"trace_{timestamp}.json")
        with open(trace_file, 'w') as f:
            json.dump({
                "events": state.trace_events[-500:],
                "performance": state.performance_data,
                "timestamp": timestamp
            }, f, indent=2)

    try:
        cmd = [
            sys.executable, "-c",
            f"""
import sys
sys.path.insert(0, '{visualizer_script.parent}')
from ultimate_architecture_viz import UltimateArchitectureScene
from manim import config

config.quality = '{quality}'
config.preview = False
config.media_dir = '{state.project_dir / ".pycharm_plugin" / "manim" / "media"}'

scene = UltimateArchitectureScene(trace_file='{trace_file}')
scene.render()
print('VIDEO_PATH:', config.get_output_dir())
"""
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'VIDEO_PATH:' in line:
                    video_dir = line.split('VIDEO_PATH:')[1].strip()
                    state.manim_videos.append(video_dir)
                    return f"Video generated successfully at: {video_dir}"
            return f"Video rendered. Output: {result.stdout}"
        else:
            return f"Manim error: {result.stderr}"

    except subprocess.TimeoutExpired:
        return "Video generation timed out (5 min limit)"
    except Exception as e:
        return f"Error generating video: {str(e)}"


async def manim_list_videos() -> str:
    """List all generated Manim videos."""
    global state

    media_dir = state.project_dir / ".pycharm_plugin" / "manim" / "media" / "videos"

    videos = []
    if media_dir.exists():
        for video_file in media_dir.rglob("*.mp4"):
            stat = video_file.stat()
            videos.append({
                "path": str(video_file),
                "name": video_file.name,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat()
            })

    return json.dumps(videos, indent=2)


# ============================================================================
# DIAGRAM EXPORT IMPLEMENTATIONS
# ============================================================================

async def export_diagram(format: str = "plantuml", output_file: str = "") -> str:
    """Export execution flow as a diagram."""
    global state

    if not state.trace_events:
        return "No trace events to export. Collect traces first."

    modules = set()
    for event in state.trace_events[:200]:
        modules.add(event.get("module", "unknown"))

    if format == "plantuml":
        lines = ["@startuml", "autonumber"]
        for mod in modules:
            lines.append(f'participant "{mod}" as {mod.replace(".", "_")}')
        lines.append("")

        for event in state.trace_events[:100]:
            if event.get("type") == "call":
                caller = event.get("parent_module", "Main").replace(".", "_")
                callee = event.get("module", "unknown").replace(".", "_")
                func = event.get("function", "unknown")
                lines.append(f"{caller} -> {callee}: {func}()")

        lines.append("@enduml")
        content = "\n".join(lines)

    elif format == "mermaid":
        lines = ["sequenceDiagram", "    autonumber"]
        for mod in modules:
            lines.append(f"    participant {mod.replace('.', '_')}")

        for event in state.trace_events[:100]:
            if event.get("type") == "call":
                caller = event.get("parent_module", "Main").replace(".", "_")
                callee = event.get("module", "unknown").replace(".", "_")
                func = event.get("function", "unknown")
                lines.append(f"    {caller}->>+{callee}: {func}()")

        content = "\n".join(lines)
    else:
        content = json.dumps(state.trace_events[:200], indent=2)

    if output_file:
        output_path = Path(output_file)
    else:
        ext = {"plantuml": ".puml", "mermaid": ".md", "json": ".json"}[format]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = state.project_dir / "traces" / f"diagram_{timestamp}{ext}"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(content)

    return f"Diagram exported to: {output_path}"


async def export_flamegraph(output_file: str = "") -> str:
    """Export performance data as a flamegraph-compatible JSON."""
    global state

    if not state.performance_data:
        return "No performance data. Collect traces first."

    flamegraph_data = {
        "shared": {"frames": []},
        "profiles": [{
            "type": "sampled",
            "name": "TrueFlow Trace",
            "unit": "milliseconds",
            "startValue": 0,
            "endValue": sum(d["total_ms"] for d in state.performance_data.values()),
            "samples": [],
            "weights": []
        }]
    }

    for i, (func, data) in enumerate(state.performance_data.items()):
        flamegraph_data["shared"]["frames"].append({
            "name": func,
            "file": data.get("file", ""),
            "line": data.get("line", 0)
        })
        flamegraph_data["profiles"][0]["samples"].append([i])
        flamegraph_data["profiles"][0]["weights"].append(data["total_ms"])

    if output_file:
        output_path = Path(output_file)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = state.project_dir / "traces" / f"flamegraph_{timestamp}.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(flamegraph_data, f, indent=2)

    return f"Flamegraph exported to: {output_path}\nOpen at https://speedscope.app"


# ============================================================================
# AI SERVER IMPLEMENTATIONS
# ============================================================================

async def ai_server_start(model_path: str = "", port: int = 8080) -> str:
    """Start the local AI server."""
    global state

    if state.ai_server_process and state.ai_server_process.poll() is None:
        return "AI server is already running"

    home = Path.home()
    possible_paths = [
        home / ".trueflow" / "llama.cpp" / "build" / "bin" / "Release" / "llama-server.exe",
        home / ".trueflow" / "llama.cpp" / "build" / "bin" / "llama-server",
    ]

    llama_server = None
    for p in possible_paths:
        if p.exists():
            llama_server = p
            break

    if not llama_server:
        return "llama-server not found. Install llama.cpp first."

    if not model_path:
        models_dir = home / ".trueflow" / "models"
        if models_dir.exists():
            for gguf in models_dir.glob("*.gguf"):
                model_path = str(gguf)
                break

    if not model_path:
        return "No model found. Download a model first."

    try:
        cmd = [
            str(llama_server),
            "--model", model_path,
            "--port", str(port),
            "--ctx-size", "4096",
            "--host", "127.0.0.1"
        ]

        state.ai_server_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        for _ in range(30):
            time.sleep(1)
            try:
                import urllib.request
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
                return f"AI server started on port {port}"
            except:
                continue

        return f"AI server started but may still be loading. Check http://127.0.0.1:{port}/health"

    except Exception as e:
        return f"Failed to start AI server: {str(e)}"


async def ai_server_stop() -> str:
    """Stop the local AI server."""
    global state

    if not state.ai_server_process:
        return "AI server is not running"

    try:
        state.ai_server_process.terminate()
        state.ai_server_process.wait(timeout=5)
        state.ai_server_process = None
        return "AI server stopped"
    except Exception as e:
        return f"Error stopping server: {str(e)}"


async def ai_server_status() -> str:
    """Check AI server status."""
    global state

    running = state.ai_server_process and state.ai_server_process.poll() is None

    health = "unknown"
    if running:
        try:
            import urllib.request
            response = urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2)
            health = "healthy" if response.status == 200 else "unhealthy"
        except:
            health = "not responding"

    return json.dumps({
        "running": running,
        "health": health,
        "pid": state.ai_server_process.pid if running else None
    }, indent=2)


async def ai_server_update() -> str:
    """Update llama.cpp to the latest build."""
    try:
        from local_llm_server import LlamaCppServer
        server = LlamaCppServer()
        old_ver = server.get_version()

        messages = []
        def on_progress(msg, pct):
            messages.append(f"{msg} ({pct:.0f}%)")

        success = server.update_llama_cpp(progress_callback=on_progress)
        if success:
            new_ver = server.get_version()
            ver_msg = f"b{old_ver} → b{new_ver}" if old_ver and new_ver else "complete"
            return f"Update {ver_msg}. Steps: {'; '.join(messages[-3:])}"
        else:
            return f"Update failed. Log: {'; '.join(messages[-3:])}"
    except Exception as e:
        return f"Update failed: {str(e)}"


async def ai_server_version() -> str:
    """Get the installed llama.cpp build version."""
    try:
        from local_llm_server import LlamaCppServer
        server = LlamaCppServer()
        ver = server.get_version()
        if ver:
            return json.dumps({"build": ver, "build_tag": f"b{ver}"}, indent=2)
        else:
            return json.dumps({"build": None, "message": "llama.cpp not installed or version unknown"}, indent=2)
    except Exception as e:
        return f"Error checking version: {str(e)}"


async def ai_download_model(model_name: str = "Qwen3-VL-2B-Instruct-Q4_K_XL") -> str:
    """Download an AI model from HuggingFace."""
    MODEL_PRESETS = {
        "Qwen3-VL-2B-Instruct-Q4_K_XL": {
            "repo": "unsloth/Qwen3-VL-2B-Instruct-GGUF",
            "file": "Qwen3-VL-2B-Instruct-UD-Q4_K_XL.gguf"
        },
        "Qwen3-VL-2B-Thinking-Q4_K_XL": {
            "repo": "unsloth/Qwen3-VL-2B-Thinking-GGUF",
            "file": "Qwen3-VL-2B-Thinking-UD-Q4_K_XL.gguf"
        },
        "Qwen3-VL-4B-Instruct-Q4_K_XL": {
            "repo": "unsloth/Qwen3-VL-4B-Instruct-GGUF",
            "file": "Qwen3-VL-4B-Instruct-UD-Q4_K_XL.gguf"
        },
        "Qwen3-2B-Instruct-Q4_K_M": {
            "repo": "unsloth/Qwen3-2B-Instruct-GGUF",
            "file": "Qwen3-2B-Instruct-Q4_K_M.gguf"
        },
        "Qwen3.5-2B-UD-Q4_K_XL": {
            "repo": "unsloth/Qwen3.5-2B-GGUF",
            "file": "Qwen3.5-2B-UD-Q4_K_XL.gguf"
        },
        "Qwen3.5-4B-UD-Q4_K_XL": {
            "repo": "unsloth/Qwen3.5-4B-GGUF",
            "file": "Qwen3.5-4B-UD-Q4_K_XL.gguf"
        }
    }

    if model_name not in MODEL_PRESETS:
        return f"Unknown model. Available: {', '.join(MODEL_PRESETS.keys())}"

    preset = MODEL_PRESETS[model_name]
    url = f"https://huggingface.co/{preset['repo']}/resolve/main/{preset['file']}"

    models_dir = Path.home() / ".trueflow" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    dest_path = models_dir / preset['file']

    if dest_path.exists():
        return f"Model already downloaded at: {dest_path}"

    try:
        import urllib.request
        logger.info(f"Downloading {model_name}...")
        urllib.request.urlretrieve(url, dest_path)
        return f"Model downloaded to: {dest_path}"
    except Exception as e:
        return f"Download failed: {str(e)}"


async def ai_explain_code(question: str, context_type: str = "all") -> str:
    """Ask the AI to explain code behavior using trace context."""
    global state

    context = ""
    if context_type in ["all", "performance"]:
        if state.performance_data:
            context += "\n--- Performance Hotspots ---\n"
            for func, data in sorted(state.performance_data.items(),
                                    key=lambda x: x[1]["total_ms"], reverse=True)[:10]:
                context += f"  {func}: {data['calls']} calls, {data['total_ms']:.1f}ms total\n"

    if context_type in ["all", "dead_code"]:
        if state.dead_code_data:
            context += f"\n--- Dead Code ({state.dead_code_data.get('dead_count', 0)} functions) ---\n"
            for func in state.dead_code_data.get("dead_functions", [])[:10]:
                context += f"  - {func}\n"

    if context_type in ["all", "call_trace"]:
        if state.call_graph:
            context += "\n--- Active Call Graph ---\n"
            context += f"  Functions: {len(state.function_info)}, Edges: {sum(len(v) for v in state.call_graph.values())}\n"
            entry_points = [f for f in state.covered_functions if not state.reverse_call_graph.get(f, [])]
            context += f"  Entry points: {', '.join(entry_points[:5])}\n"

    try:
        import urllib.request

        payload = json.dumps({
            "model": "qwen3-vl",
            "messages": [
                {"role": "system", "content": "You are TrueFlow AI, a code analysis assistant. Analyze the execution trace context and answer the developer's question."},
                {"role": "user", "content": f"{question}\n{context}" if context else question}
            ],
            "max_tokens": 1024,
            "temperature": 0.7
        }).encode('utf-8')

        req = urllib.request.Request(
            "http://127.0.0.1:8080/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        response = urllib.request.urlopen(req, timeout=120)
        result = json.loads(response.read().decode('utf-8'))
        return result["choices"][0]["message"]["content"]

    except Exception as e:
        return f"AI server error: {str(e)}. Start server with ai_server_start first.\n\nContext that would be sent:\n{context}"


# ============================================================================
# PROJECT MANAGEMENT IMPLEMENTATIONS
# ============================================================================

async def set_project_dir(directory: str) -> str:
    """Set the project directory for TrueFlow operations."""
    global state

    path = Path(directory).resolve()
    if not path.exists():
        return f"Directory does not exist: {directory}"

    state.project_dir = path
    return f"Project directory set to: {state.project_dir}"


async def get_project_info() -> str:
    """Get information about the current project."""
    global state

    info = {
        "project_dir": str(state.project_dir),
        "plugin_dir": str(state.project_dir / ".pycharm_plugin"),
        "plugin_exists": (state.project_dir / ".pycharm_plugin").exists(),
        "traces_dir": str(state.project_dir / "traces"),
        "traces_exist": (state.project_dir / "traces").exists(),
        "trace_files": []
    }

    traces_dir = state.project_dir / "traces"
    if traces_dir.exists():
        info["trace_files"] = [f.name for f in traces_dir.glob("*.json")][:20]

    return json.dumps(info, indent=2)


# ============================================================================
# STATIC ANALYSIS HELPER
# ============================================================================

def build_call_graph_static(source_dir: str) -> tuple:
    """Build call graph from static AST analysis."""
    source_path = state.project_dir / source_dir
    call_graph = {}
    reverse_graph = {}
    function_info = {}

    for py_file in source_path.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        try:
            content = py_file.read_text(encoding='utf-8')
            tree = ast.parse(content)
            rel_path = py_file.relative_to(source_path.parent)
            module_name = str(rel_path).replace(os.sep, '.').replace('/', '.').replace('.py', '')

            class CallVisitor(ast.NodeVisitor):
                def __init__(self):
                    self.current_func = None
                    self.current_class = None

                def visit_ClassDef(self, node):
                    old = self.current_class
                    self.current_class = node.name
                    self.generic_visit(node)
                    self.current_class = old

                def visit_FunctionDef(self, node):
                    old = self.current_func
                    if self.current_class:
                        self.current_func = f"{module_name}.{self.current_class}.{node.name}"
                    else:
                        self.current_func = f"{module_name}.{node.name}"
                    function_info[self.current_func] = {"file": str(py_file), "line": node.lineno, "module": module_name}
                    if self.current_func not in call_graph:
                        call_graph[self.current_func] = []
                    self.generic_visit(node)
                    self.current_func = old

                visit_AsyncFunctionDef = visit_FunctionDef

                def visit_Call(self, node):
                    if self.current_func:
                        callee = None
                        if isinstance(node.func, ast.Name):
                            callee = node.func.id
                        elif isinstance(node.func, ast.Attribute):
                            callee = node.func.attr
                        if callee:
                            call_graph[self.current_func].append(callee)
                            if callee not in reverse_graph:
                                reverse_graph[callee] = []
                            reverse_graph[callee].append(self.current_func)
                    self.generic_visit(node)

            CallVisitor().visit(tree)
        except Exception as e:
            logger.debug(f"Error parsing {py_file}: {e}")

    # Update global state
    state.call_graph = call_graph
    state.reverse_call_graph = reverse_graph
    state.function_info = function_info

    return call_graph, reverse_graph, function_info


# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Run the MCP server."""
    logger.info("Starting TrueFlow MCP Server (Claude-compatible)...")
    logger.info(f"Project directory: {state.project_dir}")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
