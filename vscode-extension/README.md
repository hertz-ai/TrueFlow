# TrueFlow VS Code Extension

> Deterministic Code Visualizer & Explainer for VS Code

## Features

- **Zero-Code Instrumentation** - Auto-integrate tracing into any Python project
- **Real-Time Trace Viewer** - Watch execution flow as your code runs
- **3D Manim Videos** - Generate animated execution visualizations
- **Multi-Format Export** - PlantUML, Mermaid, D2, JSON, Markdown

## Installation

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

## Quick Start

1. Open a Python project in VS Code
2. Open Command Palette (Ctrl+Shift+P)
3. Run "TrueFlow: Auto-Integrate into Project"
4. Select your entry point (main.py, app.py, etc.)
5. Run your application with the generated configuration
6. Open "TrueFlow: Show Trace Viewer" to see execution flow

## Commands

| Command | Description |
|---------|-------------|
| `TrueFlow: Auto-Integrate into Project` | Set up tracing for current project |
| `TrueFlow: Show Trace Viewer` | Open the trace visualization panel |
| `TrueFlow: Generate Manim Video` | Create 3D animated execution video |
| `TrueFlow: Export Diagram` | Export trace to various formats |

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `trueflow.traceDirectory` | `./traces` | Directory for trace files |
| `trueflow.autoRefresh` | `true` | Auto-refresh on new traces |
| `trueflow.pythonPath` | `python` | Python interpreter path |
| `trueflow.socketPort` | `5678` | Real-time streaming port |
| `trueflow.manimQuality` | `medium_quality` | Manim video quality |

## Development Status

This extension is currently in early development. The PyCharm plugin is more mature.

See the main [TrueFlow README](../README.md) for full documentation.
