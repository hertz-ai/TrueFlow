# Changelog

## [0.1.147] - 2025-12-30

### Added
- **Interactive 3D Flow Explorer**: New Three.js-powered visualization with rotate, zoom, pan controls
  - Color-coded nodes: Green (executed), Red (dead), Blue (branch points), Orange (partial)
  - Click any node for function details, timing, call count
  - Dead code nodes show "Why Not Covered" with actual branch conditions
  - Force-directed layout organizes by call hierarchy
- **Smart Root Cause Analysis**: "Why Not Covered" now traces the entire call chain to find the *topmost* executed function that blocked execution, not just immediate callers
- **Actual Branch Conditions**: Shows real code conditions like `if config.enabled and user.is_admin:` instead of generic "condition was False"
- **Java Instrumentation Support**: Full branch analysis for Java projects with JavaParser-based AST extraction
- **Server Status Badge**: Clear visual indicator showing whether AI server is "Managed" (started by TrueFlow) or "External" (started elsewhere)

### Improved
- Branch registry now includes line numbers for one-click navigation to uncovered branches
- Better mmproj (vision model) download handling - prevents duplicate downloads
- External server detection with helpful guidance for vision model setup

### Fixed
- Vision support now properly detects when external llama.cpp server needs mmproj flag
- Duplicate mmproj download requests are now prevented

---

## [0.1.0] - 2025-01-29

### Added
- Initial release
- Zero-code Python runtime instrumentation
- Real-time trace viewer with WebSocket streaming
- 3D Manim video generation for execution visualization
- Performance analysis with flamegraph-style views
- Dead code detection panel
- AI-powered code explanations with local LLM support
- Vision model support (Qwen3-VL) for analyzing diagrams
- Multiple export formats: PlantUML, Mermaid, D2, JSON, Markdown
- Context injection from performance/dead code panels to AI chat
- Auto-integration into Python projects
