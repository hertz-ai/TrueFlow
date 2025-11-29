# Contributing to TrueFlow

Thank you for your interest in contributing to TrueFlow! This document provides guidelines for contributing to the project.

## Code of Conduct

Be respectful, inclusive, and constructive. We welcome contributors of all experience levels.

## Getting Started

### Prerequisites

- Python 3.8+ (for runtime injector and Manim)
- JDK 17+ (for PyCharm plugin)
- Node.js 18+ (for VS Code extension)
- Manim (for visualization engine)

### Setting Up Development Environment

```bash
# Clone the repository
git clone https://github.com/trueflow/trueflow.git
cd trueflow

# Set up Python environment
cd runtime_injector
pip install -e .

# Set up Manim visualizer
cd ../manim_visualizer
pip install -r requirements.txt

# Build PyCharm plugin
cd ..
./gradlew build

# Set up VS Code extension
cd vscode-extension
npm install
```

## Project Structure

```
TrueFlow/
├── runtime_injector/     # Python runtime instrumentation
│   └── python_runtime_instrumentor.py
├── manim_visualizer/     # 3D visualization engine
│   └── ultimate_architecture_viz.py
├── src/                  # PyCharm plugin (Kotlin)
│   └── main/kotlin/com/crawl4ai/learningviz/
├── vscode-extension/     # VS Code extension (TypeScript)
│   └── src/extension.ts
├── tests/                # Test suites
└── docs/                 # Documentation
```

## How to Contribute

### Reporting Bugs

1. Search existing issues first
2. Create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Python version, IDE version)

### Suggesting Features

1. Open a Discussion first to gauge interest
2. Describe the use case
3. Propose implementation approach if possible

### Submitting Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Add tests if applicable
5. Run existing tests: `./gradlew test` and `pytest`
6. Commit with clear messages
7. Push and create a Pull Request

### PR Guidelines

- Keep PRs focused on a single change
- Update documentation if needed
- Ensure all tests pass
- Follow existing code style
- Add meaningful commit messages

## Development Workflow

### Python Components (runtime_injector, manim_visualizer)

```bash
# Run tests
pytest tests/

# Check code style
flake8 runtime_injector/ manim_visualizer/

# Format code
black runtime_injector/ manim_visualizer/
```

### PyCharm Plugin (Kotlin)

```bash
# Build
./gradlew build

# Run in sandbox IDE
./gradlew runIde

# Run tests
./gradlew test
```

### VS Code Extension (TypeScript)

```bash
cd vscode-extension

# Compile
npm run compile

# Run linter
npm run lint

# Launch Extension Development Host
# Press F5 in VS Code
```

## Architecture Guidelines

### Runtime Injector

- Must support Python 2.7+ and 3.x
- Zero dependencies for core tracing
- Minimize performance overhead (<2.5%)
- Thread-safe operation

### Manim Visualizer

- Use Manim Community edition
- Keep animations smooth (60fps)
- Support multiple trace formats
- Generate both preview and final quality

### IDE Plugins

- Non-blocking UI operations
- Graceful error handling
- Clear user feedback
- Consistent cross-platform behavior

## Testing

### Unit Tests

Test individual functions and classes in isolation.

### Integration Tests

Test component interactions (e.g., injector -> trace file -> visualizer).

### End-to-End Tests

Test complete workflows from instrumentation to visualization.

## Documentation

- Update README.md for user-facing changes
- Add docstrings to new functions
- Update API documentation if adding public interfaces
- Include examples for new features

## Release Process

1. Update version in gradle.properties and package.json
2. Update CHANGELOG.md
3. Create a release tag
4. Build artifacts
5. Publish to marketplaces

## Questions?

- Open a GitHub Discussion
- Check existing documentation
- Review closed issues for similar questions

Thank you for contributing to TrueFlow!
