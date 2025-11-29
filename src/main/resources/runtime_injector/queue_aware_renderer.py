"""
DEPRECATED: This file has been superseded by ManimAutoRenderer.kt

The queue-aware rendering is now handled by ManimAutoRenderer.kt which:
- Uses 5-second idle detection instead of LLM queue status
- Deduplicates videos using path hashing
- Integrates directly with the PyCharm plugin

DO NOT USE - Kept for reference only.
================================================================================

Queue-Aware Video Renderer

Generates ONE comprehensive architecture video only when LLM is available.
Skips rendering if LLM queue is busy to avoid overwhelming the system.
"""

import json
import time
import requests
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import threading

# Import logging configuration
from logging_config import get_queue_renderer_logger

# Initialize logger
logger = get_queue_renderer_logger()


class LLMQueueChecker:
    """Check if LLM is available and not busy."""

    def __init__(self, llm_url: str = "http://localhost:8000/v1/chat/completions"):
        self.llm_url = llm_url
        self.last_check_time = 0
        self.check_interval = 60.0  # Check at most once per minute
        self.cached_status = {"available": False, "queue_depth": 0}
        self.lock = threading.Lock()

    def is_llm_available(self, quick_check: bool = True) -> bool:
        """
        Check if LLM is available for use.

        Args:
            quick_check: If True, use cached status if recent check was done

        Returns:
            True if LLM is available and queue is not busy
        """
        with self.lock:
            current_time = time.time()

            # Use cached status if check was recent
            if quick_check and (current_time - self.last_check_time) < self.check_interval:
                return self.cached_status["available"]

            # Perform actual check
            try:
                # Send minimal ping request
                response = requests.post(
                    self.llm_url,
                    json={
                        "model": "Qwen3-VL-2B-Instruct",
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                        "temperature": 0.0
                    },
                    timeout=2.0  # Short timeout - if it takes longer, assume busy
                )

                if response.status_code == 200:
                    self.cached_status["available"] = True
                    self.cached_status["queue_depth"] = 0
                    logger.info("LLM available and ready")
                else:
                    self.cached_status["available"] = False
                    logger.info(f"LLM not available (status {response.status_code})")

            except requests.exceptions.Timeout:
                # Timeout means LLM is busy processing
                self.cached_status["available"] = False
                self.cached_status["queue_depth"] = 1  # Assume at least one request queued
                logger.info("LLM busy (timeout)")

            except Exception as e:
                # Any other error means not available
                self.cached_status["available"] = False
                logger.warning(f"LLM not available ({e})")

            self.last_check_time = current_time
            return self.cached_status["available"]


