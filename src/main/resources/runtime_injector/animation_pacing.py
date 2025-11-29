"""
Animation Pacing - 3Blue1Brown Standards

Implements the timing principles from 3Blue1Brown videos:
- Concept over speed: 3-5 seconds per concept (not 0.6s per call!)
- Breathing room: Pauses between concepts
- Smooth transitions: Slower camera movements
- Progressive disclosure: Show → Explain → Move on

Based on Animator Agent design spec (ANIMATION_DESIGN_SPEC.md)
"""

from dataclasses import dataclass


@dataclass
class AnimationPacing:
    """
    3Blue1Brown-style animation pacing.

    Key principle: TIME PER CONCEPT, not time per animation.
    A concept might require multiple animations (e.g., create box + add label + show data flow).

    Formula: Total time ≈ 3-5s per important concept
    """

    # ========================================================================
    # CORE PRINCIPLES
    # ========================================================================

    # Concept timing (the most important!)
    CONCEPT_INTRODUCTION: float = 3.0      # Time to introduce new concept
    CONCEPT_EXPLANATION: float = 4.0        # Time to explain concept details
    CONCEPT_TRANSITION: float = 2.0         # Time between concepts
    CONCEPT_BREATHING: float = 0.5          # Pause after showing concept

    # ========================================================================
    # ANIMATION CATEGORIES (3Blue1Brown)
    # ========================================================================

    # Fast (0.3-0.5s) - Quick highlights, attention draws
    FAST_HIGHLIGHT: float = 0.3             # Flash/pulse to draw attention
    FAST_FADE: float = 0.4                  # Quick fade in/out for secondary elements
    FAST_PULSE: float = 0.5                 # Pulse animation for emphasis

    # Medium (0.8-1.2s) - Standard animations
    MEDIUM_TRANSITION: float = 0.8          # Standard fade/grow/shrink
    MEDIUM_DATA_FLOW: float = 1.0           # Data flowing between components
    MEDIUM_TRANSFORM: float = 1.2           # Shape transformations

    # Slow (2-3s) - Important concepts, camera movements
    SLOW_CONCEPT: float = 2.0               # Introducing important concept
    SLOW_CAMERA: float = 2.5                # Camera movements (smooth, deliberate)
    SLOW_EXPLANATION: float = 3.0           # Complex explanations

    # ========================================================================
    # SPECIFIC ANIMATION TYPES
    # ========================================================================

    # Titles and text
    TITLE_WRITE: float = 1.5                # Main title write animation
    TITLE_FADE_OUT: float = 0.5             # Title fade out (fast)
    PHASE_HEADER_IN: float = 0.8            # Phase header appears
    PHASE_HEADER_OUT: float = 0.5           # Phase header disappears
    LABEL_APPEAR: float = 0.4               # Labels appear (quick)

    # Module visualization
    MODULE_CREATE: float = 0.6              # Creating single module box
    MODULE_LABEL: float = 0.4               # Adding module label
    MODULE_HIGHLIGHT: float = 0.5           # Highlighting active module
    MODULE_CONNECTION: float = 1.0          # Showing connection between modules

    # Data flow
    DATA_FLOW_SHORT: float = 0.8            # Short distance (adjacent modules)
    DATA_FLOW_LONG: float = 1.2             # Long distance (across architecture)
    DATA_TRANSFORM: float = 1.5             # Data transformation visualization

    # Camera movements
    CAMERA_SETUP: float = 0.0               # Initial camera setup (instant)
    CAMERA_ORBIT: float = 2.5               # Smooth orbit around scene
    CAMERA_FOCUS: float = 2.0               # Focus on specific element
    CAMERA_ZOOM: float = 1.8                # Zoom in/out

    # Pauses (breathing room)
    PAUSE_SHORT: float = 0.3                # Brief pause
    PAUSE_MEDIUM: float = 0.8               # Standard pause
    PAUSE_LONG: float = 1.5                 # Long pause between sections

    # Error visualization
    ERROR_APPEAR: float = 0.8               # Error message appears
    ERROR_DWELL: float = 2.0                # Time to read error
    ERROR_DISAPPEAR: float = 0.5            # Error message disappears

    # Summary and statistics
    SUMMARY_APPEAR: float = 0.8             # Summary appears
    SUMMARY_DWELL: float = 2.5              # Time to read summary
    STAT_INCREMENT: float = 0.1             # Per-stat animation (if animated)

    # ========================================================================
    # COMPOUND TIMINGS (common patterns)
    # ========================================================================

    def module_full_creation(self, num_elements: int = 3) -> float:
        """
        Time to fully create and label a module.

        Args:
            num_elements: Number of elements (box, label, count, etc.)

        Returns:
            Total time in seconds
        """
        # Create box + label + pause
        return self.MODULE_CREATE + (num_elements * 0.3) + self.PAUSE_SHORT

    def concept_full_cycle(self) -> float:
        """
        Time for complete concept cycle: introduce → explain → pause.

        Returns:
            Total time in seconds
        """
        return (
            self.CONCEPT_INTRODUCTION +
            self.CONCEPT_EXPLANATION +
            self.CONCEPT_BREATHING
        )

    def phase_transition(self) -> float:
        """
        Time for phase transition: fade out old → pause → fade in new.

        Returns:
            Total time in seconds
        """
        return (
            self.PHASE_HEADER_OUT +
            self.PAUSE_SHORT +
            self.PHASE_HEADER_IN
        )

    # ========================================================================
    # TIMING VALIDATORS
    # ========================================================================

    def validate_concept_time(self, total_time: float, num_concepts: int) -> bool:
        """
        Check if timing meets 3Blue1Brown standard (3-5s per concept).

        Args:
            total_time: Total video duration
            num_concepts: Number of important concepts shown

        Returns:
            True if timing is appropriate, False if too fast
        """
        time_per_concept = total_time / max(num_concepts, 1)
        return 3.0 <= time_per_concept <= 5.0

    def calculate_target_duration(self, num_concepts: int) -> tuple[float, float]:
        """
        Calculate target duration range for video.

        Args:
            num_concepts: Number of important concepts

        Returns:
            (min_duration, max_duration) in seconds
        """
        min_duration = num_concepts * 3.0
        max_duration = num_concepts * 5.0
        return (min_duration, max_duration)

    # ========================================================================
    # PACING CALCULATOR
    # ========================================================================

    def calculate_scene_duration(
        self,
        num_modules: int,
        num_data_flows: int,
        num_camera_moves: int,
        has_errors: bool = False
    ) -> float:
        """
        Calculate total scene duration based on content.

        Args:
            num_modules: Number of modules to show
            num_data_flows: Number of data flow animations
            num_camera_moves: Number of camera movements
            has_errors: Whether scene includes error visualization

        Returns:
            Total duration in seconds
        """
        duration = 0.0

        # Title
        duration += self.TITLE_WRITE + self.PAUSE_SHORT + self.TITLE_FADE_OUT

        # Modules
        duration += num_modules * self.module_full_creation()

        # Data flows
        duration += num_data_flows * self.DATA_FLOW_LONG

        # Camera movements
        duration += num_camera_moves * self.CAMERA_ORBIT

        # Errors (if any)
        if has_errors:
            duration += self.ERROR_APPEAR + self.ERROR_DWELL + self.ERROR_DISAPPEAR

        # Summary
        duration += self.SUMMARY_APPEAR + self.SUMMARY_DWELL

        # Final pause
        duration += self.PAUSE_LONG

        return duration


