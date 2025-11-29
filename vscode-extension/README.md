# TrueFlow - Deterministic Code Visualizer

Unblackbox your code with deterministic truth. Zero-code Python runtime instrumentation with 3D animated execution videos.

## Features

- **Zero-Code Instrumentation**: Automatically trace Python code execution without modifying source files
- **Real-Time Trace Viewer**: Watch function calls and execution flow in real-time via WebSocket streaming
- **3D Manim Visualizations**: Generate beautiful animated videos of code execution using Manim
- **Performance Analysis**: Identify bottlenecks with flamegraph-style performance views
- **Dead Code Detection**: Find unreachable or unused code paths
- **AI-Powered Explanations**: Local LLM integration for explaining code behavior (supports vision models)
- **Multiple Export Formats**: PlantUML, Mermaid, D2, JSON, and Markdown exports

## Commands

| Command | Description |
|---------|-------------|
| `TrueFlow: Auto-Integrate into Project` | Add tracing to your Python project |
| `TrueFlow: Show Trace Viewer` | Open the trace visualization panel |
| `TrueFlow: Generate Manim Video` | Create an animated execution video |
| `TrueFlow: Export Diagram` | Export trace as PlantUML/Mermaid diagram |
| `TrueFlow: Connect to Trace Server` | Start real-time trace streaming |
| `TrueFlow: Download AI Model` | Download local LLM for explanations |
| `TrueFlow: Start AI Server` | Start the local llama.cpp server |
| `TrueFlow: Open AI Chat` | Open AI chat panel for code explanations |

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `trueflow.traceDirectory` | `./traces` | Directory to store trace files |
| `trueflow.autoRefresh` | `true` | Auto-refresh on new traces |
| `trueflow.pythonPath` | `python` | Path to Python interpreter |
| `trueflow.socketHost` | `localhost` | Host for trace streaming |
| `trueflow.socketPort` | `5678` | Port for trace streaming |
| `trueflow.manimQuality` | `medium_quality` | Video quality setting |

## Quick Start

1. Open a Python project in VS Code
2. Run `TrueFlow: Auto-Integrate into Project` from the command palette
3. Execute your Python code normally
4. View traces in the TrueFlow sidebar panel
5. Generate Manim videos or export diagrams

## Requirements

- Python 3.8+
- Manim (optional, for video generation)
- llama.cpp (optional, for AI explanations)

## AI Explanation Panel

The AI panel supports:
- **Context injection** from dead code, performance, and call trace panels
- **Vision models** (Qwen3-VL) for analyzing screenshots and diagrams
- **Conversation history** with context awareness
- **Local inference** via llama.cpp server

## Installation

### From VS Code Marketplace / Open VSX

Search for "TrueFlow" in the Extensions view.

### From VSIX

```bash
code --install-extension trueflow-0.1.0.vsix
```

### From Source

```bash
cd vscode-extension
npm install
npm run compile
```

Then press F5 to launch Extension Development Host.

## License

MIT

## Links

- [GitHub Repository](https://github.com/hevolve-ai/trueflow)
- [Report Issues](https://github.com/hevolve-ai/trueflow/issues)
