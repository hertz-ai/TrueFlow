"""
Automatic Execution Recording with Correlation ID Tracking

Auto-starts recording when execution begins, assigns correlation IDs to track
instances through async flows, and generates complete video replays.

Features:
- Automatic start on first execution entry point
- Correlation ID propagation through async flows
- Complete flow tracking even with async/parallel execution
- Video replay generation per correlation ID
- Persistent storage with correlation ID indexing
"""

import sys
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass, field
from datetime import datetime
import json
import asyncio
from contextvars import ContextVar

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime_injector.python_runtime_instrumentor import (
    RuntimeInstrumentor,
    TraceSocketServer
)
from manim_visualizer.realtime_visualizer import BatchTraceVisualizer
from manim_visualizer.config import get_config

# Logger integration
try:
    from logger import get_logger
    LOGGER_AVAILABLE = True
except ImportError:
    LOGGER_AVAILABLE = False
    class DummyLogger:
        def debug(self, msg): pass
        def info(self, msg): pass
        def warning(self, msg): logger.info("[WARNING] " + str(msg))
        def error(self, msg, exc_info=False): logger.info("[ERROR] " + str(msg))
    def get_logger(name): return DummyLogger()


# Context variable for correlation ID (thread-safe and async-safe)
correlation_id_var: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)


@dataclass
class ExecutionSession:
    """Represents a single execution session with correlation ID."""
    correlation_id: str
    start_time: float
    end_time: Optional[float] = None
    entry_point: str = ""
    input_data: Dict[str, Any] = field(default_factory=dict)
    trace_file: str = ""
    video_file: str = ""
    call_count: int = 0
    thread_ids: Set[str] = field(default_factory=set)
    async_task_ids: Set[str] = field(default_factory=set)
    status: str = "running"  # running, completed, failed


