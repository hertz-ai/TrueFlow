# TrueFlow - Deterministic Code Visualizer & Explainer

> **Unblackbox LLM code with deterministic truth**

## Vision

TrueFlow reveals the hidden execution paths of AI-generated code. While LLMs produce code probabilistically, TrueFlow provides **deterministic, verifiable truth** about what that code actually does at runtime.

**Tagline:** *"From probabilistic chaos to execution certainty"*

## What is TrueFlow?

TrueFlow is an open-source runtime instrumentation and visualization toolkit that:

- **Traces** every function call in your Python code without any code changes
- **Visualizes** execution flows as interactive 3D animations (Manim)
- **Explains** what code does in natural language
- **Integrates** with PyCharm, VS Code, and runs standalone

### Core Components

```
TrueFlow/
├── runtime_injector/          # Python runtime instrumentation (zero-code)
├── manim_visualizer/          # 3D animated execution videos
├── src/                       # PyCharm plugin (Kotlin)
└── vscode-extension/          # VS Code extension (coming soon)
```

## Key Features

### Zero-Code Instrumentation
- **NO SDK required** - Works with any Python project
- **NO code changes** - Pure runtime injection via PYTHONPATH
- **ONE click setup** - Auto-integrate into any repo
- **Python 2.7+ and 3.x** - Universal compatibility

### 11+ Export Formats
- PlantUML, Mermaid, D2 diagrams
- JSON, Markdown, ASCII art
- Flamegraph visualization
- LLM-friendly natural language summaries

### 3D Animated Visualizations
- Real-time execution flow videos
- Architecture diagrams that animate
- Function call sequences as cinematic scenes
- Powered by Manim (3Blue1Brown's animation library)

### 29+ Protocol Detection
- SQL, gRPC, GraphQL
- Kafka, Redis, MQTT
- WebSocket, WebRTC
- MCP, A2A protocols

### Framework Detection
- **Web:** FastAPI, Flask, Django
- **AI/ML:** PyTorch, TensorFlow, LangChain, AutoGen
- **Data:** Pandas, NumPy, SQLAlchemy

## Quick Start

### PyCharm Plugin

```bash
cd TrueFlow
./gradlew buildPlugin
# Install: Settings -> Plugins -> Install from Disk
# Select: build/distributions/trueflow-*.zip
```

### Standalone Python

```bash
cd TrueFlow/runtime_injector
pip install -e .

# Set environment and run any Python script
TRUEFLOW_ENABLED=1 python your_script.py

# Traces appear in ./traces/
```

### Manim Visualizations

```bash
cd TrueFlow/manim_visualizer
pip install -r requirements.txt

# Generate video from trace
python ultimate_architecture_viz.py --trace traces/session_*.json
```

## How It Works

```
Python App Start
    -> TrueFlow Injector Loaded via PYTHONPATH/sitecustomize.py
    -> sys.settrace() Hooks All Function Calls
    -> Events Streamed to Socket (port 5678)
    -> IDE Plugin Receives Events in Real-Time
    -> Manim Renders Animated Execution Videos
```

**Performance overhead:** < 2.5% (typically +0.1-0.5ms per request)

## IDE Integration

### PyCharm (Available Now)

The PyCharm plugin provides:
- 9-tab interface for different views
- Real-time trace visualization
- Auto-generate Manim videos
- One-click project integration

### VS Code (Coming Soon)

VS Code extension with:
- Webview-based visualizations
- Integrated terminal tracing
- Live reload on trace updates

## Safety Guarantees

- **32/32 tests passing (100%)**
- **Memory safety** - Hard limits (100,000 calls max)
- **Graceful degradation** - Failures don't crash your app
- **Zero impact** - Even if TrueFlow fails, your code runs normally

## Use Cases

### 1. Understanding AI-Generated Code
```
You: "Claude, write me an async task queue"
Claude: *generates 500 lines of code*
You: *runs TrueFlow* -> See exactly how it executes
```

### 2. Debugging Complex Flows
- Visualize async/await execution order
- Trace distributed system calls
- Identify bottlenecks with flamegraphs

### 3. Code Review & Documentation
- Auto-generate architecture diagrams
- Export execution flows for docs
- Create animated explainer videos

## Contributing

We welcome contributions! See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for guidelines.

**Ways to contribute:**
- Report bugs and request features
- Submit pull requests
- Improve documentation
- Create visualization themes
- Build IDE extensions

## License

MIT License - See [LICENSE](LICENSE)

## Community

- **GitHub Issues:** Bug reports and feature requests
- **Discussions:** Architecture decisions and roadmap
- **Discord:** Coming soon

---

**TrueFlow** - *Deterministic truth for probabilistic code*

*Built for developers who need to understand what AI-generated code actually does.*
