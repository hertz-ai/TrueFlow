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
"""

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
from typing import Any, Optional

# MCP SDK imports
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent, Resource, ResourceTemplate
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
    project_dir: Path = field(default_factory=lambda: Path.cwd())
    trace_socket: Optional[socket.socket] = None
    trace_connected: bool = False
    trace_events: list = field(default_factory=list)
    ai_server_process: Optional[subprocess.Popen] = None
    manim_videos: list = field(default_factory=list)
    performance_data: dict = field(default_factory=dict)
    dead_code_data: dict = field(default_factory=dict)
    call_trace_data: list = field(default_factory=list)
    # Call graph structures (matching Interactive Explorer)
    call_graph: dict = field(default_factory=dict)  # caller -> [callees]
    reverse_call_graph: dict = field(default_factory=dict)  # callee -> [callers]
    covered_functions: set = field(default_factory=set)  # Functions that have been executed
    function_info: dict = field(default_factory=dict)  # func_name -> {file, line, module}
    # Stack tracking for building call graph
    _call_stack: list = field(default_factory=list)  # Stack of (call_id, func_name)


# Global state
state = TrueFlowState()


# ============================================================================
# TRACE COLLECTION TOOLS
# ============================================================================

@server.tool()
async def trace_connect(host: str = "127.0.0.1", port: int = 5678) -> str:
    """
    Connect to a running TrueFlow trace server.

    The trace server streams real-time execution events from Python code.
    Start your Python app with TrueFlow instrumentation first.

    Args:
        host: Trace server host (default: 127.0.0.1)
        port: Trace server port (default: 5678)

    Returns:
        Connection status message
    """
    global state

    if state.trace_connected:
        return "Already connected to trace server"

    try:
        state.trace_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        state.trace_socket.settimeout(5.0)
        state.trace_socket.connect((host, port))
        state.trace_connected = True
        state.trace_events = []

        # Start background reader
        asyncio.create_task(_read_trace_events())

        return f"Connected to trace server at {host}:{port}"
    except Exception as e:
        state.trace_connected = False
        return f"Failed to connect: {str(e)}. Make sure the trace server is running."


@server.tool()
async def trace_disconnect() -> str:
    """
    Disconnect from the trace server.

    Returns:
        Disconnection status message
    """
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


@server.tool()
async def trace_status() -> str:
    """
    Get current trace collection status.

    Returns:
        JSON with connection status, event count, and recent events
    """
    global state

    status = {
        "connected": state.trace_connected,
        "event_count": len(state.trace_events),
        "recent_events": state.trace_events[-10:] if state.trace_events else [],
        "unique_functions": len(set(e.get("function", "") for e in state.trace_events)),
        "unique_modules": len(set(e.get("module", "") for e in state.trace_events))
    }
    return json.dumps(status, indent=2)


@server.tool()
async def trace_get_events(limit: int = 100, filter_module: str = "", filter_function: str = "") -> str:
    """
    Get collected trace events with optional filtering.

    Args:
        limit: Maximum number of events to return (default: 100)
        filter_module: Filter by module name (partial match)
        filter_function: Filter by function name (partial match)

    Returns:
        JSON array of trace events
    """
    global state

    events = state.trace_events

    if filter_module:
        events = [e for e in events if filter_module.lower() in e.get("module", "").lower()]

    if filter_function:
        events = [e for e in events if filter_function.lower() in e.get("function", "").lower()]

    return json.dumps(events[-limit:], indent=2)


@server.tool()
async def trace_clear() -> str:
    """
    Clear all collected trace events.

    Returns:
        Confirmation message
    """
    global state
    count = len(state.trace_events)
    state.trace_events = []
    state.performance_data = {}
    state.dead_code_data = {}
    state.call_trace_data = []
    return f"Cleared {count} trace events"


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
    """Update performance, call graph, and dead code analytics from event."""
    global state

    func_key = f"{event.get('module', 'unknown')}.{event.get('function', 'unknown')}"
    event_type = event.get("type", "")
    call_id = event.get("call_id")

    # Initialize performance data for new functions
    if func_key not in state.performance_data:
        state.performance_data[func_key] = {
            "calls": 0,
            "total_ms": 0,
            "min_ms": float('inf'),
            "max_ms": 0,
            "file": event.get("file", ""),
            "line": event.get("line", 0)
        }

    # Store function info (file, line, module)
    if func_key not in state.function_info:
        state.function_info[func_key] = {
            "file": event.get("file", ""),
            "line": event.get("line", 0),
            "module": event.get("module", "unknown")
        }

    perf = state.performance_data[func_key]

    # Handle call events - build call graph
    if event_type == "call":
        perf["calls"] += 1
        state.covered_functions.add(func_key)

        # Build call graph from stack
        if state._call_stack:
            caller = state._call_stack[-1][1]  # Get caller function name
            # Add to call_graph (caller -> callees)
            if caller not in state.call_graph:
                state.call_graph[caller] = []
            if func_key not in state.call_graph[caller]:
                state.call_graph[caller].append(func_key)

            # Add to reverse_call_graph (callee -> callers)
            if func_key not in state.reverse_call_graph:
                state.reverse_call_graph[func_key] = []
            if caller not in state.reverse_call_graph[func_key]:
                state.reverse_call_graph[func_key].append(caller)

        # Push to stack
        state._call_stack.append((call_id, func_key))

    # Handle return events
    elif event_type == "return":
        if "duration_ms" in event:
            duration = event["duration_ms"]
            perf["total_ms"] += duration
            perf["min_ms"] = min(perf["min_ms"], duration)
            perf["max_ms"] = max(perf["max_ms"], duration)

        # Pop from stack
        if state._call_stack and state._call_stack[-1][0] == call_id:
            state._call_stack.pop()

    # Track call hierarchy for detailed analysis
    state.call_trace_data.append({
        "function": func_key,
        "depth": event.get("depth", 0),
        "parent_id": event.get("parent_id"),
        "call_id": call_id,
        "timestamp": event.get("timestamp"),
        "type": event_type
    })


# ============================================================================
# MANIM VIDEO GENERATION TOOLS
# ============================================================================

@server.tool()
async def manim_generate_video(
    trace_file: str = "",
    quality: str = "low_quality",
    scene_type: str = "execution_flow"
) -> str:
    """
    Generate a Manim 3D animation video from trace data.

    Creates beautiful 3D visualizations of code execution flow,
    similar to 3Blue1Brown style animations.

    Args:
        trace_file: Path to trace JSON file (uses current trace if empty)
        quality: Video quality - low_quality, medium_quality, high_quality
        scene_type: Type of visualization - execution_flow, architecture, error_propagation

    Returns:
        Path to generated video file or error message
    """
    global state

    # Find the visualizer script
    plugin_dir = state.project_dir / ".pycharm_plugin" / "runtime_injector"
    visualizer_script = plugin_dir / "ultimate_architecture_viz.py"

    if not visualizer_script.exists():
        # Try alternate locations
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

    # Create trace file from current events if not provided
    if not trace_file:
        traces_dir = state.project_dir / ".pycharm_plugin" / "manim" / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trace_file = str(traces_dir / f"trace_{timestamp}.json")

        with open(trace_file, 'w') as f:
            json.dump({
                "events": state.trace_events[-500:],  # Last 500 events
                "performance": state.performance_data,
                "timestamp": timestamp
            }, f, indent=2)

    # Run Manim
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
            # Find the video path from output
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


@server.tool()
async def manim_list_videos() -> str:
    """
    List all generated Manim videos.

    Returns:
        JSON array of video file paths with metadata
    """
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
# ANALYSIS TOOLS
# ============================================================================

@server.tool()
async def analyze_performance(sort_by: str = "total_ms", limit: int = 20) -> str:
    """
    Analyze performance metrics from collected traces.

    Shows which functions take the most time, have the most calls, etc.

    Args:
        sort_by: Sort metric - total_ms, calls, avg_ms, max_ms
        limit: Number of top functions to return

    Returns:
        JSON with performance analysis
    """
    global state

    if not state.performance_data:
        return "No performance data. Connect to trace server and collect events first."

    # Calculate averages
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

    # Sort
    results.sort(key=lambda x: x.get(sort_by, 0), reverse=True)

    return json.dumps({
        "total_functions": len(results),
        "sort_by": sort_by,
        "hotspots": results[:limit]
    }, indent=2)


@server.tool()
async def analyze_dead_code(source_dir: str = "") -> str:
    """
    Analyze dead/unreachable code by comparing static analysis with runtime traces.

    Identifies functions that exist in source but were never called during execution.

    Args:
        source_dir: Directory to scan for Python files (default: project dir)

    Returns:
        JSON with dead code analysis
    """
    global state

    source_path = Path(source_dir) if source_dir else state.project_dir

    # Get all defined functions from source files
    defined_functions = set()
    for py_file in source_path.rglob("*.py"):
        if ".venv" in str(py_file) or "node_modules" in str(py_file):
            continue
        try:
            with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                import ast
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        module = str(py_file.relative_to(source_path)).replace('/', '.').replace('\\', '.').replace('.py', '')
                        defined_functions.add(f"{module}.{node.name}")
        except:
            continue

    # Get called functions from traces
    called_functions = set(state.performance_data.keys())

    # Find dead code
    dead_functions = defined_functions - called_functions

    # Categorize
    result = {
        "total_defined": len(defined_functions),
        "total_called": len(called_functions),
        "dead_count": len(dead_functions),
        "coverage_percent": round(len(called_functions) / len(defined_functions) * 100, 1) if defined_functions else 0,
        "dead_functions": sorted(list(dead_functions))[:50],
        "note": "Run more code paths to improve coverage accuracy"
    }

    state.dead_code_data = result
    return json.dumps(result, indent=2)


@server.tool()
async def analyze_call_tree(root_function: str = "", max_depth: int = 5) -> str:
    """
    Generate a call tree showing function call hierarchy.

    Args:
        root_function: Starting function (empty for all entry points)
        max_depth: Maximum tree depth to show

    Returns:
        JSON call tree structure
    """
    global state

    if not state.call_trace_data:
        return "No call trace data. Connect and collect traces first."

    # Build call graph
    calls_by_parent = {}
    for call in state.call_trace_data:
        parent = call.get("parent_id", "root")
        if parent not in calls_by_parent:
            calls_by_parent[parent] = []
        calls_by_parent[parent].append(call)

    def build_tree(parent_id: str, depth: int) -> list:
        if depth > max_depth:
            return []
        children = calls_by_parent.get(parent_id, [])
        return [{
            "function": c["function"],
            "depth": c["depth"],
            "children": build_tree(c["call_id"], depth + 1) if c["call_id"] else []
        } for c in children]

    tree = build_tree("root", 0)

    if root_function:
        # Filter to specific function
        def find_function(nodes, target):
            for n in nodes:
                if target in n["function"]:
                    return n
                found = find_function(n.get("children", []), target)
                if found:
                    return found
            return None
        tree = [find_function(tree, root_function)] if find_function(tree, root_function) else []

    return json.dumps(tree, indent=2)


@server.tool()
async def analyze_sql_queries() -> str:
    """
    Analyze SQL queries from traces to detect N+1 problems and slow queries.

    Returns:
        JSON with SQL analysis including N+1 detection
    """
    global state

    # Filter SQL-related events
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

    # Group by query pattern
    query_patterns = {}
    for event in sql_events:
        pattern = event.get('function', 'unknown')
        if pattern not in query_patterns:
            query_patterns[pattern] = {"count": 0, "total_ms": 0}
        query_patterns[pattern]["count"] += 1
        query_patterns[pattern]["total_ms"] += event.get("duration_ms", 0)

    # Detect N+1 (same query called many times in short period)
    n_plus_1 = [
        {"pattern": p, **data}
        for p, data in query_patterns.items()
        if data["count"] > 10
    ]

    return json.dumps({
        "total_queries": len(sql_events),
        "unique_patterns": len(query_patterns),
        "potential_n_plus_1": n_plus_1,
        "all_patterns": query_patterns
    }, indent=2)


# ============================================================================
# DIAGRAM EXPORT TOOLS
# ============================================================================

@server.tool()
async def export_diagram(format: str = "plantuml", output_file: str = "") -> str:
    """
    Export execution flow as a diagram.

    Args:
        format: Output format - plantuml, mermaid, json
        output_file: Output file path (auto-generated if empty)

    Returns:
        Path to exported file or diagram content
    """
    global state

    if not state.trace_events:
        return "No trace events to export. Collect traces first."

    # Generate unique participants
    modules = set()
    for event in state.trace_events[:200]:  # Limit for readability
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


@server.tool()
async def export_flamegraph(output_file: str = "") -> str:
    """
    Export performance data as a flamegraph-compatible JSON.

    Can be visualized with speedscope.app or similar tools.

    Args:
        output_file: Output file path (auto-generated if empty)

    Returns:
        Path to exported file
    """
    global state

    if not state.performance_data:
        return "No performance data. Collect traces first."

    # Build flamegraph format
    flamegraph_data = {
        "shared": {
            "frames": []
        },
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

    frame_index = {}
    for i, (func, data) in enumerate(state.performance_data.items()):
        frame_index[func] = i
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
# AI SERVER MANAGEMENT TOOLS
# ============================================================================

@server.tool()
async def ai_server_start(model_path: str = "", port: int = 8080) -> str:
    """
    Start the local AI server (llama.cpp) for code explanations.

    Args:
        model_path: Path to GGUF model file (uses default if empty)
        port: Server port (default: 8080)

    Returns:
        Server status message
    """
    global state

    if state.ai_server_process and state.ai_server_process.poll() is None:
        return "AI server is already running"

    # Find llama-server
    home = Path.home()
    possible_paths = [
        home / ".trueflow" / "llama.cpp" / "build" / "bin" / "Release" / "llama-server.exe",
        home / ".trueflow" / "llama.cpp" / "build" / "bin" / "llama-server",
        home / ".trueflow" / "llama.cpp" / "build" / "bin" / "llama-server.exe",
    ]

    llama_server = None
    for p in possible_paths:
        if p.exists():
            llama_server = p
            break

    if not llama_server:
        return "llama-server not found. Install llama.cpp first."

    # Find model
    if not model_path:
        models_dir = home / ".trueflow" / "models"
        if models_dir.exists():
            for gguf in models_dir.glob("*.gguf"):
                model_path = str(gguf)
                break

    if not model_path:
        return "No model found. Download a model first using ai_download_model."

    # Start server
    try:
        cmd = [
            str(llama_server),
            "--model", model_path,
            "--port", str(port),
            "--ctx-size", "4096",
            "--host", "127.0.0.1"
        ]

        state.ai_server_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Wait for startup
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


@server.tool()
async def ai_server_stop() -> str:
    """
    Stop the local AI server.

    Returns:
        Status message
    """
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


@server.tool()
async def ai_server_status() -> str:
    """
    Check AI server status.

    Returns:
        JSON with server status
    """
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


@server.tool()
async def ai_download_model(model_name: str = "Qwen3-VL-2B-Instruct-Q4_K_XL") -> str:
    """
    Download an AI model from HuggingFace.

    Args:
        model_name: Model preset name. Options:
            - Qwen3-VL-2B-Instruct-Q4_K_XL (recommended, 1.5GB)
            - Qwen3-VL-2B-Thinking-Q4_K_XL (reasoning, 1.5GB)
            - Qwen3-VL-4B-Instruct-Q4_K_XL (larger, 2.8GB)
            - Qwen3-2B-Instruct-Q4_K_M (text-only, 1.1GB)

    Returns:
        Download status message
    """
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

        def report_progress(count, block_size, total_size):
            percent = int(count * block_size * 100 / total_size)
            if count % 100 == 0:
                logger.info(f"Download progress: {percent}%")

        logger.info(f"Downloading {model_name}...")
        urllib.request.urlretrieve(url, dest_path, reporthook=report_progress)
        return f"Model downloaded to: {dest_path}"

    except Exception as e:
        return f"Download failed: {str(e)}"


@server.tool()
async def ai_explain_code(question: str, context_type: str = "all") -> str:
    """
    Ask the AI to explain code behavior using collected trace context.

    Args:
        question: Your question about the code
        context_type: Context to include - all, performance, dead_code, call_trace, none

    Returns:
        AI explanation
    """
    global state

    # Build context
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
        if state.call_trace_data:
            context += "\n--- Recent Call Trace ---\n"
            for call in state.call_trace_data[-20:]:
                indent = "  " * call.get("depth", 0)
                context += f"{indent}-> {call['function']}\n"

    # Call AI server
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
        return f"AI server error: {str(e)}. Make sure the server is running with ai_server_start."


# ============================================================================
# PROJECT MANAGEMENT TOOLS
# ============================================================================

@server.tool()
async def set_project_dir(directory: str) -> str:
    """
    Set the project directory for TrueFlow operations.

    Args:
        directory: Path to project directory

    Returns:
        Confirmation message
    """
    global state

    path = Path(directory).resolve()
    if not path.exists():
        return f"Directory does not exist: {directory}"

    state.project_dir = path
    return f"Project directory set to: {state.project_dir}"


@server.tool()
async def get_project_info() -> str:
    """
    Get information about the current project.

    Returns:
        JSON with project info
    """
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


@server.tool()
async def auto_integrate(entry_point: str = "") -> str:
    """
    Auto-integrate TrueFlow tracing into a Python project.

    Sets up the runtime injector so that running Python code
    automatically streams trace events.

    Args:
        entry_point: Main Python file (e.g., main.py, app.py)

    Returns:
        Integration status and instructions
    """
    global state

    plugin_dir = state.project_dir / ".pycharm_plugin"
    injector_dir = plugin_dir / "runtime_injector"

    # Create directories
    plugin_dir.mkdir(parents=True, exist_ok=True)
    injector_dir.mkdir(parents=True, exist_ok=True)

    # Copy injector files from our location
    source_dir = Path(__file__).parent
    files_to_copy = [
        "python_runtime_instrumentor.py",
        "sitecustomize.py"
    ]

    copied = []
    for filename in files_to_copy:
        source = source_dir / filename
        dest = injector_dir / filename
        if source.exists():
            import shutil
            shutil.copy2(source, dest)
            copied.append(filename)

    instructions = f"""
