"""
DEPRECATED: This file has been superseded by ManimAutoRenderer.kt + ultimate_architecture_viz.py

The realtime visualization is now handled by:
- ManimAutoRenderer.kt (Kotlin): Buffers events, detects idle cycles
- ultimate_architecture_viz.py (Python): Generates videos

This approach provides better integration with the PyCharm plugin and
avoids maintaining a separate Python socket connection.

DO NOT USE - Kept for reference only.
================================================================================

Real-time Manim Visualization Integration

Connects to RuntimeInstrumentor's socket server to receive trace data
in real-time and generate live Manim animations.
"""

import socket
import json
import threading
import queue
from pathlib import Path
from typing import Optional, Dict, Any
import time
import logging
import sys

from trace_to_manim import TraceParser, ExecutionFlowScene, CallVisualization
from config import VisualizationConfig, get_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | [ManimVisualizer] %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


class RealtimeTraceVisualizer:
    """
    Real-time trace visualizer that connects to RuntimeInstrumentor
    socket server and generates live Manim animations.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5678,
        config: Optional[VisualizationConfig] = None
    ):
        """
        Initialize real-time visualizer.

        Args:
            host: Socket server host
            port: Socket server port (default: 5678 from RuntimeInstrumentor)
            config: Visualization configuration
        """
        self.host = host
        self.port = port
        self.config = config or get_config("medium")

        # Socket connection
        self.socket: Optional[socket.socket] = None
        self.connected = False

        # Trace data queue
        self.trace_queue: queue.Queue = queue.Queue()

        # Trace parser
        self.parser = TraceParser("", filter_path=self.config.filter_path)

        # Background threads
        self.receiver_thread: Optional[threading.Thread] = None
        self.visualizer_thread: Optional[threading.Thread] = None
        self.running = False

        # Statistics
        self.stats = {
            "calls_received": 0,
            "calls_visualized": 0,
            "bytes_received": 0,
            "start_time": None
        }

    def connect(self) -> bool:
        """
        Connect to RuntimeInstrumentor socket server.

        Returns:
            True if connected successfully
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.connected = True
            self.stats["start_time"] = time.time()

            if self.config.verbose_logging:
                logger.info(f"Connected to trace server at {self.host}:{self.port}")

            return True

        except Exception as e:
            logger.error(f"Failed to connect to trace server: {e}")
            self.connected = False
            return False

    def start(self):
        """Start real-time visualization."""
        if not self.connected:
            if not self.connect():
                logger.error("Cannot start visualizer - not connected")
                return

        self.running = True

        # Start receiver thread
        self.receiver_thread = threading.Thread(
            target=self._receive_traces,
            daemon=True
        )
        self.receiver_thread.start()

        # Start visualizer thread
        self.visualizer_thread = threading.Thread(
            target=self._visualize_traces,
            daemon=True
        )
        self.visualizer_thread.start()

        if self.config.verbose_logging:
            logger.info("Real-time visualization started")

    def stop(self):
        """Stop real-time visualization."""
        self.running = False

        if self.receiver_thread:
            self.receiver_thread.join(timeout=2.0)

        if self.visualizer_thread:
            self.visualizer_thread.join(timeout=2.0)

        if self.socket:
            self.socket.close()
            self.connected = False

        self._print_stats()

        if self.config.verbose_logging:
            logger.info("Real-time visualization stopped")

    def _receive_traces(self):
        """Background thread that receives trace data from socket."""
        buffer = ""

        while self.running and self.connected:
            try:
                # Receive data
                data = self.socket.recv(4096)
                if not data:
                    break

                self.stats["bytes_received"] += len(data)
                buffer += data.decode('utf-8')

                # Process complete JSON objects (newline-delimited)
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        try:
                            trace_data = json.loads(line)
                            self.trace_queue.put(trace_data)
                            self.stats["calls_received"] += 1
                        except json.JSONDecodeError as e:
                            if self.config.verbose_logging:
                                logger.info(f"JSON decode error: {e}")

            except socket.timeout:
                continue
            except Exception as e:
                if self.config.verbose_logging:
                    logger.info(f"Error receiving traces: {e}")
                break

    def _visualize_traces(self):
        """Background thread that visualizes received traces."""
        # Buffer calls before rendering
        call_buffer = []
        last_render_time = time.time()
        render_interval = 5.0  # Render every 5 seconds

        while self.running:
            try:
                # Get trace data from queue
                trace_data = self.trace_queue.get(timeout=1.0)

                # Filter to project code (if filter_path is specified)
                file_path = trace_data.get('file_path', '')
                if self.config.filter_path and self.config.filter_path not in file_path:
                    continue

                # Skip excluded packages
                if any(pkg in file_path for pkg in self.config.exclude_packages):
                    continue

                # Add to buffer
                call_buffer.append(trace_data)

                # Render periodically
                current_time = time.time()
                if current_time - last_render_time >= render_interval:
                    if call_buffer:
                        self._render_buffer(call_buffer)
                        call_buffer = []
                        last_render_time = current_time

            except queue.Empty:
                # Render remaining buffer if any
                if call_buffer and time.time() - last_render_time >= render_interval:
                    self._render_buffer(call_buffer)
                    call_buffer = []
                    last_render_time = time.time()
                continue

            except Exception as e:
                if self.config.verbose_logging:
                    logger.info(f"Error visualizing traces: {e}")

    def _render_buffer(self, call_buffer: list):
        """Render buffered calls as Manim animation."""
        if not call_buffer:
            return

        # Limit to max calls
        if len(call_buffer) > self.config.max_calls_to_render:
            call_buffer = call_buffer[-self.config.max_calls_to_render:]

        # Save to project's media/videos directory for PyCharm plugin to find
        # This is where the plugin's ManimVideoPanel looks for videos
        media_dir = Path("media/videos/manim_traces")
        media_dir.mkdir(parents=True, exist_ok=True)

        # Create trace file with timestamp
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        trace_file = media_dir / f"trace_{timestamp}.json"

        with open(trace_file, 'w', encoding='utf-8') as f:
            json.dump({"calls": call_buffer}, f)

        temp_trace_file = trace_file  # Use this for parsing

        # Parse and visualize
        try:
            self.parser.trace_file_path = temp_trace_file
            self.parser.load_trace()
            self.parser.detect_parallel_threads()

            if self.config.verbose_logging:
                logger.info(f"Rendering {len(self.parser.calls)} calls...")
                logger.info(f"Detected {len(self.parser.threads)} parallel threads")

            # Create and render scene
            scene = ExecutionFlowScene(self.parser)
            scene.render()

            self.stats["calls_visualized"] += len(self.parser.calls)

            if self.config.verbose_logging:
                logger.info(f"Rendered animation with {len(self.parser.calls)} calls")

        except Exception as e:
            if self.config.verbose_logging:
                logger.info(f"Error rendering animation: {e}")

        finally:
            # Cleanup
            if temp_trace_file.exists():
                temp_trace_file.unlink()

    def _print_stats(self):
        """Print statistics."""
        if not self.stats["start_time"]:
            return

        duration = time.time() - self.stats["start_time"]
        calls_per_sec = self.stats["calls_received"] / duration if duration > 0 else 0

        logger.info("\n=== Real-time Visualization Statistics ===")
        logger.info(f"Duration: {duration:.2f}s")
        logger.info(f"Calls Received: {self.stats['calls_received']}")
        logger.info(f"Calls Visualized: {self.stats['calls_visualized']}")
        logger.info(f"Bytes Received: {self.stats['bytes_received']:,}")
        logger.info(f"Calls/sec: {calls_per_sec:.2f}")
        logger.info("==========================================\n")


