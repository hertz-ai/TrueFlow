from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Auto-Recording Example with Correlation ID Tracking

Demonstrates automatic recording that starts on first execution,
tracks correlation IDs through async flows, and generates replay videos.
"""

import sys
import time
import asyncio
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from manim_visualizer.integration import track_execution, tracked_execution, get_recorder


# Example 1: Simple synchronous execution with auto-recording
@track_execution("simple_sync_function")
def simple_function(x: int, y: int) -> int:
    """Simple function that gets auto-recorded."""
    logger.info(f"Computing {x} + {y}")
    time.sleep(0.1)
    result = x + y
    logger.info(f"Result: {result}")
    return result


# Example 2: Function with nested calls
@track_execution("nested_computation")
def nested_function(n: int) -> int:
    """Function with nested calls - all tracked under same correlation ID."""
    logger.info(f"Processing n={n}")

    def helper(x):
        logger.info(f"  Helper processing {x}")
        time.sleep(0.05)
        return x * 2

    total = 0
    for i in range(n):
        total += helper(i)

    logger.info(f"Total: {total}")
    return total


# Example 3: Async function with parallel tasks
@track_execution("async_parallel_execution")
async def async_function_with_parallel_tasks():
    """Async function with parallel tasks - all under same correlation ID."""
    logger.info("Starting async parallel tasks...")

    async def task1():
        logger.info("  Task 1 starting")
        await asyncio.sleep(0.1)
        logger.info("  Task 1 done")
        return "result1"

    async def task2():
        logger.info("  Task 2 starting")
        await asyncio.sleep(0.15)
        logger.info("  Task 2 done")
        return "result2"

    async def task3():
        logger.info("  Task 3 starting")
        await asyncio.sleep(0.12)
        logger.info("  Task 3 done")
        return "result3"

    # Run tasks in parallel - all tracked under same correlation ID
    results = await asyncio.gather(task1(), task2(), task3())
    logger.info(f"All tasks complete: {results}")
    return results


# Example 4: Manual correlation ID tracking
def manual_tracking_example():
    """Manual tracking with context manager."""
    logger.info("\n=== Manual Tracking Example ===")

    with tracked_execution("data_processing", {"source": "database"}) as correlation_id:
        logger.info(f"Processing with correlation ID: {correlation_id}")

        # Simulate data processing
        time.sleep(0.1)
        logger.info("  Loading data...")
        time.sleep(0.1)
        logger.info("  Processing data...")
        time.sleep(0.1)
        logger.info("  Saving results...")

        logger.info(f"Processing complete (correlation ID: {correlation_id})")


# Example 5: Simulated embodied_ai workflow
@track_execution("embodied_ai_learning_workflow")
def embodied_ai_workflow():
    """Simulate embodied AI learning workflow with multiple components."""
    logger.info("\n=== Embodied AI Learning Workflow ===")

    try:
        from crawl4ai.embodied_ai.memory.episodic_memory import EpisodicMemory
        from crawl4ai.embodied_ai.learning.temporal_coherence import TemporalCoherence

        logger.info("1. Initializing memory system...")
        memory = EpisodicMemory(capacity=100)

        logger.info("2. Adding episodes...")
        for i in range(5):
            memory.add_episode(
                observation={"step": i, "data": f"obs_{i}"},
                action={"type": f"action_{i}"},
                reward=0.5 + i * 0.1,
                next_observation={"step": i+1, "data": f"obs_{i+1}"},
                done=False,
                metadata={"episode": i}
            )
            time.sleep(0.05)

        logger.info("3. Initializing temporal coherence tracker...")
        import torch
        temporal = TemporalCoherence(window_size=10, device="cpu")

        logger.info("4. Tracking predictions...")
        for i in range(5):
            pred = torch.randn(1, 128)
            temporal.track_prediction(
                prediction=pred,
                timestamp=i * 0.1,
                metadata={"step": i}
            )
            time.sleep(0.05)

        logger.info("5. Checking coherence...")
        is_coherent = temporal.check_coherence(threshold=0.8)
        logger.info(f"   Coherence status: {is_coherent}")

        logger.info("6. Retrieving similar episodes...")
        query = {"step": 2, "data": "obs_2"}
        similar = memory.retrieve_similar(query, k=3)
        logger.info(f"   Retrieved {len(similar)} similar episodes")

        logger.info("\nWorkflow complete!")
        return True

    except ImportError as e:
        logger.info(f"Could not import embodied_ai modules: {e}")
        logger.info("Running simplified simulation instead...")

        # Simplified simulation without actual imports
        logger.info("1. Simulating memory operations...")
        time.sleep(0.2)
        logger.info("2. Simulating learning...")
        time.sleep(0.2)
        logger.info("3. Simulating coherence checking...")
        time.sleep(0.2)
        logger.info("Simulation complete!")
        return True


# Example 6: Multiple concurrent sessions
def multiple_concurrent_sessions():
    """Demonstrate multiple concurrent sessions with different correlation IDs."""
    logger.info("\n=== Multiple Concurrent Sessions ===")

    import threading

    def session_worker(session_id: int):
        """Worker function for concurrent session."""
        with tracked_execution(
            f"concurrent_session_{session_id}",
            {"session_id": session_id}
        ) as correlation_id:
            logger.info(f"Session {session_id} started (correlation: {correlation_id[:8]}...)")

            # Simulate work
            for i in range(3):
                logger.info(f"  Session {session_id}: step {i+1}")
                time.sleep(0.1)

            logger.info(f"Session {session_id} complete")

    # Start multiple concurrent sessions
    threads = []
    for i in range(3):
        thread = threading.Thread(target=session_worker, args=(i,))
        thread.start()
        threads.append(thread)
        time.sleep(0.05)  # Stagger starts

    # Wait for all sessions to complete
    for thread in threads:
        thread.join()

    logger.info("All concurrent sessions complete!")


def run_all_examples():
    """Run all examples and show session management."""
    logger.info("\n" + "="*70)
    logger.info("AUTO-RECORDING WITH CORRELATION ID TRACKING EXAMPLES")
    logger.info("="*70)

    # Get recorder instance
    recorder = get_recorder(
        output_dir="auto_recordings",
        quality="medium",
        auto_generate_video=True
    )

    logger.info("\nRecorder initialized. Auto-start will trigger on first execution.\n")

    try:
        # Example 1: Simple sync
        logger.info("\n" + "-"*70)
        logger.info("Example 1: Simple Synchronous Function")
        logger.info("-"*70)
        result = simple_function(5, 3)
        logger.info(f"Returned: {result}")

        time.sleep(1)  # Allow time for recording

        # Example 2: Nested calls
        logger.info("\n" + "-"*70)
        logger.info("Example 2: Nested Function Calls")
        logger.info("-"*70)
        result = nested_function(5)
        logger.info(f"Returned: {result}")

        time.sleep(1)

        # Example 3: Async parallel
        logger.info("\n" + "-"*70)
        logger.info("Example 3: Async Parallel Tasks")
        logger.info("-"*70)
        result = asyncio.run(async_function_with_parallel_tasks())
        logger.info(f"Returned: {result}")

        time.sleep(1)

        # Example 4: Manual tracking
        logger.info("\n" + "-"*70)
        logger.info("Example 4: Manual Correlation ID Tracking")
        logger.info("-"*70)
        manual_tracking_example()

        time.sleep(1)

        # Example 5: Embodied AI workflow
        logger.info("\n" + "-"*70)
        logger.info("Example 5: Embodied AI Learning Workflow")
        logger.info("-"*70)
        embodied_ai_workflow()

        time.sleep(1)

        # Example 6: Multiple concurrent sessions
        logger.info("\n" + "-"*70)
        logger.info("Example 6: Multiple Concurrent Sessions")
        logger.info("-"*70)
        multiple_concurrent_sessions()

        time.sleep(2)  # Allow all recordings to finish

        # Show session summary
        logger.info("\n" + "="*70)
        logger.info("SESSION SUMMARY")
        logger.info("="*70)

        sessions = recorder.list_sessions(limit=20)
        logger.info(f"\nTotal sessions: {len(sessions)}")

        for i, session in enumerate(sessions, 1):
            logger.info(f"\n{i}. Session {session.correlation_id[:16]}...")
            logger.info(f"   Entry Point: {session.entry_point}")
            logger.info(f"   Status: {session.status}")
            logger.info(f"   Duration: {session.end_time - session.start_time:.2f}s" if session.end_time else "   Duration: (running)")
            logger.info(f"   Calls: {session.call_count}")
            logger.info(f"   Threads: {len(session.thread_ids)}")
            logger.info(f"   Async Tasks: {len(session.async_task_ids)}")
            logger.info(f"   Trace File: {Path(session.trace_file).name}")
            logger.info(f"   Video File: {Path(session.video_file).name}")

            # Check if video was generated
            if Path(session.video_file).exists():
                logger.info("   Video: GENERATED")
            else:
                logger.info("   Video: (generating...)")

        # Show how to replay a session
        logger.info("\n" + "="*70)
        logger.info("HOW TO REPLAY A SESSION")
        logger.info("="*70)

        if sessions:
            latest = sessions[0]
            video_path = recorder.replay_session(latest.correlation_id)

            if video_path:
                logger.info(f"\nTo replay the latest session:")
                logger.info(f"  Correlation ID: {latest.correlation_id}")
                logger.info(f"  Video file: {video_path}")
                logger.info(f"\nOpen with your video player:")
                logger.info(f"  vlc {video_path}")
                logger.info(f"  # or")
                logger.info(f"  mpv {video_path}")
            else:
                logger.info("\nVideo not yet generated. Please wait for rendering to complete.")

        logger.info("\n" + "="*70)
        logger.info("EXAMPLES COMPLETE")
        logger.info("="*70)

        logger.info("\nAll recordings saved to: auto_recordings/")
        logger.info("Session index: auto_recordings/session_index.json")

    finally:
        # Cleanup
        logger.info("\nCleaning up...")
        recorder.cleanup()
        logger.info("Done!")


if __name__ == "__main__":
    run_all_examples()