TrueFlow integration complete!

Files deployed to: {injector_dir}
Copied: {', '.join(copied)}

To run with tracing enabled:

Option 1 - Environment variable:
    set PYTHONPATH={injector_dir};%PYTHONPATH%
    python {entry_point or 'your_script.py'}

Option 2 - Direct import:
    Add to your script:
    import sys
    sys.path.insert(0, r'{injector_dir}')
    import sitecustomize

Then connect with: trace_connect()
"""

    return instructions


# ============================================================================
# INTERACTIVE EXPLORER TOOLS (for LLM-driven code exploration)
# Uses exact same call_graph logic as Interactive Explorer HTML
# ============================================================================

def _find_matching_function(function_name: str) -> str:
    """Find exact or partial match in covered functions."""
    # Try exact match first
    if function_name in state.covered_functions:
        return function_name
    # Try partial match
    for func in state.covered_functions:
        if function_name.lower() in func.lower():
            return func
    return ""


def _find_all_children(func_name: str) -> list:
    """Find ALL children (callees) of a function - matches Interactive Explorer findAllChildren()."""
    return state.call_graph.get(func_name, [])


def _find_all_parents(func_name: str) -> list:
    """Find ALL parents (callers) of a function - matches Interactive Explorer findAllParents()."""
    return state.reverse_call_graph.get(func_name, [])


def _find_downstream_path(func_name: str, visited: set = None) -> list:
    """
    Find all downstream nodes (callees) recursively.
    Matches Interactive Explorer findDownstreamPath().
    """
    if visited is None:
        visited = set()
    if func_name in visited:
        return []
    visited.add(func_name)

    callees = state.call_graph.get(func_name, [])
    downstream = []

    for callee in callees:
        downstream.append(callee)
        downstream.extend(_find_downstream_path(callee, visited))

    return list(set(downstream))


def _find_upstream_path(func_name: str, visited: set = None) -> list:
    """
    Find all upstream nodes (callers) recursively.
    Matches Interactive Explorer findUpstreamPath().
    """
    if visited is None:
        visited = set()
    if func_name in visited:
        return []
    visited.add(func_name)

    callers = state.reverse_call_graph.get(func_name, [])
    upstream = []

    for caller in callers:
        upstream.append(caller)
        upstream.extend(_find_upstream_path(caller, visited))

    return list(set(upstream))


def _find_root_caller(func_name: str) -> str:
    """
    Find the root caller (entry point) for a function.
    Matches Interactive Explorer findRootCaller().
    """
    current = func_name
    visited = set()

    while True:
        if current in visited:
            break
        visited.add(current)

        callers = state.reverse_call_graph.get(current, [])
        if not callers:
            return current  # No callers - this is the root

        # Follow the first caller (primary path)
        current = callers[0]

    return current


@server.tool()
async def explorer_get_function_details(function_name: str) -> str:
    """
    Get detailed information about a specific function from trace data.

    Use this when an LLM needs to understand what a function does, its performance,
    who calls it, and what it calls. Uses exact same call_graph logic as Interactive Explorer.

    Args:
        function_name: Full or partial function name (e.g., "MyClass.method" or just "method")

    Returns:
        JSON with function details: file, line, calls, performance, callees, callers
    """
    global state

    if not state.call_graph and not state.performance_data:
        return "No trace data available. Connect to trace server and collect events first."

    # Find matching functions
    matches = []
    for func_key in state.covered_functions:
        if function_name.lower() in func_key.lower():
            perf_data = state.performance_data.get(func_key, {})
            func_info = state.function_info.get(func_key, {})

            # Get callees and callers using call_graph (same as Interactive Explorer)
            callees = _find_all_children(func_key)
            callers = _find_all_parents(func_key)

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
                "is_entry_point": len(callers) == 0
            })

    if not matches:
        return f"No function matching '{function_name}' found in traces."

    # Sort by calls (most called first)
    matches.sort(key=lambda x: x["calls"], reverse=True)

    return json.dumps({
        "query": function_name,
        "matches": matches[:10],
        "total_matches": len(matches)
    }, indent=2)


@server.tool()
async def explorer_get_callees(function_name: str, max_depth: int = 2) -> str:
    """
    Get all functions called by a specific function (outgoing call edges).

    Use this to understand what other code a function depends on.
    Uses exact same call_graph logic as Interactive Explorer findDownstreamPath().

    Args:
        function_name: Function to analyze
        max_depth: How deep to follow the call chain (default: 2)

    Returns:
        JSON tree of called functions with their metrics
    """
    global state

    if not state.call_graph:
        return "No call graph data available. Connect to trace server and collect events first."

    # Find exact function
    func = _find_matching_function(function_name)
    if not func:
        return f"Function '{function_name}' not found in traces."

    def build_callee_tree(func_name: str, depth: int, visited: set) -> list:
        if depth > max_depth or func_name in visited:
            return []
        visited.add(func_name)

        result = []
        callees = _find_all_children(func_name)

        for callee in callees:
            perf = state.performance_data.get(callee, {})
            result.append({
                "function": callee,
                "calls": perf.get("calls", 0),
                "total_ms": round(perf.get("total_ms", 0), 2),
                "is_covered": callee in state.covered_functions,
                "children": build_callee_tree(callee, depth + 1, visited.copy()) if depth + 1 <= max_depth else []
            })

        return result

    tree = build_callee_tree(func, 0, set())

    # Also get flat list of all downstream functions
    all_downstream = _find_downstream_path(func)

    return json.dumps({
        "function": func,
        "max_depth": max_depth,
        "callees_tree": tree,
        "all_downstream": all_downstream[:50],
        "total_downstream": len(all_downstream)
    }, indent=2)


@server.tool()
async def explorer_get_callers(function_name: str, max_depth: int = 2) -> str:
    """
    Get all functions that call a specific function (incoming call edges).

    Use this to understand what code depends on a function.
    Uses exact same call_graph logic as Interactive Explorer findUpstreamPath().

    Args:
        function_name: Function to analyze
        max_depth: How deep to follow the caller chain (default: 2)

    Returns:
        JSON tree of calling functions
    """
    global state

    if not state.reverse_call_graph:
        return "No call graph data available. Connect to trace server and collect events first."

    # Find exact function
    func = _find_matching_function(function_name)
    if not func:
        return f"Function '{function_name}' not found in traces."

    def build_caller_tree(func_name: str, depth: int, visited: set) -> list:
        if depth > max_depth or func_name in visited:
            return []
        visited.add(func_name)

        result = []
        callers = _find_all_parents(func_name)

        for caller in callers:
            perf = state.performance_data.get(caller, {})
            result.append({
                "function": caller,
                "calls": perf.get("calls", 0),
                "total_ms": round(perf.get("total_ms", 0), 2),
                "is_covered": caller in state.covered_functions,
                "callers": build_caller_tree(caller, depth + 1, visited.copy()) if depth + 1 <= max_depth else []
            })

        return result

    tree = build_caller_tree(func, 0, set())

    # Also get flat list of all upstream functions and root caller
    all_upstream = _find_upstream_path(func)
    root = _find_root_caller(func)

    return json.dumps({
        "function": func,
        "max_depth": max_depth,
        "callers_tree": tree,
        "all_upstream": all_upstream[:50],
        "total_upstream": len(all_upstream),
        "root_caller": root if root != func else None
    }, indent=2)


@server.tool()
async def explorer_search(query: str, search_type: str = "function") -> str:
    """
    Search for functions, modules, or files in the trace data.

    Use this to find code elements by name or pattern.
    Uses same data structures as Interactive Explorer.

    Args:
        query: Search query (partial match supported)
        search_type: What to search - function, module, file, all

    Returns:
        JSON array of matching items with metadata
    """
    global state

    results = []
    query_lower = query.lower()

    for func_key in state.covered_functions:
        perf_data = state.performance_data.get(func_key, {})
        func_info = state.function_info.get(func_key, {})

        match = False
        module_name = func_key.rsplit(".", 1)[0] if "." in func_key else ""
        func_name = func_key.rsplit(".", 1)[-1] if "." in func_key else func_key
        file_path = func_info.get("file", perf_data.get("file", ""))

        if search_type in ["function", "all"] and query_lower in func_name.lower():
            match = True
        if search_type in ["module", "all"] and query_lower in module_name.lower():
            match = True
        if search_type in ["file", "all"] and query_lower in file_path.lower():
            match = True

        if match:
            callees = _find_all_children(func_key)
            callers = _find_all_parents(func_key)
            results.append({
                "function": func_key,
                "module": module_name,
                "name": func_name,
                "file": file_path,
                "line": func_info.get("line", perf_data.get("line", 0)),
                "calls": perf_data.get("calls", 0),
                "total_ms": round(perf_data.get("total_ms", 0), 2),
                "callees_count": len(callees),
                "callers_count": len(callers),
                "is_entry_point": len(callers) == 0
            })

    # Sort by calls (most called first)
    results.sort(key=lambda x: x["calls"], reverse=True)

    return json.dumps({
        "query": query,
        "search_type": search_type,
        "results": results[:50],
        "total_matches": len(results)
    }, indent=2)


@server.tool()
async def explorer_get_hot_paths(limit: int = 10) -> str:
    """
    Get the most frequently executed code paths (hot paths).

    Use this to identify performance-critical execution flows.
    Analyzes call_graph to find heavily traversed paths.

    Args:
        limit: Number of hot paths to return

    Returns:
        JSON array of hot paths with call sequences and metrics
    """
    global state

    if not state.call_graph:
        return "No call graph data available."

    # Find entry points (functions with no callers)
    entry_points = [f for f in state.covered_functions if not _find_all_parents(f)]

    # Build paths from each entry point
    paths = []

    for entry in entry_points:
        # DFS to collect all paths from this entry
        def collect_paths(func: str, current_path: list, visited: set):
            if func in visited or len(current_path) > 10:
                return
            visited.add(func)
            current_path.append(func)

            callees = _find_all_children(func)
            if not callees:
                # Leaf node - record path
                perf = state.performance_data.get(func, {})
                path_total_ms = sum(state.performance_data.get(f, {}).get("total_ms", 0) for f in current_path)
                path_total_calls = min(state.performance_data.get(f, {}).get("calls", 0) for f in current_path) if current_path else 0
                paths.append({
                    "entry_point": entry,
                    "path": " -> ".join(current_path[:5]) + ("..." if len(current_path) > 5 else ""),
                    "functions": current_path.copy(),
                    "depth": len(current_path),
                    "path_total_ms": round(path_total_ms, 2),
                    "min_calls_in_path": path_total_calls
                })
            else:
                for callee in callees[:5]:  # Limit branching
                    collect_paths(callee, current_path.copy(), visited.copy())

        collect_paths(entry, [], set())

    # Sort by execution frequency (min_calls_in_path as proxy)
    paths.sort(key=lambda x: x["min_calls_in_path"], reverse=True)

    return json.dumps({
        "hot_paths": paths[:limit],
        "total_paths_analyzed": len(paths),
        "entry_points": entry_points[:20]
    }, indent=2)


@server.tool()
async def explorer_get_coverage_summary() -> str:
    """
    Get code coverage summary from trace data.

    Use this to understand what percentage of code has been executed.
    Uses same call_graph analysis as Interactive Explorer.

    Returns:
        JSON with coverage statistics by module and overall
    """
    global state

    if not state.covered_functions:
        return "No trace data available."

    # Find entry points (no callers) and leaf nodes (no callees)
    entry_points = []
    leaf_nodes = []
    for func in state.covered_functions:
        callers = _find_all_parents(func)
        callees = _find_all_children(func)
        if not callers:
            entry_points.append(func)
        if not callees:
            leaf_nodes.append(func)

    # Group by module
    modules = {}
    for func_key in state.covered_functions:
        perf_data = state.performance_data.get(func_key, {})
        module = func_key.rsplit(".", 1)[0] if "." in func_key else "unknown"
        if module not in modules:
            modules[module] = {
                "functions_covered": 0,
                "total_calls": 0,
                "total_ms": 0,
                "entry_points": 0,
                "functions": []
            }
        modules[module]["functions_covered"] += 1
        modules[module]["total_calls"] += perf_data.get("calls", 0)
        modules[module]["total_ms"] += perf_data.get("total_ms", 0)
        modules[module]["functions"].append(func_key.rsplit(".", 1)[-1])
        if func_key in entry_points:
            modules[module]["entry_points"] += 1

    # Calculate totals
    total_functions = len(state.covered_functions)
    total_calls = sum(state.performance_data.get(f, {}).get("calls", 0) for f in state.covered_functions)
    total_ms = sum(state.performance_data.get(f, {}).get("total_ms", 0) for f in state.covered_functions)

    # Call graph stats
    total_edges = sum(len(callees) for callees in state.call_graph.values())

    # Add dead code info if available
    dead_code_info = {}
    if state.dead_code_data:
        dead_code_info = {
            "total_defined": state.dead_code_data.get("total_defined", 0),
            "dead_count": state.dead_code_data.get("dead_count", 0),
            "coverage_percent": state.dead_code_data.get("coverage_percent", 0)
        }

    # Sort modules by activity
    module_summary = [
        {
            "module": m,
            "functions_covered": d["functions_covered"],
            "total_calls": d["total_calls"],
            "total_ms": round(d["total_ms"], 2),
            "entry_points": d["entry_points"]
        }
        for m, d in sorted(modules.items(), key=lambda x: x[1]["total_calls"], reverse=True)
    ][:20]

    return json.dumps({
        "summary": {
            "total_functions_executed": total_functions,
            "total_function_calls": total_calls,
            "total_execution_time_ms": round(total_ms, 2),
            "unique_modules": len(modules),
            "call_graph_edges": total_edges,
            "entry_points_count": len(entry_points),
            "leaf_nodes_count": len(leaf_nodes)
        },
        "entry_points": entry_points[:10],
        "dead_code": dead_code_info,
        "modules": module_summary
    }, indent=2)


@server.tool()
async def explorer_explain_function(function_name: str) -> str:
    """
    Get an AI-powered explanation of a function's behavior based on trace data.

    Combines trace context with AI to explain what a function does,
    its performance characteristics, and its role in the codebase.

    Args:
        function_name: Function to explain

    Returns:
        AI-generated explanation with trace context
    """
    global state

    # Get function details first
    details_json = await explorer_get_function_details(function_name)
    details = json.loads(details_json)

    if "matches" not in details or not details["matches"]:
        return f"Function '{function_name}' not found in traces."

    func_info = details["matches"][0]

    # Build context for AI
    context = f"""