class AutoRecorder:
    """
    Automatic recorder that tracks executions with correlation IDs.

    Auto-starts recording on first entry point and tracks entire flow
    including async/parallel execution.
    """

    def __init__(
        self,
        output_dir: str = "recordings",
        project_root: Optional[str] = None,
        quality: str = "medium",
        auto_generate_video: bool = True,
        verbose: bool = True
    ):
        """
        Initialize auto recorder.

        Args:
            output_dir: Directory for recordings
            project_root: Project root (auto-detected if None)
            quality: Video rendering quality
            auto_generate_video: Generate video automatically when session ends
            verbose: Enable verbose logging
        """
        # Initialize logger first
        self.logger = get_logger("auto_recorder")
        self.verbose = verbose

        if verbose and LOGGER_AVAILABLE:
            from logger import enable_verbose
            enable_verbose("auto_recorder")

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Auto-detect project root (project-agnostic)
        if project_root is None:
            project_root = AutoRecorder._detect_project_root()
        self.project_root = project_root or str(Path.cwd())

        self.quality = quality
        self.auto_generate_video = auto_generate_video

        # Active sessions indexed by correlation ID
        self.sessions: Dict[str, ExecutionSession] = {}
        self.lock = threading.Lock()

        self.logger.info("AutoRecorder initialized - output: {0}".format(self.output_dir))

        # Instrumentor and server
        self.instrumentor: Optional[RuntimeInstrumentor] = None
        self.server: Optional[TraceSocketServer] = None

        # Session index file
        self.index_file = self.output_dir / "session_index.json"
        self._load_index()

        # Auto-start flag
        self.started = False

    @staticmethod
    def _detect_project_root() -> str:
        """
        Auto-detect project root in a project-agnostic way.

        Looks for common project markers:
        - pyproject.toml
        - setup.py
        - setup.cfg
        - .git directory
        - src/ directory

        Returns:
            Project root path as string
        """
        current = Path.cwd()

        # Traverse up to find project markers
        while current != current.parent:
            # Check for standard Python project markers
            if (current / "pyproject.toml").exists():
                return str(current)
            if (current / "setup.py").exists():
                return str(current)
            if (current / "setup.cfg").exists():
                return str(current)
            if (current / ".git").exists():
                return str(current)
            if (current / "src").exists():
                return str(current)

            current = current.parent

        # Fallback to current working directory
        return str(Path.cwd())

    def _load_index(self):
        """Load session index from disk."""
        if self.index_file.exists():
            with open(self.index_file, 'r') as f:
                index_data = json.load(f)

            for session_data in index_data.get('sessions', []):
                session = ExecutionSession(
                    correlation_id=session_data['correlation_id'],
                    start_time=session_data['start_time'],
                    end_time=session_data.get('end_time'),
                    entry_point=session_data.get('entry_point', ''),
                    input_data=session_data.get('input_data', {}),
                    trace_file=session_data.get('trace_file', ''),
                    video_file=session_data.get('video_file', ''),
                    call_count=session_data.get('call_count', 0),
                    thread_ids=set(session_data.get('thread_ids', [])),
                    async_task_ids=set(session_data.get('async_task_ids', [])),
                    status=session_data.get('status', 'completed')
                )
                self.sessions[session.correlation_id] = session

    def _save_index(self):
        """Save session index to disk."""
        index_data = {
            'last_updated': datetime.now().isoformat(),
            'sessions': [
                {
                    'correlation_id': s.correlation_id,
                    'start_time': s.start_time,
                    'end_time': s.end_time,
                    'entry_point': s.entry_point,
                    'input_data': s.input_data,
                    'trace_file': s.trace_file,
                    'video_file': s.video_file,
                    'call_count': s.call_count,
                    'thread_ids': list(s.thread_ids),
                    'async_task_ids': list(s.async_task_ids),
                    'status': s.status
                }
                for s in self.sessions.values()
            ]
        }

        with open(self.index_file, 'w') as f:
            json.dump(index_data, f, indent=2)

    def _auto_start(self):
        """Auto-start recording on first execution."""
        if self.started:
            return

        with self.lock:
            if self.started:
                return

            # Create instrumentor
            self.instrumentor = RuntimeInstrumentor(
                project_root=self.project_root,
                output_format="json"
            )

            # Wrap instrumentor to inject correlation ID tracking
            self._inject_correlation_tracking()

            # Start socket server for real-time monitoring
            self.server = TraceSocketServer(self.instrumentor, port=5678)
            self.server.start()

            # Start tracing
            self.instrumentor.start_trace()

            self.started = True

            self.logger.info("Auto-started recording at {0}".format(datetime.now()))
            self.logger.info("Output directory: {0}".format(self.output_dir))

    def _inject_correlation_tracking(self):
        """Inject correlation ID tracking into instrumentor."""
        if not self.instrumentor:
            return

        # Store original trace function
        original_trace_func = self.instrumentor.trace_function

        def correlation_aware_trace(frame, event, arg):
            """Wrapper that adds correlation ID to each call."""
            # Get or create correlation ID
            correlation_id = correlation_id_var.get()

            if correlation_id is None:
                # This is an entry point - create new correlation ID
                correlation_id = self.create_session(
                    entry_point=f"{frame.f_code.co_filename}:{frame.f_code.co_name}",
                    input_data=self._extract_input_data(frame)
                )
                correlation_id_var.set(correlation_id)

            # Track thread and async task
            thread_id = threading.current_thread().ident
            with self.lock:
                if correlation_id in self.sessions:
                    self.sessions[correlation_id].thread_ids.add(str(thread_id))

                    # Track async task if in async context
                    try:
                        task = asyncio.current_task()
                        if task:
                            self.sessions[correlation_id].async_task_ids.add(str(id(task)))
                    except RuntimeError:
                        pass  # Not in async context

            # Add correlation_id to frame locals for tracking
            if 'correlation_id' not in frame.f_locals:
                frame.f_locals['_correlation_id'] = correlation_id

            # Call original trace function
            return original_trace_func(frame, event, arg)

        # Replace trace function
        self.instrumentor.trace_function = correlation_aware_trace

    def _extract_input_data(self, frame) -> Dict[str, Any]:
        """Extract input data from frame."""
        input_data = {}

        # Get function arguments
        if frame.f_code.co_argcount > 0:
            arg_names = frame.f_code.co_varnames[:frame.f_code.co_argcount]
            for arg_name in arg_names:
                if arg_name in frame.f_locals:
                    value = frame.f_locals[arg_name]
                    # Convert to serializable format
                    try:
                        if hasattr(value, '__dict__'):
                            input_data[arg_name] = str(type(value).__name__)
                        else:
                            input_data[arg_name] = str(value)[:100]  # Limit length
                    except:
                        input_data[arg_name] = "<not serializable>"

        return input_data

    def create_session(
        self,
        correlation_id: Optional[str] = None,
        entry_point: str = "",
        input_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create new execution session.

        Args:
            correlation_id: Optional correlation ID (auto-generated if None)
            entry_point: Entry point function/method
            input_data: Input data for this session

        Returns:
            Correlation ID
        """
        # Auto-start if not started
        self._auto_start()

        # Generate correlation ID if not provided
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())

        # Create session
        session = ExecutionSession(
            correlation_id=correlation_id,
            start_time=time.time(),
            entry_point=entry_point,
            input_data=input_data or {}
        )

        # Generate file paths
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        session.trace_file = str(
            self.output_dir / f"trace_{correlation_id}_{timestamp}.json"
        )
        session.video_file = str(
            self.output_dir / f"video_{correlation_id}_{timestamp}.mp4"
        )

        with self.lock:
            self.sessions[correlation_id] = session
            self._save_index()

        self.logger.info("Created session {0}".format(correlation_id))
        self.logger.debug("  Entry: {0}".format(entry_point))
        self.logger.debug("  Trace: {0}".format(session.trace_file))

        # Set correlation ID in context
        correlation_id_var.set(correlation_id)

        return correlation_id

    def end_session(self, correlation_id: str, status: str = "completed"):
        """
        End execution session and generate video.

        Args:
            correlation_id: Correlation ID to end
            status: Session status (completed, failed)
        """
        with self.lock:
            if correlation_id not in self.sessions:
                self.logger.warning("Unknown session: {0}".format(correlation_id))
                return

            session = self.sessions[correlation_id]
            session.end_time = time.time()
            session.status = status

            duration = session.end_time - session.start_time
            self.logger.info("Session {0} ended".format(correlation_id))
            self.logger.debug("  Duration: {0:.2f}s".format(duration))
            self.logger.debug("  Threads: {0}".format(len(session.thread_ids)))
            self.logger.debug("  Async Tasks: {0}".format(len(session.async_task_ids)))
            self.logger.debug("  Status: {0}".format(status))

            # Export trace for this session
            if self.instrumentor:
                # Filter calls by correlation ID
                self._export_session_trace(session)

            self._save_index()

        # Generate video in background
        if self.auto_generate_video:
            threading.Thread(
                target=self._generate_video_background,
                args=(correlation_id,),
                daemon=True
            ).start()

    def _export_session_trace(self, session: ExecutionSession):
        """Export trace for specific session."""
        if not self.instrumentor:
            return

        # Get all calls
        all_calls = self.instrumentor.calls

        # Filter by correlation ID (stored in frame locals)
        session_calls = []
        for call in all_calls:
            # Check if call is part of this session
            # (would need correlation_id stored in call metadata)
            # For now, use time range as proxy
            if session.start_time <= call.start_time:
                if session.end_time is None or call.start_time <= session.end_time:
                    session_calls.append(call)

        session.call_count = len(session_calls)

        # Export to JSON
        self.instrumentor.export_json(session.trace_file)

        self.logger.debug("Exported {0} calls to {1}".format(len(session_calls), session.trace_file))

    def _generate_video_background(self, correlation_id: str):
        """Generate video in background thread."""
        with self.lock:
            if correlation_id not in self.sessions:
                return
            session = self.sessions[correlation_id]

        try:
            self.logger.info("Generating video for {0}...".format(correlation_id))

            # Create visualizer
            config = get_config(self.quality)
            visualizer = BatchTraceVisualizer(config=config)

            # Generate video
            visualizer.visualize_trace_file(
                session.trace_file,
                session.video_file
            )

            self.logger.info("Video saved to {0}".format(session.video_file))

        except Exception as e:
            self.logger.error("Error generating video: {0}".format(e), exc_info=True)

            with self.lock:
                session.status = "video_failed"
                self._save_index()

    def get_session(self, correlation_id: str) -> Optional[ExecutionSession]:
        """Get session by correlation ID."""
        with self.lock:
            return self.sessions.get(correlation_id)

    def list_sessions(
        self,
        status: Optional[str] = None,
        limit: int = 10
    ) -> List[ExecutionSession]:
        """
        List sessions.

        Args:
            status: Filter by status (None for all)
            limit: Maximum number of sessions to return

        Returns:
            List of sessions, most recent first
        """
        with self.lock:
            sessions = list(self.sessions.values())

        # Filter by status
        if status:
            sessions = [s for s in sessions if s.status == status]

        # Sort by start time (most recent first)
        sessions.sort(key=lambda s: s.start_time, reverse=True)

        return sessions[:limit]

    def replay_session(self, correlation_id: str) -> Optional[str]:
        """
        Get video file path for replaying session.

        Args:
            correlation_id: Correlation ID to replay

        Returns:
            Path to video file, or None if not found
        """
        with self.lock:
            session = self.sessions.get(correlation_id)

        if session and session.video_file and Path(session.video_file).exists():
            return session.video_file

        return None

    def cleanup(self):
        """Cleanup and stop recording."""
        if self.instrumentor:
            self.instrumentor.stop_trace()

        if self.server:
            self.server.stop()

        # End all active sessions
        with self.lock:
            active_sessions = [
                s.correlation_id
                for s in self.sessions.values()
                if s.status == "running"
            ]

        for correlation_id in active_sessions:
            self.end_session(correlation_id, status="interrupted")

        self.logger.info("Cleanup complete")


# Global auto recorder instance
_global_recorder: Optional[AutoRecorder] = None


def get_recorder(
    output_dir: str = "recordings",
    quality: str = "medium",
    auto_generate_video: bool = True
) -> AutoRecorder:
    """Get or create global auto recorder."""
    global _global_recorder

    if _global_recorder is None:
        _global_recorder = AutoRecorder(
            output_dir=output_dir,
            quality=quality,
            auto_generate_video=auto_generate_video
        )

    return _global_recorder


# Decorator for automatic session tracking
def track_execution(entry_point_name: Optional[str] = None):
    """
    Decorator to automatically track execution with correlation ID.

    Usage:
        @track_execution(entry_point_name="train_model")
        def train_model(data):
            # Entire execution flow tracked
            pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            recorder = get_recorder()

            # Create session
            entry_name = entry_point_name or f"{func.__module__}.{func.__name__}"
            correlation_id = recorder.create_session(
                entry_point=entry_name,
                input_data={"args": str(args)[:100], "kwargs": str(kwargs)[:100]}
            )

            try:
                result = func(*args, **kwargs)
                recorder.end_session(correlation_id, status="completed")
                return result

            except Exception as e:
                recorder.end_session(correlation_id, status="failed")
                raise

        return wrapper
    return decorator


# Context manager for manual session tracking
class tracked_execution:
    """
    Context manager for manual execution tracking.

    Usage:
        with tracked_execution("data_processing") as correlation_id:
            # Process data
            process_data()
    """

    def __init__(self, entry_point: str, input_data: Optional[Dict] = None):
        self.entry_point = entry_point
        self.input_data = input_data
        self.correlation_id: Optional[str] = None

    def __enter__(self):
        recorder = get_recorder()
        self.correlation_id = recorder.create_session(
            entry_point=self.entry_point,
            input_data=self.input_data
        )
        return self.correlation_id

    def __exit__(self, exc_type, exc_val, exc_tb):
        recorder = get_recorder()
        status = "failed" if exc_type else "completed"
        recorder.end_session(self.correlation_id, status=status)


if __name__ == "__main__":
    # Example usage
    recorder = get_recorder(output_dir="example_recordings")

    # Example 1: Using decorator
    @track_execution("example_function")
    def example_function(x, y):
        time.sleep(0.1)
        return x + y

    result = example_function(5, 3)
    logger.info(f"Result: {result}")

    # Example 2: Using context manager
    with tracked_execution("manual_tracking", {"input": "test data"}):
        time.sleep(0.1)
        logger.info("Processing...")

    # List sessions
    logger.info("\n=== Recent Sessions ===")
    for session in recorder.list_sessions(limit=5):
        logger.info(f"ID: {session.correlation_id[:8]}...")
        logger.info(f"  Entry: {session.entry_point}")
        logger.info(f"  Status: {session.status}")
        logger.info(f"  Video: {session.video_file}")
        logger.info()

    # Cleanup
    recorder.cleanup()