class QueueAwareRenderer:
    """
    Renders ONE comprehensive architecture video when LLM is available.

    Strategy:
    - Check if LLM is available before rendering
    - If busy, skip and defer to next opportunity
    - Only generate ONE video showing entire system architecture
    - Use hardcoded mapping for most operations
    - Use LLM only for unmappable operations (async, when available)
    """

    def __init__(self, trace_dir: str = "../manim_traces"):
        self.trace_dir = Path(trace_dir)
        self.llm_checker = LLMQueueChecker()
        self.render_queue = []
        self.rendered_videos = set()  # Track what's already rendered
        self.video_dir = Path("media/videos/manim_traces")
        self.video_dir.mkdir(parents=True, exist_ok=True)

        # State file to track what's been rendered
        self.state_file = self.video_dir / "rendered_state.json"
        self.load_state()

    def load_state(self):
        """Load previously rendered videos from state file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.rendered_videos = set(state.get("rendered", []))
                    logger.info(f"Loaded {len(self.rendered_videos)} previously rendered videos")
            except Exception as e:
                logger.warning(f"Could not load state: {e}")

    def save_state(self):
        """Save rendered videos to state file."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump({"rendered": list(self.rendered_videos)}, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save state: {e}")

    def should_render(self, trace_file: Path) -> bool:
        """
        Decide if this trace should be rendered.

        Criteria:
        1. Not already rendered
        2. LLM is available (or trace doesn't need LLM)
        3. Trace represents complete system architecture
        """
        # Check if already rendered
        if trace_file.stem in self.rendered_videos:
            logger.debug(f"{trace_file.name} - already rendered")
            return False

        # Check if this is a comprehensive trace (heuristic: has many operations)
        try:
            with open(trace_file, 'r') as f:
                trace_data = json.load(f)
                call_count = len(trace_data.get("calls", []))

                # Only render if it's a substantial trace
                if call_count < 50:
                    logger.debug(f"{trace_file.name} - too small ({call_count} calls)")
                    return False

                logger.info(f"{trace_file.name} - {call_count} calls")
                return True

        except Exception as e:
            logger.error(f"Could not read {trace_file.name}: {e}")
            return False

    def needs_llm(self, trace_file: Path) -> bool:
        """
        Check if trace has operations that need LLM classification.

        Most operations use hardcoded mapping, only unknown ones need LLM.
        """
        try:
            with open(trace_file, 'r') as f:
                trace_data = json.load(f)

                # Import detector to check
                import sys
                sys.path.insert(0, str(Path(__file__).parent))
                from advanced_operation_viz import OperationDetector

                # Count how many operations fall back to method_call
                unknown_count = 0
                total_count = 0

                for call in trace_data.get("calls", []):
                    total_count += 1
                    op_type = OperationDetector.detect_operation_type(call)
                    if op_type == "method_call":
                        unknown_count += 1

                unknown_ratio = unknown_count / max(total_count, 1)

                if unknown_ratio > 0.1:  # More than 10% unknown
                    logger.debug(f"{trace_file.name} needs LLM ({unknown_count}/{total_count} unknown)")
                    return True
                else:
                    logger.debug(f"{trace_file.name} can use hardcoded mapping")
                    return False

        except Exception as e:
            logger.error(f"Could not analyze {trace_file.name}: {e}")
            return False

    def render_architecture_video(self, trace_file: Path, use_llm: bool = False):
        """
        Render ONE comprehensive architecture video for the trace.

        This creates a complete source-to-sink visualization showing:
        - Entry point → All intermediate steps → Final output
        - Data passing animations between ALL layers/methods/operations
        - Transformations at each step
        - Pattern-specific visualization (neural network, pipeline, recursive, etc.)

        Args:
            trace_file: Path to trace JSON
            use_llm: Whether to enable LLM for operation classification
        """
        logger.info("="*60)
        logger.info("Starting SOURCE-TO-SINK video generation")
        logger.info(f"Trace file: {trace_file.name}")
        logger.info(f"LLM enabled: {use_llm}")
        logger.info("Will show complete execution flow from entry to exit")
        logger.info("With data passing animations between all operations")
        logger.info("="*60)

        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent))

            # Use procedural trace viz for comprehensive architecture view
            from procedural_trace_viz import ProceduralTraceScene
            from manim import config

            # Configure Manim
            config.quality = 'medium_quality'  # Balance between quality and speed
            config.output_file = f"source_to_sink__{trace_file.stem}"

            logger.info("Creating ProceduralTraceScene...")
            logger.info("This will:")
            logger.info("1. Analyze execution pattern")
            logger.info("2. Build complete execution graph")
            logger.info("3. Create 3D visualization")
            logger.info("4. Animate data flow from source to sink")

            # Create and render scene
            scene = ProceduralTraceScene(str(trace_file))
            scene.render()

            video_path = scene.renderer.file_writer.movie_file_path
            logger.info("="*60)
            logger.info("Complete source-to-sink video rendered!")
            logger.info(f"Video path: {video_path}")
            logger.info("Shows entire execution cycle with data flow")
            logger.info("="*60)

            # Mark as rendered
            self.rendered_videos.add(trace_file.stem)
            self.save_state()

            return video_path

        except Exception as e:
            logger.error(f"Rendering failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def process_queue(self):
        """
        Process rendering queue intelligently.

        Strategy:
        1. Check if LLM is available
        2. Find ONE good candidate trace
        3. Determine if it needs LLM
        4. Render only if LLM available OR trace doesn't need LLM
        5. Stop after rendering one video
        """
        logger.info("="*60)
        logger.info("QUEUE-AWARE VIDEO RENDERER")
        logger.info("="*60)

        # Find trace files
        trace_files = list(self.trace_dir.glob("trace_*.json"))
        logger.info(f"Found {len(trace_files)} trace files")

        if not trace_files:
            logger.info("No trace files to process")
            return

        # Check LLM availability
        llm_available = self.llm_checker.is_llm_available(quick_check=False)

        # Find best candidate
        best_candidate = None
        for trace_file in sorted(trace_files, key=lambda x: x.stat().st_mtime, reverse=True):
            if self.should_render(trace_file):
                needs_llm = self.needs_llm(trace_file)

                if needs_llm and not llm_available:
                    logger.info(f"{trace_file.name} needs LLM, but LLM is busy - skipping")
                    continue

                best_candidate = trace_file
                break

        if not best_candidate:
            logger.info("No suitable candidate found (all rendered or require busy LLM)")
            return

        # Render the ONE best candidate
        logger.info(f"Selected: {best_candidate.name}")
        use_llm = llm_available and self.needs_llm(best_candidate)

        video_path = self.render_architecture_video(best_candidate, use_llm=use_llm)

        if video_path:
            logger.info("="*60)
            logger.info("Architecture video ready!")
            logger.info(f"Video path: {video_path}")
            logger.info("="*60)
        else:
            logger.error("Video generation failed")


def main():
    """Main entry point."""
    renderer = QueueAwareRenderer()
    renderer.process_queue()


if __name__ == "__main__":
    main()