Function: {func_info['function']}
File: {func_info['file']}:{func_info['line']}

Performance Metrics:
- Called {func_info['calls']} times
- Total time: {func_info['total_ms']}ms
- Average time: {func_info['avg_ms']}ms per call
- Max time: {func_info['max_ms']}ms

Calls these functions ({func_info['callees_count']} callees):
{', '.join(func_info['callees'][:10]) if func_info['callees'] else 'None recorded'}

Called by ({func_info['callers_count']} callers):
{', '.join(func_info['callers'][:10]) if func_info['callers'] else 'Entry point or not recorded'}
"""

    # Try to get AI explanation
    try:
        import urllib.request

        prompt = f"""Based on the runtime trace data below, explain what this function does and its role in the codebase.
Focus on:
1. What the function's purpose appears to be
2. Its performance characteristics (is it called often? is it slow?)
3. Its dependencies (what it calls) and dependents (what calls it)
4. Any potential concerns (e.g., called too often, takes too long)

{context}

Provide a concise technical explanation."""

        payload = json.dumps({
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 512,
            "temperature": 0.7
        }).encode('utf-8')

        req = urllib.request.Request(
            "http://127.0.0.1:8080/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        response = urllib.request.urlopen(req, timeout=60)
        result = json.loads(response.read().decode('utf-8'))
        ai_explanation = result["choices"][0]["message"]["content"]

        return json.dumps({
            "function": func_info['function'],
            "metrics": {
                "calls": func_info['calls'],
                "total_ms": func_info['total_ms'],
                "avg_ms": func_info['avg_ms']
            },
            "ai_explanation": ai_explanation
        }, indent=2)

    except Exception as e:
        # Return just the metrics if AI is not available
        return json.dumps({
            "function": func_info['function'],
            "metrics": func_info,
            "ai_explanation": f"AI server not available: {str(e)}. Start with ai_server_start().",
            "context": context
        }, indent=2)


@server.tool()
async def explorer_get_call_graph(module_filter: str = "") -> str:
    """
    Get the full call graph structure as used by Interactive Explorer.

    Use this to understand the overall code structure and relationships.
    This is the same data structure that Interactive Explorer visualizes as 3D nodes.

    Args:
        module_filter: Optional filter to only include functions from specific module

    Returns:
        JSON with call_graph (caller->callees) and reverse_call_graph (callee->callers)
    """
    global state

    if not state.call_graph:
        return "No call graph data available. Connect to trace server and collect events first."

    # Apply module filter if provided
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
        filtered_functions = [f for f in state.covered_functions if filter_lower in f.lower()]
    else:
        filtered_call_graph = dict(state.call_graph)
        filtered_reverse = dict(state.reverse_call_graph)
        filtered_functions = list(state.covered_functions)

    # Find entry points and leaf nodes
    entry_points = [f for f in filtered_functions if f not in filtered_reverse or not filtered_reverse[f]]
    leaf_nodes = [f for f in filtered_functions if f not in filtered_call_graph or not filtered_call_graph[f]]

    return json.dumps({
        "call_graph": filtered_call_graph,
        "reverse_call_graph": filtered_reverse,
        "functions": filtered_functions[:100],
        "total_functions": len(filtered_functions),
        "total_edges": sum(len(v) for v in filtered_call_graph.values()),
        "entry_points": entry_points[:20],
        "leaf_nodes": leaf_nodes[:20],
        "module_filter": module_filter or "none"
    }, indent=2)


@server.tool()
async def explorer_find_path(source: str, target: str) -> str:
    """
    Find the call path between two functions.

    Use this to understand how one function reaches another through the call chain.
    Similar to navigating between nodes in Interactive Explorer.

    Args:
        source: Starting function name
        target: Target function name to reach

    Returns:
        JSON with the path from source to target (if reachable)
    """
    global state

    if not state.call_graph:
        return "No call graph data available."

    # Find exact matches
    source_func = _find_matching_function(source)
    target_func = _find_matching_function(target)

    if not source_func:
        return f"Source function '{source}' not found in traces."
    if not target_func:
        return f"Target function '{target}' not found in traces."

    # BFS to find shortest path from source to target (downstream)
    def find_downstream_path():
        queue = [(source_func, [source_func])]
        visited = {source_func}

        while queue:
            current, path = queue.pop(0)
            if current == target_func:
                return path

            for callee in state.call_graph.get(current, []):
                if callee not in visited:
                    visited.add(callee)
                    queue.append((callee, path + [callee]))

        return None

    # BFS to find path from source to target (upstream - target calls source)
    def find_upstream_path():
        queue = [(source_func, [source_func])]
        visited = {source_func}

        while queue:
            current, path = queue.pop(0)
            if current == target_func:
                return list(reversed(path))

            for caller in state.reverse_call_graph.get(current, []):
                if caller not in visited:
                    visited.add(caller)
                    queue.append((caller, path + [caller]))

        return None

    downstream_path = find_downstream_path()
    upstream_path = find_upstream_path()

    result = {
        "source": source_func,
        "target": target_func
    }

    if downstream_path:
        result["downstream_path"] = {
            "direction": f"{source_func} calls ... calls {target_func}",
            "path": downstream_path,
            "length": len(downstream_path) - 1,
            "path_string": " -> ".join(downstream_path)
        }

    if upstream_path:
        result["upstream_path"] = {
            "direction": f"{target_func} calls ... calls {source_func}",
            "path": upstream_path,
            "length": len(upstream_path) - 1,
            "path_string": " -> ".join(upstream_path)
        }

    if not downstream_path and not upstream_path:
        result["reachable"] = False
        result["message"] = f"No call path exists between {source_func} and {target_func}"
    else:
        result["reachable"] = True

    return json.dumps(result, indent=2)


# ============================================================================
# RESOURCES (for MCP resource protocol)
# ============================================================================

@server.resource("trueflow://traces/latest")
async def get_latest_traces() -> str:
    """Get the latest trace events as a resource."""
    return json.dumps(state.trace_events[-100:], indent=2)


@server.resource("trueflow://performance/summary")
async def get_performance_summary() -> str:
    """Get performance analysis summary as a resource."""
    return json.dumps(state.performance_data, indent=2)


@server.resource("trueflow://deadcode/report")
async def get_deadcode_report() -> str:
    """Get dead code analysis report as a resource."""
    return json.dumps(state.dead_code_data, indent=2)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

async def main():
    """Run the MCP server."""
    logger.info("Starting TrueFlow MCP Server...")
    logger.info(f"Project directory: {state.project_dir}")

    # Run with stdio transport (standard MCP protocol)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