# ============================================================================
# PRESETS
# ============================================================================

class PacingPresets:
    """Pre-configured pacing for common scenarios."""

    @staticmethod
    def tutorial_mode() -> AnimationPacing:
        """Slow, educational pacing (5-7s per concept)."""
        pacing = AnimationPacing()
        # Increase all timings by 50%
        for attr in dir(pacing):
            if not attr.startswith('_') and isinstance(getattr(pacing, attr), float):
                setattr(pacing, attr, getattr(pacing, attr) * 1.5)
        return pacing

    @staticmethod
    def presentation_mode() -> AnimationPacing:
        """Standard 3Blue1Brown pacing (3-5s per concept)."""
        return AnimationPacing()

    @staticmethod
    def demo_mode() -> AnimationPacing:
        """Faster pacing for demos (2-3s per concept)."""
        pacing = AnimationPacing()
        # Decrease all timings by 30%
        for attr in dir(pacing):
            if not attr.startswith('_') and isinstance(getattr(pacing, attr), float):
                setattr(pacing, attr, getattr(pacing, attr) * 0.7)
        return pacing


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == "__main__":
    pacing = AnimationPacing()

    print("=== 3Blue1Brown Animation Pacing ===\n")

    print("Core Principles:")
    print(f"  Concept Introduction: {pacing.CONCEPT_INTRODUCTION}s")
    print(f"  Concept Explanation:  {pacing.CONCEPT_EXPLANATION}s")
    print(f"  Concept Transition:   {pacing.CONCEPT_TRANSITION}s")
    print()

    print("Fast Animations (0.3-0.5s):")
    print(f"  Highlight:  {pacing.FAST_HIGHLIGHT}s")
    print(f"  Fade:       {pacing.FAST_FADE}s")
    print(f"  Pulse:      {pacing.FAST_PULSE}s")
    print()

    print("Medium Animations (0.8-1.2s):")
    print(f"  Transition: {pacing.MEDIUM_TRANSITION}s")
    print(f"  Data Flow:  {pacing.MEDIUM_DATA_FLOW}s")
    print(f"  Transform:  {pacing.MEDIUM_TRANSFORM}s")
    print()

    print("Slow Animations (2-3s):")
    print(f"  Concept:     {pacing.SLOW_CONCEPT}s")
    print(f"  Camera Move: {pacing.SLOW_CAMERA}s")
    print(f"  Explanation: {pacing.SLOW_EXPLANATION}s")
    print()

    print("Example Scene Calculation:")
    duration = pacing.calculate_scene_duration(
        num_modules=5,
        num_data_flows=3,
        num_camera_moves=2,
        has_errors=False
    )
    print(f"  5 modules + 3 data flows + 2 camera moves = {duration:.1f}s")
    print()

    print("Concept Validation:")
    num_concepts = 5
    min_dur, max_dur = pacing.calculate_target_duration(num_concepts)
    print(f"  {num_concepts} concepts should take {min_dur:.0f}-{max_dur:.0f}s")
    print(f"  Is {duration:.1f}s appropriate? {pacing.validate_concept_time(duration, num_concepts)}")
