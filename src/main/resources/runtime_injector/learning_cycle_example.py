from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Learning Cycle Tracing Example

Demonstrates correlation ID lifecycle tied to learning cycles:
- Each cycle: Input → Forward → Loss → Backward → Update
- Separate video per cycle showing all parallel paths
- Synchronized to same input time
- Auto-completes when parameter update finishes
"""

import sys
from pathlib import Path
import time

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from manim_visualizer import LearningCycleTracer


def example_1_simple_training():
    """Example 1: Simple PyTorch training with cycle tracing."""
    logger.info("\n" + "="*70)
    logger.info("EXAMPLE 1: Simple PyTorch Training")
    logger.info("="*70 + "\n")

    import torch
    import torch.nn as nn

    # Create tracer
    tracer = LearningCycleTracer(
        output_dir="learning_cycles/simple_training",
        auto_generate_video=True,  # Set False for quick demo
        video_quality="medium",
        verbose=True
    )

    # Simple model
    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.fc1 = nn.Linear(10, 64)
            self.fc2 = nn.Linear(64, 1)

        def forward(self, x):
            x = torch.relu(self.fc1(x))
            return self.fc2(x)

    model = Net()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.MSELoss()

    # Training loop
    for epoch in range(3):
        logger.info(f"\n{'='*70}")
        logger.info(f"EPOCH {epoch+1}")
        logger.info(f"{'='*70}\n")

        # Each iteration is a separate learning cycle
        for batch_idx in range(2):
            # CYCLE STARTS HERE
            with tracer.cycle(input_data={
                "epoch": epoch,
                "batch": batch_idx,
                "timestamp": time.time()
            }):
                # 1. INPUT (auto-detected)
                x = torch.randn(32, 10)
                y = torch.randn(32, 1)

                # 2. FORWARD PASS (auto-detected from function name)
                output = model(x)

                # 3. LOSS COMPUTATION (auto-detected)
                loss = criterion(output, y)

                # 4. BACKWARD PASS (auto-detected)
                optimizer.zero_grad()
                loss.backward()

                # 5. PARAMETER UPDATE (auto-detected from optimizer.step)
                optimizer.step()

                logger.info(f"  Batch {batch_idx}: Loss = {loss.item():.4f}")

            # CYCLE ENDS HERE -> Video generated for this cycle
            # Shows: Input → Forward → Loss → Backward → Update
            # All parallel paths synchronized to input time

    # Print summary of all cycles
    tracer.print_summary()

    logger.info("\n" + "="*70)
    logger.info("EXAMPLE 1 COMPLETE")
    logger.info("="*70)
    logger.info(f"\nVideos saved to: learning_cycles/simple_training/")
    logger.info("Each cycle has its own video showing the complete learning path!\n")


def example_2_embodied_ai_learning():
    """Example 2: Embodied AI learning with cycle tracing."""
    logger.info("\n" + "="*70)
    logger.info("EXAMPLE 2: Embodied AI Learning")
    logger.info("="*70 + "\n")

    try:
        from crawl4ai.embodied_ai.learning.reality_grounded_learner import RealityGroundedLearner
        from crawl4ai.embodied_ai.memory.episodic_memory import EpisodicMemory
        import torch

        # Create tracer
        tracer = LearningCycleTracer(
            output_dir="learning_cycles/embodied_ai",
            auto_generate_video=True,
            video_quality="high",  # High quality for important runs
            verbose=True
        )

        # Initialize components
        learner = RealityGroundedLearner()
        memory = EpisodicMemory(capacity=100)

        # Learning loop
        for episode in range(5):
            logger.info(f"\n{'='*70}")
            logger.info(f"EPISODE {episode+1}")
            logger.info(f"{'='*70}\n")

            # Simulate observation
            observation = torch.randn(1, 128)
            target_action = torch.randn(1, 64)

            # LEARNING CYCLE: Observation → Action → Reward → Learn
            with tracer.cycle(input_data={
                "episode": episode,
                "observation_shape": list(observation.shape),
                "timestamp": time.time()
            }):
                # 1. FORWARD: Select action based on observation
                action = learner.select_action(observation)

                # 2. EXECUTE: Simulate action execution
                reward = 0.5 + (episode * 0.1)  # Increasing reward
                next_observation = torch.randn(1, 128)

                # 3. MEMORY: Store episode
                memory.add_episode(
                    observation={"tensor": observation},
                    action={"tensor": action},
                    reward=reward,
                    next_observation={"tensor": next_observation},
                    done=False,
                    metadata={"episode": episode}
                )

                # 4. LEARN: Update from experience
                if len(memory) >= 5:
                    batch = memory.sample(batch_size=5)
                    learner.learn_from_batch(batch)

                logger.info(f"  Reward: {reward:.3f}")

            # Cycle complete → Video shows entire flow

        # Print summary
        tracer.print_summary()

        logger.info("\n" + "="*70)
        logger.info("EXAMPLE 2 COMPLETE")
        logger.info("="*70)
        logger.info(f"\nVideos saved to: learning_cycles/embodied_ai/")
        logger.info("Each episode has its own video with correlation ID!\n")

    except ImportError as e:
        logger.info(f"Could not import embodied_ai modules: {e}")
        logger.info("Skipping Example 2\n")


def example_3_parallel_learning():
    """Example 3: Parallel learning paths in same cycle."""
    logger.info("\n" + "="*70)
    logger.info("EXAMPLE 3: Parallel Learning Paths")
    logger.info("="*70 + "\n")

    import torch
    import torch.nn as nn
    import threading

    # Create tracer
    tracer = LearningCycleTracer(
        output_dir="learning_cycles/parallel",
        auto_generate_video=True,
        video_quality="medium",
        verbose=True
    )

    # Multiple models learning in parallel
    class ModalityNet(nn.Module):
        def __init__(self, name):
            super().__init__()
            self.name = name
            self.fc = nn.Linear(10, 1)

        def forward(self, x):
            return self.fc(x)

    visual_model = ModalityNet("visual")
    audio_model = ModalityNet("audio")
    text_model = ModalityNet("text")

    visual_opt = torch.optim.SGD(visual_model.parameters(), lr=0.01)
    audio_opt = torch.optim.SGD(audio_model.parameters(), lr=0.01)
    text_opt = torch.optim.SGD(text_model.parameters(), lr=0.01)

    criterion = nn.MSELoss()

    # Training cycle with parallel modalities
    for cycle_idx in range(3):
        logger.info(f"\n{'='*70}")
        logger.info(f"CYCLE {cycle_idx+1}: Multi-Modal Parallel Learning")
        logger.info(f"{'='*70}\n")

        # CYCLE WITH PARALLEL PATHS
        with tracer.cycle(input_data={
            "cycle": cycle_idx,
            "modalities": ["visual", "audio", "text"],
            "timestamp": time.time()
        }):
            # Shared input
            x = torch.randn(32, 10)
            y = torch.randn(32, 1)

            # Process each modality (these could be parallel threads)
            def process_modality(model, optimizer, name):
                # Forward
                output = model(x)

                # Loss
                loss = criterion(output, y)

                # Backward
                optimizer.zero_grad()
                loss.backward()

                # Update
                optimizer.step()

                logger.info(f"    {name}: Loss = {loss.item():.4f}")

            # Sequential for demo (could be parallel with threading)
            process_modality(visual_model, visual_opt, "Visual")
            process_modality(audio_model, audio_opt, "Audio")
            process_modality(text_model, text_opt, "Text")

        # Video will show all 3 parallel paths synchronized to same input time

    tracer.print_summary()

    logger.info("\n" + "="*70)
    logger.info("EXAMPLE 3 COMPLETE")
    logger.info("="*70)
    logger.info(f"\nVideos saved to: learning_cycles/parallel/")
    logger.info("Videos show all 3 modalities learning in parallel!\n")


def example_4_manual_phase_control():
    """Example 4: Manual control of learning phases."""
    logger.info("\n" + "="*70)
    logger.info("EXAMPLE 4: Manual Phase Control")
    logger.info("="*70 + "\n")

    import torch

    # Create tracer
    tracer = LearningCycleTracer(
        output_dir="learning_cycles/manual_phases",
        auto_generate_video=True,
        video_quality="medium",
        verbose=True
    )

    # Manually control phases
    logger.info("Starting cycle with manual phase control...\n")

    correlation_id = tracer.start_cycle(input_data={"custom": "data"})

    try:
        # Phase 1: Data preprocessing
        tracer.set_phase("preprocessing")
        time.sleep(0.1)
        data = torch.randn(100, 10)
        logger.info("  Preprocessing complete")

        # Phase 2: Forward pass
        tracer.set_phase("forward")
        time.sleep(0.1)
        output = data * 2
        logger.info("  Forward pass complete")

        # Phase 3: Loss computation
        tracer.set_phase("loss")
        time.sleep(0.1)
        loss = torch.mean(output ** 2)
        logger.info(f"  Loss computed: {loss.item():.4f}")

        # Phase 4: Backward pass
        tracer.set_phase("backward")
        time.sleep(0.1)
        logger.info("  Backward pass complete")

        # Phase 5: Update
        tracer.set_phase("update")
        time.sleep(0.1)
        logger.info("  Parameters updated")

    finally:
        tracer.end_cycle(status="completed")

    tracer.print_summary()

    logger.info("\n" + "="*70)
    logger.info("EXAMPLE 4 COMPLETE")
    logger.info("="*70)
    logger.info(f"\nVideo saved to: learning_cycles/manual_phases/")
    logger.info("Video shows each custom phase with timing!\n")


def run_all_examples():
    """Run all examples."""
    logger.info("\n" + "="*70)
    logger.info("LEARNING CYCLE TRACER - COMPLETE EXAMPLES")
    logger.info("="*70)

    try:
        example_1_simple_training()
        input("\nPress Enter for Example 2...")

        example_2_embodied_ai_learning()
        input("\nPress Enter for Example 3...")

        example_3_parallel_learning()
        input("\nPress Enter for Example 4...")

        example_4_manual_phase_control()

        logger.info("\n" + "="*70)
        logger.info("ALL EXAMPLES COMPLETE")
        logger.info("="*70)
        logger.info("\nKey Features Demonstrated:")
        logger.info("1. ✓ Automatic correlation ID per learning cycle")
        logger.info("2. ✓ Separate video per cycle")
        logger.info("3. ✓ Phase detection (forward, loss, backward, update)")
        logger.info("4. ✓ Parallel path visualization")
        logger.info("5. ✓ Synchronized to input time")
        logger.info("6. ✓ Auto-completion on parameter update")
        logger.info("\nAll videos saved to: learning_cycles/")
        logger.info()

    except KeyboardInterrupt:
        logger.info("\n\nExamples interrupted by user")
    except Exception as e:
        logger.info(f"\n\nError running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Learning cycle tracing examples")
    parser.add_argument(
        "--example",
        type=int,
        choices=[1, 2, 3, 4],
        help="Run specific example (1-4)"
    )

    args = parser.parse_args()

    if args.example == 1:
        example_1_simple_training()
    elif args.example == 2:
        example_2_embodied_ai_learning()
    elif args.example == 3:
        example_3_parallel_learning()
    elif args.example == 4:
        example_4_manual_phase_control()
    else:
        run_all_examples()
