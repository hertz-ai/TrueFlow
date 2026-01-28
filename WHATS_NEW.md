# What's New - TrueFlow

## Release Notes 

| Platform | Version |
|----------|---------|
| JetBrains (PyCharm/IntelliJ) | 1.0.205 |
| VS Code (Open VSX) | 0.1.147 |
| VS Code (VS Marketplace) | 0.1.147 |

---

## JetBrains Marketplace (PyCharm/IntelliJ Plugin)

### What's New in 1.0.205

**Interactive 3D Flow Explorer (Three.js)**
Brand new tab in the Manim Video panel featuring a fully interactive 3D visualization:
- **Rotate, zoom, pan** through your code's execution flow
- **Color-coded nodes**: Green (executed), Red (dead code), Orange (partial), Blue (branch points)
- **Click any node** to see function details, call count, duration
- **"Why Not Covered" integration**: Click dead code to see the exact branch condition that blocked it
- **Force-directed layout** automatically organizes functions by call hierarchy
- Real-time stats bar showing total functions, coverage percentage

**Smart Root Cause Analysis for Uncovered Code**
The "Why Not Covered" analysis now intelligently traces up the entire call chain to find the *topmost* executed function that blocked execution. Instead of showing every function in the call stack, you now see exactly where the branch decision was made that prevented your code from running.

**Real Branch Conditions from Source Code**
No more guessing! TrueFlow now parses your actual source code (Python and Java) to show the real branch conditions:
- Before: "condition was False"fii
- After: `if config.enabled and user.is_admin:` with line number for one-click navigation

**Java Instrumentation Support**
Full support for Java projects with:
- Runtime method tracing via Java agent
- AST-based branch analysis using JavaParser
- Branch registry with if/else, switch/case, try/catch, loops
- Call site tracking with branch context

**AI Server Status Badge**
Clear visual indicator next to the status dot:
- **Green + "Managed"**: Server started and controlled by TrueFlow
- **Orange + "External"**: Server running externally (command line, other IDE, etc.)

**Vision Model Improvements**
- Fixed duplicate mmproj download issue
- Better detection of external llama.cpp servers
- Helpful guidance when external server needs vision support

---

## Open VSX Registry (VS Code Extension)

### What's New in 0.1.147

#### Interactive 3D Flow Explorer
Explore your code execution in a stunning 3D environment powered by Three.js:
- **Mouse controls**: Drag to rotate, scroll to zoom, right-drag to pan
- **Visual coding**: Green nodes = executed, Red = dead code, Blue = branch points
- **Click to inspect**: Select any function to see details, timing, call count
- **Why Not Covered**: Dead code nodes show the exact branch condition blocking them

#### Root Cause Tracing
TrueFlow's "Why Not Covered" analysis is now smarter. When investigating why code wasn't executed, it traces up the call chain to find the **root cause** - the topmost function that was executed but chose not to call your code.

#### Actual Branch Conditions
See exactly what condition blocked execution:
```
Function 'process_order' not covered
Root cause: 'validate_user' (line 42)
Branch: if user.is_authenticated and user.has_permission('orders'):
```

#### Java Project Support
TrueFlow now fully supports Java projects:
- Attach the Java agent for runtime tracing
- Branch analysis extracts all control flow structures
- Same rich visualization as Python projects

#### Managed vs External Server Indicator
The AI assistant header now shows whether the llama.cpp server is:
- **Managed** (green): Started by TrueFlow, you can stop it
- **External** (orange): Started elsewhere, read-only access

#### Bug Fixes
- Vision model (mmproj) no longer downloads twice when clicking "Add Vision Support"
- External server detection improved for better UX

---

## Visual Studio Marketplace (VS Code Extension)

### What's New in TrueFlow 0.1.147

**Interactive 3D Visualization**
New Three.js-powered explorer lets you navigate your code's execution flow in 3D:

| Control | Action |
|---------|--------|
| Left-drag | Rotate view |
| Scroll | Zoom in/out |
| Right-drag | Pan |
| Click | Select node |
| Double-click | Focus on node |

Color-coded nodes show execution status at a glance:
- **Green**: Executed functions
- **Red**: Dead code (with "Why Not Covered" details)
- **Blue**: Branch decision points
- **Orange**: Partially covered

**Smarter Dead Code Analysis**
Understanding why code isn't covered is now easier than ever:
- **Root Cause Tracing**: Follows the call chain to the exact function that made the decision
- **Actual Conditions**: Shows real source code conditions like `if x > 0 and is_valid:`
- **Line Numbers**: Click to navigate directly to the branch that blocked execution

**Java Support**
TrueFlow now supports Java projects alongside Python:
- Java agent for runtime instrumentation
- Full branch coverage analysis
- Unified visualization across languages

**AI Server Management**
New status badge shows server ownership:
| Status | Meaning |
|--------|---------|
| Managed | TrueFlow controls the server |
| External | Server started outside TrueFlow |

This helps when multiple tools share the same llama.cpp server.

**Reliability Improvements**
- Fixed vision model download duplication
- Better handling of externally-started AI servers
- Improved error messages for vision setup

---

## Short Description (for store listings)

**One-liner:**
Interactive 3D flow explorer, smart root cause analysis, real branch conditions, Java support.

**Feature bullets:**
- NEW: Interactive 3D visualization with Three.js - rotate, zoom, click to explore
- Root cause tracing finds the *topmost* function blocking execution
- Shows actual branch conditions from source code with line numbers
- Full Java instrumentation support with branch analysis
- AI server badge shows "Managed" vs "External" status
- Fixed vision model download issues

---

## Tags/Keywords
`code-coverage` `dead-code` `runtime-analysis` `python` `java` `llm` `ai-assistant` `visualization` `debugging` `branch-coverage` `3d-visualization` `threejs`
