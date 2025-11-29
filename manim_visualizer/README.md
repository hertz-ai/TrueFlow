# Manim Trace Visualizer

Animated visualization of execution traces from RuntimeInstrumentor using the Manim animation library.

## Features

- **Automatic Recording**: Auto-starts recording on first execution - no manual setup required
- **Correlation ID Tracking**: Tracks entire execution flow with unique correlation IDs
- **Async/Parallel Support**: Tracks async flows and parallel threads under same correlation ID
- **Replay by Correlation ID**: Replay any execution by its correlation ID
- **Animated Method Call Visualization**: Watch function calls appear in sequence with call hierarchy
- **Data Flow Animation**: See parameter passing and data flow between functions
- **Parallel Execution Visualization**: Multiple threads shown side-by-side with synchronized timelines
- **Multiple Camera System**: Different camera angles tracking parallel execution flows
- **Embodied AI Filtering**: Only visualizes code within the embodied_ai folder
- **Real-time Mode**: Connect to RuntimeInstrumentor socket server for live visualization
- **Batch Mode**: Process existing trace files post-hoc

## Installation

```bash
# Install Manim and dependencies
pip install -r requirements.txt

# On Windows, you may also need to install ffmpeg
# Download from https://ffmpeg.org/download.html
```

## Usage

### Auto-Recording Mode (Recommended)

The easiest way to use the visualizer is with automatic recording:

```python
from manim_visualizer.integration import track_execution

# Decorator automatically records execution with correlation ID
@track_execution("train_model")
def train_model(data):
    # Your code here
    # Everything is automatically recorded!
    pass

train_model(my_data)
# Video automatically generated at: recordings/video_<correlation_id>_<timestamp>.mp4
```

Or use context manager for manual control:

```python
from manim_visualizer.integration import tracked_execution

with tracked_execution("data_processing", {"source": "database"}) as correlation_id:
    # Process data
    # All calls tracked under this correlation_id
    process_data()

# Video automatically generated when context exits
print(f"Replay video for correlation ID: {correlation_id}")
```

Features:
- **Auto-start**: Recording starts automatically on first execution
- **Correlation ID tracking**: Each execution gets unique ID
- **Async support**: Tracks async/await and parallel tasks under same ID
- **Auto-video generation**: Videos generated automatically when execution completes
- **Session management**: List, replay, and manage all recorded sessions

### Listing and Replaying Sessions

```python
from manim_visualizer.integration import get_recorder

recorder = get_recorder()

# List recent sessions
sessions = recorder.list_sessions(limit=10)
for session in sessions:
    print(f"ID: {session.correlation_id}")
    print(f"Entry: {session.entry_point}")
    print(f"Video: {session.video_file}")

# Replay a specific session
video_path = recorder.replay_session(correlation_id)
# Open video_path with your video player
```

### Batch Mode (Post-Processing)

Visualize a single trace file:

```bash
python realtime_visualizer.py --mode batch --trace-file path/to/trace.json --output animation.mp4
```

Visualize all trace files in a directory:

```bash
python realtime_visualizer.py --mode batch --trace-dir traces/ --output-dir animations/
```

With quality settings:

```bash
python realtime_visualizer.py --mode batch --trace-file trace.json --quality high
```

Quality options:
- `low`: 854x480, 15fps (fast rendering, smaller files)
- `medium`: 1280x720, 30fps (default)
- `high`: 1920x1080, 60fps (high quality)
- `production`: 3840x2160, 60fps (4K, very slow)

### Real-time Mode

Start real-time visualization connected to RuntimeInstrumentor:

```bash
python realtime_visualizer.py --mode realtime --host localhost --port 5678
```

This will:
1. Connect to the trace socket server (port 5678)
2. Receive trace data in real-time
3. Generate animations every 5 seconds
4. Filter to embodied_ai folder only

Press Ctrl+C to stop.

### Programmatic Usage

```python
from manim_visualizer import BatchTraceVisualizer, get_config

# Create visualizer with high quality settings
config = get_config("high")
visualizer = BatchTraceVisualizer(config=config)

# Visualize a trace file
video_path = visualizer.visualize_trace_file(
    "traces/session_trace.json",
    output_path="animations/session.mp4"
)

print(f"Animation saved to {video_path}")
```

Real-time visualization:

```python
from manim_visualizer import RealtimeTraceVisualizer, get_config
import time

config = get_config("medium")
visualizer = RealtimeTraceVisualizer(
    host="localhost",
    port=5678,
    config=config
)

visualizer.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    visualizer.stop()
```

## Integration with PyCharm Plugin

### Step 1: Enable RuntimeInstrumentor Socket Server

In your code that uses the PyCharm plugin:

```python
from pycharm_plugin.runtime_injector.python_runtime_instrumentor import (
    RuntimeInstrumentor,
    TraceSocketServer
)

# Create instrumentor
instrumentor = RuntimeInstrumentor(project_root="/path/to/embodied_ai")

# Start socket server for real-time streaming
server = TraceSocketServer(instrumentor, port=5678)
server.start()

# Enable tracing
instrumentor.start_trace()

# Your code here
# ...

# Cleanup
instrumentor.stop_trace()
server.stop()
```

