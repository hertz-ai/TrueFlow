"""
Test example demonstrating Manim trace visualization.

This script shows how to use the Manim visualizer with embodied_ai code.
"""

import sys
from pathlib import Path

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from manim_visualizer.integration import (
    ManimTracingContext,
    trace_with_manim,
    tracer,
    quick_visualize
)


# Example 1: Using context manager
def example_context_manager():
    """Example using context manager for tracing."""
    print("\n=== Example 1: Context Manager ===\n")

    with ManimTracingContext(
        output_file="example_context.json",
        realtime=False,  # Set to True for real-time visualization
        quality="medium",
        auto_visualize=True
    ):
        # Simulate some embodied_ai operations
        print("Running embodied AI operations...")

        # Example calls that would be traced
        from crawl4ai.embodied_ai.memory.episodic_memory import EpisodicMemory

        memory = EpisodicMemory(capacity=100)

        # Add some episodes
        for i in range(5):
            memory.add_episode(
                observation={"data": f"observation_{i}"},
                action={"type": f"action_{i}"},
                reward=0.5 + i * 0.1,
                next_observation={"data": f"observation_{i+1}"},
                done=False,
                metadata={"episode": i}
            )

        # Retrieve similar episodes
        query = {"data": "observation_2"}
        similar = memory.retrieve_similar(query, k=3)

        print(f"Retrieved {len(similar)} similar episodes")

    print("\nTrace complete! Animation should be generated.")


# Example 2: Using decorator
@trace_with_manim(
    output_file="example_decorator.json",
    realtime=False,
    quality="medium",
    auto_visualize=True
)
def example_decorator():
    """Example using decorator for tracing."""
    print("\n=== Example 2: Decorator ===\n")

    from crawl4ai.embodied_ai.learning.temporal_coherence import TemporalCoherence

    # Create temporal coherence tracker
    temporal = TemporalCoherence(window_size=10, device="cpu")

    print("Running temporal coherence operations...")

    # Simulate some predictions
    import torch

    for i in range(5):
        pred = torch.randn(1, 128)  # Fake prediction
        temporal.track_prediction(
            prediction=pred,
            timestamp=i * 0.1,
            metadata={"step": i}
        )

    # Check coherence
    is_coherent = temporal.check_coherence(threshold=0.8)
    print(f"Predictions coherent: {is_coherent}")

    print("\nTrace complete! Animation should be generated.")


# Example 3: Using global tracer
def example_global_tracer():
    """Example using global tracer."""
    print("\n=== Example 3: Global Tracer ===\n")

    # Start tracing
    tracer.start(
        output_file="example_global.json",
        realtime=False,
        quality="medium",
        auto_visualize=True
    )

    try:
        from crawl4ai.embodied_ai.learning.kernel_continual_learning import KernelContinualLearning

        print("Running kernel continual learning operations...")

        # Create learner
        kernel_learner = KernelContinualLearning(
            kernel_type="rbf",
            bandwidth=1.0,
            device="cpu"
        )

        # Simulate learning from data
        import torch
        for i in range(3):
            data = torch.randn(10, 64)  # Batch of data
            labels = torch.randint(0, 10, (10,))

            kernel_learner.add_kernel_points(data, labels)
            print(f"Added batch {i+1}")

        print("Learning complete!")

    finally:
        # Stop tracing
        tracer.stop()

    print("\nTrace complete! Animation should be generated.")


# Example 4: Quick visualization of existing trace
def example_quick_visualize():
    """Example of quick visualization."""
    print("\n=== Example 4: Quick Visualization ===\n")

    # First generate a trace (without auto-visualize)
    with ManimTracingContext(
        output_file="example_quick.json",
        realtime=False,
        auto_visualize=False
    ):
        from crawl4ai.embodied_ai.models.unified_sensory_stream import UnifiedSensoryStream

        print("Generating trace data...")

        stream = UnifiedSensoryStream(
            input_dim=512,
            hidden_dim=256,
            output_dim=128
        )

        import torch
        input_data = torch.randn(1, 512)
        output = stream.forward(input_data)

        print(f"Output shape: {output.shape}")

    # Now visualize it
    print("\nVisualizing trace file...")
    video_path = quick_visualize(
        "example_quick.json",
        quality="medium"
    )
    print(f"\nAnimation saved to: {video_path}")


def run_all_examples():
    """Run all examples."""
    print("\n" + "="*60)
    print("Manim Trace Visualization Examples")
    print("="*60)

    # Note: These examples won't actually render Manim animations
    # unless Manim is installed. They will demonstrate the tracing
    # and integration functionality.

    try:
        # Run examples one by one
        example_context_manager()
        input("\nPress Enter to continue to next example...")

        example_decorator()
        input("\nPress Enter to continue to next example...")

        example_global_tracer()
        input("\nPress Enter to continue to next example...")

        example_quick_visualize()

        print("\n" + "="*60)
        print("All examples completed!")
        print("="*60)

    except Exception as e:
        print(f"\nError running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Manim trace visualization examples")
    parser.add_argument(
        "--example",
        type=int,
        choices=[1, 2, 3, 4],
        help="Run specific example (1-4), or run all if not specified"
    )

    args = parser.parse_args()

    if args.example == 1:
        example_context_manager()
    elif args.example == 2:
        example_decorator()
    elif args.example == 3:
        example_global_tracer()
    elif args.example == 4:
        example_quick_visualize()
    else:
        run_all_examples()
