# TrueFlow - Deterministic Code Visualizer & Explainer

> **Unblackbox LLM code with deterministic truth**

## Vision

TrueFlow reveals the hidden execution paths of AI-generated code. While LLMs produce code probabilistically, TrueFlow provides **deterministic, verifiable truth** about what that code actually does at runtime.

**Tagline:** *"From probabilistic chaos to execution certainty"*

---

## Table of Contents

1. [What is TrueFlow?](#what-is-trueflow)
2. [Quick Start](#quick-start)
3. [Installation](#installation)
4. [IDE Variants](#ide-variants)
5. [Auto-Integrate Feature](#auto-integrate-feature)
6. [Socket-Based Real-Time Tracing](#socket-based-real-time-tracing)
7. [Manim Visualizations](#manim-visualizations)
8. [Export Formats](#export-formats)
9. [Configuration](#configuration)
10. [Running Tests](#running-tests)
11. [Contributing](#contributing)

---

## What is TrueFlow?

TrueFlow is an open-source runtime instrumentation and visualization toolkit that:

- **Traces** every function call in your Python code without any code changes
- **Streams** events in real-time via socket (port 5678) to your IDE
- **Visualizes** execution flows as interactive 3D animations (Manim)
- **Explains** what code does in natural language
- **Integrates** with PyCharm, VS Code, and runs standalone

### Core Components

```
TrueFlow/
├── runtime_injector/          # Python runtime instrumentation (zero-code)
│   ├── python_runtime_instrumentor.py  # Main instrumentor with socket streaming
│   └── sitecustomize.py       # Auto-loader via PYTHONPATH
├── manim_visualizer/          # 3D animated execution videos
├── src/                       # PyCharm plugin (Kotlin)
└── vscode-extension/          # VS Code extension (TypeScript)
```

---

## Quick Start

### 1. Clone and Build

```bash
git clone https://github.com/your-org/TrueFlow.git
cd TrueFlow

# Build PyCharm plugin
./gradlew buildPlugin

# Build VS Code extension
cd vscode-extension
npm install
npm run compile
npx vsce package
```

### 2. Install IDE Extension

**PyCharm:**
- Settings → Plugins → Install from Disk
- Select: `build/distributions/SequenceDiagramPython-*.zip`

**VS Code:**
```bash
code --install-extension vscode-extension/trueflow-0.1.0.vsix
```

### 3. Use Auto-Integrate (One Click Setup)

In your IDE, open the TrueFlow panel and click **"Auto-Integrate"**. Select your entry point file (e.g., `main.py`, `app.py`) and TrueFlow handles the rest - **NO code changes required!**

---

## Installation

### Prerequisites

- **Python**: 2.7+ or 3.x (tested with 3.8-3.12)
- **PyCharm** 2023.1+ OR **VS Code** 1.80+
- **Manim** (optional, for video generation): `pip install manim`

### PyCharm Plugin

```bash
cd TrueFlow
./gradlew clean buildPlugin

# Output: build/distributions/SequenceDiagramPython-1.0.3.zip
```

Install in PyCharm:
1. Settings → Plugins → Gear icon → Install Plugin from Disk
2. Select the `.zip` file
3. Restart PyCharm

### VS Code Extension

```bash
cd TrueFlow/vscode-extension
npm install
npm run compile
npx vsce package --allow-missing-repository

# Output: trueflow-0.1.0.vsix
```

Install in VS Code:
```bash
code --install-extension trueflow-0.1.0.vsix
```

### Standalone Python (No IDE)

```bash
cd TrueFlow/runtime_injector
pip install -e .

# Run any script with tracing
TRUEFLOW_ENABLED=1 python your_script.py
```

---

## IDE Variants

TrueFlow provides two IDE integrations with identical core functionality:

### PyCharm Plugin (Kotlin)

| Feature | Description |
|---------|-------------|
| **9-Tab Interface** | Performance, Manim, Dead Code, PlantUML, Mermaid, D2, Flamegraph, Call Trace, Errors |
| **Auto-Integrate** | One-click project setup via Tools menu |
| **Attach to Socket** | Tools → Attach to Trace Server (port 5678) |
| **Real-time Streaming** | Live trace visualization as code executes |
| **Run Configuration** | Automatically creates traced run configs |

**Location:** `src/main/kotlin/com/crawl4ai/learningviz/`

### VS Code Extension (TypeScript)

| Feature | Description |
|---------|-------------|
| **Webview Panels** | Interactive trace visualization |
| **Auto-Integrate** | Command Palette: "TrueFlow: Auto-Integrate Project" |
| **Trace Viewer** | Command Palette: "TrueFlow: Show Trace Viewer" |
| **Manim Generation** | Command Palette: "TrueFlow: Generate Manim Video" |
| **Export Diagrams** | Command Palette: "TrueFlow: Export Diagram" |

**Location:** `vscode-extension/src/extension.ts`

---

## Auto-Integrate Feature

The **Auto-Integrate** button is the easiest way to set up tracing for any Python project.

### What It Does

1. **Copies Runtime Injector** - Deploys `python_runtime_instrumentor.py` and `sitecustomize.py` to `.pycharm_plugin/` (or `.trueflow/`)
2. **Creates Trace Directory** - Sets up `./traces/` for output files
3. **Creates Run Configuration** - Adds IDE run config with proper environment variables
4. **Configures Socket Streaming** - Enables real-time event streaming to port 5678

### How It Works (Zero Code Changes!)

```
User clicks "Auto-Integrate" → Selects entry point (main.py)
    ↓
TrueFlow copies sitecustomize.py to .pycharm_plugin/
    ↓
Creates PyCharm/VS Code run configuration with:
    PYCHARM_PLUGIN_TRACE_ENABLED=1
    CRAWL4AI_TRACE_DIR=./traces
    PYTHONPATH=./.pycharm_plugin
    ↓
When you run the configuration:
    Python loads sitecustomize.py via PYTHONPATH
    sitecustomize.py imports python_runtime_instrumentor.py
    sys.settrace() hooks ALL function calls
    Events stream to socket AND save to trace files
```

### Integration Methods

| Method | Description |
|--------|-------------|
| **PyCharm Run Configuration** | Recommended - Sets environment variables in run config |
| **Environment File (.env)** | Alternative - Adds vars to project .env file |

### Advanced Options

| Option | Description |
|--------|-------------|
| **Modules to Trace** | Comma-separated list (e.g., `myapp,mylib`) - empty = trace all |
| **Exclude Modules** | Default: `test,tests,pytest,unittest` |

---

## Socket-Based Real-Time Tracing

TrueFlow uses **socket streaming** (port 5678) for real-time trace visualization, NOT file-based traces.

### How It Works

```
Python App Starts
    ↓
sitecustomize.py loads python_runtime_instrumentor.py
    ↓
TraceSocketServer starts on 127.0.0.1:5678
    ↓
IDE Plugin connects: "Attach to Trace Server"
    ↓
Every function call → JSON event → Socket stream → IDE UI
```

### Socket Protocol

Newline-delimited JSON (one event per line):

```json
{"type":"call","timestamp":1234.56,"call_id":"abc123","module":"myapp","function":"process_data","file":"/path/to/file.py","line":42,"depth":3}
{"type":"return","timestamp":1234.58,"call_id":"abc123","duration_ms":20.5,"return_value":"success"}
{"type":"exception","timestamp":1234.60,"call_id":"def456","exception":"ValueError","message":"Invalid input"}
```

### Attaching to Socket (PyCharm)

1. Start your Python application with TrueFlow enabled
2. In PyCharm: **Tools → Attach to Trace Server**
3. Enter host: `127.0.0.1`, port: `5678`
4. Traces appear in real-time in the Learning Flow Visualizer panel

### Attaching to Socket (VS Code)

1. Start your Python application with TrueFlow enabled
2. Command Palette: **TrueFlow: Show Trace Viewer**
3. The webview connects to the socket automatically

### Performance Optimizations

TrueFlow uses two-layer filtering to prevent socket overload:

| Layer | Mechanism | Impact |
|-------|-----------|--------|
| **Path Coverage** | Skips repeated calls to same location | ~1000 events/sec |
| **Socket Sampling** | Streams 1 in 10 events (configurable) | ~100 events/sec |

Configure via environment variable:
```bash
PYCHARM_PLUGIN_SOCKET_SAMPLE_RATE=10  # Default: stream 1 in 10 events
```

---

## Manim Visualizations

Generate cinematic 3D videos of your code execution using Manim (3Blue1Brown's animation library).

### Generate Video from Trace

```bash
cd TrueFlow/manim_visualizer
pip install -r requirements.txt

# Generate from trace file
python ultimate_architecture_viz.py --trace ../traces/session_*.json

# Output: media/videos/UltimateArchitectureScene/1080p60/UltimateArchitectureScene.mp4
```

### Quality Presets

| Preset | Resolution | FPS | Use Case |
|--------|------------|-----|----------|
| `low_quality` | 480p | 15 | Quick preview |
| `medium_quality` | 720p | 30 | Development |
| `high_quality` | 1080p | 60 | Production |

### Visualization Scenes

| Scene | Description |
|-------|-------------|
| `UltimateArchitectureScene` | Full system architecture with call flows |
| `ExecutionFlowScene` | Function call sequence animation |
| `DataFlowScene` | Data passing between functions |
| `MinimalTraceVisualizer` | Lightweight quick preview |

---

## Export Formats

TrueFlow exports traces to 11+ formats:

| Format | Extension | Description |
|--------|-----------|-------------|
| **PlantUML** | `.puml` | Sequence diagrams |
| **Mermaid** | `.mmd` | GitHub-compatible diagrams |
| **D2** | `.d2` | Modern declarative diagrams |
| **JSON** | `.json` | Raw trace data |
| **Markdown** | `.md` | Human-readable summary |
| **ASCII Art** | `.txt` | Terminal-friendly visualization |
| **Flamegraph** | `.json` | Performance profiling |
| **LLM Summary** | `.txt` | Natural language description |

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PYCHARM_PLUGIN_TRACE_ENABLED` | Enable tracing | `0` |
| `CRAWL4AI_TRACE_DIR` | Output directory for traces | `./traces` |
| `CRAWL4AI_TRACE_MODULES` | Comma-separated modules to trace | All |
| `CRAWL4AI_EXCLUDE_MODULES` | Modules to exclude | `test,tests` |
| `PYCHARM_PLUGIN_MAX_CALLS` | Max calls to record | `100000` |
| `PYCHARM_PLUGIN_SOCKET_SAMPLE_RATE` | Socket sampling rate | `10` |
| `TRUEFLOW_SOCKET_PORT` | Trace server port | `5678` |

### VS Code Settings

```json
{
    "trueflow.traceDirectory": "./traces",
    "trueflow.pythonPath": "python",
    "trueflow.manimQuality": "medium_quality",
    "trueflow.autoRefresh": true
}
```

---

## Running Tests

TrueFlow includes a comprehensive regression test suite.

### Quick Test (All Categories)

```bash
cd TrueFlow
python run_regression.py --quick
```

### Full Test Suite

```bash
python run_regression.py --full
```

### Individual Test Categories

```bash
# Runtime Injector Tests
python -m pytest tests/test_unit.py -v
python -m pytest tests/test_error_handling.py -v
python -m pytest tests/test_protocol_detection.py -v
python -m pytest tests/test_end_to_end.py -v

# Manim Visualizer Tests
cd manim_visualizer
python -m pytest tests/test_e2e_regression.py -v
python -m pytest tests/test_frame_bounds_validation.py -v
python -m pytest tests/test_animation_pacing.py -v
```

### Test Summary

| Category | Tests | Description |
|----------|-------|-------------|
| Unit Tests | 15+ | Core instrumentor functionality |
| Error Handling | 10+ | Crash prevention, graceful degradation |
| Protocol Detection | 29+ | SQL, gRPC, Kafka, Redis, etc. |
| End-to-End | 8+ | Full workflow validation |
| Manim E2E | 22+ | Video generation, frame bounds |

---

## Key Features

### Zero-Code Instrumentation
- **NO SDK required** - Works with any Python project
- **NO code changes** - Pure runtime injection via PYTHONPATH
- **ONE click setup** - Auto-integrate into any repo

### 29+ Protocol Detection
- SQL, gRPC, GraphQL
- Kafka, Redis, MQTT
- WebSocket, WebRTC
- MCP, A2A protocols

### Framework Detection
- **Web:** FastAPI, Flask, Django
- **AI/ML:** PyTorch, TensorFlow, LangChain, AutoGen
- **Data:** Pandas, NumPy, SQLAlchemy

### Safety Guarantees
- **Memory safety** - Hard limits (100,000 calls max)
- **Graceful degradation** - Failures don't crash your app
- **Zero impact** - Even if TrueFlow fails, your code runs normally

---

## Use Cases

### 1. Understanding AI-Generated Code
```
You: "Claude, write me an async task queue"
Claude: *generates 500 lines of code*
You: *runs TrueFlow* → See exactly how it executes
```

### 2. Debugging Complex Flows
- Visualize async/await execution order
- Trace distributed system calls
- Identify bottlenecks with flamegraphs

### 3. Code Review & Documentation
- Auto-generate architecture diagrams
- Export execution flows for docs
- Create animated explainer videos

---

## Contributing

We welcome contributions!

**Ways to contribute:**
- Report bugs and request features
- Submit pull requests
- Improve documentation
- Create visualization themes
- Build IDE extensions

---

## License

MIT License - See [LICENSE](LICENSE)

---

**TrueFlow** - *Deterministic truth for probabilistic code*

*Built for developers who need to understand what AI-generated code actually does.*
