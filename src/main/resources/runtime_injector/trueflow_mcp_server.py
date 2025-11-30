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
    """Update performance and dead code analytics from event."""
    global state

    func_key = f"{event.get('module', 'unknown')}.{event.get('function', 'unknown')}"

    if func_key not in state.performance_data:
        state.performance_data[func_key] = {
            "calls": 0,
            "total_ms": 0,
            "min_ms": float('inf'),
            "max_ms": 0,
            "file": event.get("file", ""),
            "line": event.get("line", 0)
        }

    perf = state.performance_data[func_key]
    perf["calls"] += 1

    if event.get("type") == "return" and "duration_ms" in event:
        duration = event["duration_ms"]
        perf["total_ms"] += duration
        perf["min_ms"] = min(perf["min_ms"], duration)
        perf["max_ms"] = max(perf["max_ms"], duration)

    # Track call hierarchy for dead code analysis
    state.call_trace_data.append({
        "function": func_key,
        "depth": event.get("depth", 0),
        "parent_id": event.get("parent_id"),
        "call_id": event.get("call_id"),
        "timestamp": event.get("timestamp")
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