### Step 2: Start Manim Visualizer

In a separate terminal:

```bash
python realtime_visualizer.py --mode realtime
```

### Step 3: Watch Live Animation

As your code executes:
- Function calls are captured by RuntimeInstrumentor
- Sent to socket server on port 5678
- Received by Manim visualizer
- Rendered as animated video every 5 seconds

## Visualization Features

### Call Hierarchy Visualization

Function calls are shown as boxes stacked vertically:
- **Position**: Indented based on call depth
- **Color**:
  - Purple: AI agent methods
  - Blue: Framework methods
  - Green: Async methods
  - White: Regular methods
- **Duration**: Displayed below function name
- **Arrows**: Show parameter flow from parent to child calls

### Parallel Thread Visualization

When multiple threads execute in parallel:
- Threads are positioned horizontally
- Timeline indicator at bottom shows synchronization
- Camera pans across all threads
- Execution is synchronized to actual timestamps

### Data Flow Animation

Parameter passing is visualized with:
- Orange arrows flowing from caller to callee
- Parameter count displayed
- Animation speed proportional to actual execution time

## Configuration

Edit `config.py` to customize:

```python
from manim_visualizer.config import VisualizationConfig

config = VisualizationConfig(
    # Filter settings
    filter_path="embodied_ai",

    # Visual spacing
    call_box_width=4.0,
    vertical_spacing=2.0,

    # Animation timing
    fade_in_time=0.3,
    max_wait_time=2.0,

    # Performance
    max_calls_to_render=100,
    quality="high_quality",
    fps=60,
    resolution=(1920, 1080)
)
```

## Output

Generated animations are saved as:
- Format: MP4 video
- Default location: Same directory as trace file with `_animation.mp4` suffix
- Can be opened with any video player

## Examples

### Example 1: Visualize Episodic Memory Updates

```bash
# Capture trace during episodic memory operation
python -c "
from src.crawl4ai.embodied_ai.memory.episodic_memory import EpisodicMemory
from pycharm_plugin.runtime_injector.python_runtime_instrumentor import RuntimeInstrumentor

instrumentor = RuntimeInstrumentor(project_root='.')
instrumentor.start_trace()

memory = EpisodicMemory()
memory.add_episode(...)

instrumentor.stop_trace()
instrumentor.export_json('episodic_memory_trace.json')
"

# Visualize
python realtime_visualizer.py --mode batch --trace-file episodic_memory_trace.json
```

### Example 2: Real-time Learning Visualization

```bash
# Terminal 1: Start visualizer
python realtime_visualizer.py --mode realtime --quality medium

# Terminal 2: Run learning code with tracing
python -c "
from src.crawl4ai.embodied_ai.learning.reality_grounded_learner import RealityGroundedLearner
from pycharm_plugin.runtime_injector.python_runtime_instrumentor import RuntimeInstrumentor, TraceSocketServer

instrumentor = RuntimeInstrumentor(project_root='.')
server = TraceSocketServer(instrumentor, port=5678)
server.start()
instrumentor.start_trace()

learner = RealityGroundedLearner()
learner.learn_from_reality(...)

instrumentor.stop_trace()
server.stop()
"
```

Watch the animation update every 5 seconds as learning progresses!

## Troubleshooting

### "Connection refused" error

Make sure RuntimeInstrumentor socket server is running:

```python
server = TraceSocketServer(instrumentor, port=5678)
server.start()
```

### No animation generated

Check that:
1. Trace file contains calls from embodied_ai folder
2. Quality settings aren't too high for your system
3. ffmpeg is installed and in PATH

### Animation is too fast/slow

Adjust `timeline_scale` in config:

```python
config.timeline_scale = 0.01  # Lower = faster, higher = slower
```

### Too many calls to render

Increase `max_calls_to_render` or filter more aggressively:

```python
config.max_calls_to_render = 200
config.exclude_packages = ("site-packages", "python3", "typing")
```

## Performance Tips

1. **Use lower quality for development**: `--quality low` renders 5x faster
2. **Limit call count**: Set `max_calls_to_render` appropriately
3. **Filter aggressively**: Add more paths to `exclude_packages`
4. **Batch processing**: Process multiple files overnight with high quality

## Architecture

```
manim_visualizer/
├── trace_to_manim.py       # Core Manim scene generator
├── realtime_visualizer.py  # Real-time and batch visualization
├── config.py               # Configuration and presets
├── requirements.txt        # Dependencies
├── README.md              # This file
└── __init__.py            # Package interface
```

## Future Enhancements

- [ ] 3D visualization for deep call stacks
- [ ] Interactive controls (pause, rewind, step)
- [ ] Heat maps showing hot paths
- [ ] Memory allocation visualization
- [ ] GPU usage tracking
- [ ] Export to GIF for sharing

## License

Part of the crawl4ai embodied AI system.