class BatchTraceVisualizer:
    """
    Batch visualizer for post-processing trace files.
    """

    def __init__(self, config: Optional[VisualizationConfig] = None):
        """
        Initialize batch visualizer.

        Args:
            config: Visualization configuration
        """
        self.config = config or get_config("high")

    def visualize_trace_file(
        self,
        trace_file: str,
        output_path: Optional[str] = None
    ) -> str:
        """
        Visualize a trace file.

        Args:
            trace_file: Path to trace JSON file
            output_path: Output video path (default: auto-generated)

        Returns:
            Path to rendered video
        """
        # Parse trace
        logger.info(f"Loading trace file: {trace_file}")
        parser = TraceParser(trace_file, filter_path=self.config.filter_path)
        parser.load_trace()

        logger.info(f"Loaded {len(parser.calls)} calls from {self.config.filter_path}")

        # Limit calls if needed
        if len(parser.calls) > self.config.max_calls_to_render:
            logger.info(f"Limiting to {self.config.max_calls_to_render} most recent calls")
            parser.calls = parser.calls[-self.config.max_calls_to_render:]

        # Detect parallel threads
        parser.detect_parallel_threads()
        logger.info(f"Detected {len(parser.threads)} parallel execution threads")

        # Generate output path
        if output_path is None:
            trace_path = Path(trace_file)
            output_path = str(trace_path.parent / f"{trace_path.stem}_animation.mp4")

        # Create and render scene
        logger.info(f"Rendering animation to {output_path}...")
        scene = ExecutionFlowScene(parser)
        scene.render()

        logger.info(f"Animation saved to {output_path}")
        return output_path

    def visualize_directory(
        self,
        trace_dir: str,
        output_dir: Optional[str] = None
    ) -> list:
        """
        Visualize all trace files in a directory.

        Args:
            trace_dir: Directory containing trace JSON files
            output_dir: Output directory (default: same as trace_dir)

        Returns:
            List of rendered video paths
        """
        trace_path = Path(trace_dir)
        if output_dir is None:
            output_dir = trace_path / "animations"
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        # Find all JSON trace files
        trace_files = list(trace_path.glob("*.json"))
        trace_files += list(trace_path.glob("**/*.json"))

        logger.info(f"Found {len(trace_files)} trace files")

        rendered_videos = []
        for trace_file in trace_files:
            logger.info(f"\nProcessing {trace_file.name}...")
            output_path = str(output_dir / f"{trace_file.stem}_animation.mp4")

            try:
                video_path = self.visualize_trace_file(str(trace_file), output_path)
                rendered_videos.append(video_path)
            except Exception as e:
                logger.info(f"Error processing {trace_file.name}: {e}")

        logger.info(f"\nRendered {len(rendered_videos)} animations to {output_dir}")
        return rendered_videos


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Real-time or batch trace visualization")
    parser.add_argument(
        "--mode",
        choices=["realtime", "batch"],
        default="batch",
        help="Visualization mode"
    )
    parser.add_argument(
        "--trace-file",
        help="Trace file to visualize (batch mode)"
    )
    parser.add_argument(
        "--trace-dir",
        help="Directory of trace files (batch mode)"
    )
    parser.add_argument(
        "--output",
        help="Output path or directory"
    )
    parser.add_argument(
        "--quality",
        choices=["low", "medium", "high", "production"],
        default="medium",
        help="Rendering quality"
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="Trace server host (realtime mode)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5678,
        help="Trace server port (realtime mode)"
    )

    args = parser.parse_args()

    config = get_config(args.quality)

    if args.mode == "realtime":
        # Real-time mode
        visualizer = RealtimeTraceVisualizer(
            host=args.host,
            port=args.port,
            config=config
        )
        visualizer.start()

        try:
            logger.info("Real-time visualization running... Press Ctrl+C to stop")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\nStopping...")
            visualizer.stop()

    else:
        # Batch mode
        visualizer = BatchTraceVisualizer(config=config)

        if args.trace_file:
            visualizer.visualize_trace_file(args.trace_file, args.output)
        elif args.trace_dir:
            visualizer.visualize_directory(args.trace_dir, args.output)
        else:
            logger.info("Error: --trace-file or --trace-dir required for batch mode")
            sys.exit(1)
