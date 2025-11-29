"""
DEPRECATED: This file has been superseded by ultimate_architecture_viz.py

The functionality from this file has been merged into ultimate_architecture_viz.py
which is the single active visualization engine used by ManimAutoRenderer.kt.

DO NOT USE - Kept for reference only.
================================================================================
"""

from logging_config import setup_logger
logger = setup_logger(__name__)

"""
Coherent Unified Visualization - 3Blue1Brown Style

ONE SINGLE VIDEO composing:
1. Architecture Overview - Rotating 3D modules with billboard text
2. Dependencies - Flowing arrows between modules
3. Recommendations - Floating text with smooth transitions
4. Data Flow - Complete call tree with parallel branches, all visible simultaneously
5. Smooth transitions - End position of phase N = start position of phase N+1

Camera work: Smooth movements, no occlusion, all vital info visible
Text: Always billboard-facing for legibility
Layout: Proper 3D spacing, no stacking at center
"""

import json
import numpy as np
from manim import *
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Set

# Import existing modules
try:
    from architecture_explainer import ArchitectureExtractor
    ARCH_AVAILABLE = True
except ImportError:
    ARCH_AVAILABLE = False

try:
    from comprehensive_micro_animations import ComprehensiveMicroAnimator
    MICRO_AVAILABLE = True
except ImportError:
    MICRO_AVAILABLE = False


class BillboardText(Text):
    """Text that always faces the camera."""
    def __init__(self, text_string, font_size=24, color=WHITE, **kwargs):
        super().__init__(text_string, font_size=font_size, color=color, **kwargs)

    def always_face_camera(self, camera):
        """Update orientation to face camera."""
        # This will be called each frame
        pass  # Manim handles this with add_fixed_in_frame_mobjects


class CoherentUnifiedScene(ThreeDScene):
    """
    One coherent video with smooth transitions between all phases.

    Flow:
    1. ARCHITECTURE OVERVIEW (0-10s)
       - Camera orbits around 3D layered modules
       - Billboard text shows module names
       - Smooth rotation, all text readable

    2. DEPENDENCIES (10-15s)
       - Camera stops orbiting
       - Curved arrows appear showing inter-module connections
       - Thickness = call frequency
       - Color = hot->cold (frequently->rarely called)

    3. RECOMMENDATIONS (15-20s)
       - Camera smoothly pans to side view
       - Recommendations float in as cards
       - Green checkmarks for implemented, yellow for suggested

    4. DATA FLOW - CALL TREE (20-40s)
       - Camera transitions to side view showing full depth
       - Data flows through call tree
       - Parallel branches visible simultaneously
       - Multiple camera angles composite view
       - Each function = 3D box with tensor shapes
       - Arrows show data flow between functions
       - Micro-animations show operations (matmul, reshape, etc.)

    Transitions:
    - Phase 1→2: Architecture shrinks to upper-left corner, stays visible
    - Phase 2→3: Dependencies fade to 30% opacity, stay visible
    - Phase 3→4: Zoom into first function, recommendations move to sidebar
    - Within Phase 4: Smooth camera following data, parallel branches always visible
    """

    def __init__(self, trace_file, **kwargs):
        super().__init__(**kwargs)
        self.trace_file = trace_file
        self.trace_data = None
        self.architecture = None
        self.module_objects = {}  # module_name -> (box, label, position)
        self.dependency_arrows = VGroup()
        self.recommendation_cards = VGroup()
        self.call_tree_objects = {}  # call_id -> visualization

        # Micro-animator
        if MICRO_AVAILABLE:
            self.micro_animator = ComprehensiveMicroAnimator(self)
        else:
            self.micro_animator = None

    def construct(self):
        """Main construction sequence."""
        # Load data
        self.load_and_analyze()

        # Setup camera
        self.camera.background_color = "#1e1e1e"

        # === PHASE 1: ARCHITECTURE OVERVIEW (0-10s) ===
        self.phase1_architecture_overview()

        # === PHASE 2: DEPENDENCIES (10-15s) ===
        self.phase2_show_dependencies()

        # === PHASE 3: RECOMMENDATIONS (15-20s) ===
        self.phase3_show_recommendations()

        # === PHASE 4: DATA FLOW THROUGH CALL TREE (20-40s) ===
        self.phase4_data_flow_call_tree()

        # Finale
        self.wait(2)

    def load_and_analyze(self):
        """Load trace and extract architecture."""
        with open(self.trace_file, 'r') as f:
            self.trace_data = json.load(f)

        if ARCH_AVAILABLE:
            extractor = ArchitectureExtractor(self.trace_data)
            self.architecture = extractor.extract()
        else:
            # Fallback: simple module grouping
            self.architecture = self._simple_architecture_extraction()

    def _simple_architecture_extraction(self):
        """Simple fallback architecture extraction."""
        calls = self.trace_data.get('calls', [])
        modules = defaultdict(lambda: {'functions': set(), 'calls_to': defaultdict(int)})

        for call in calls:
            module = call.get('module', 'unknown')
            func = call.get('function', '')
            modules[module]['functions'].add(func)

        # Create simple layers (1 layer for now)
        return {
            'modules': dict(modules),
            'layers': [list(modules.keys())],
            'anti_patterns': [],
            'components': {}
        }

    # ========================================================================
    # PHASE 1: ARCHITECTURE OVERVIEW
    # ========================================================================

    def phase1_architecture_overview(self):
        """
        Phase 1: Show 3D layered architecture with orbiting camera.
        Duration: 0-10s

        - Layers arranged vertically
        - Modules within layers arranged horizontally
        - Camera orbits around architecture
        - Text always faces camera (billboard)
        - Smooth appearance animations
        """
        # Title
        title = Text("System Architecture", font_size=48, color=GOLD)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(Write(title), run_time=1)

        # Set initial camera orientation
        self.set_camera_orientation(phi=70 * DEGREES, theta=-45 * DEGREES)

        # Get layers
        layers = self.architecture['layers']

        # Create architecture visualization
        all_modules = VGroup()
        layer_spacing = 2.5
        module_spacing = 1.8

        for layer_idx, layer_modules in enumerate(layers):
            y_pos = layer_idx * layer_spacing - len(layers) * layer_spacing / 2

            # Layer label (billboard)
            layer_label = Text(f"Layer {layer_idx}", font_size=20, color=YELLOW)
            layer_label.move_to(np.array([-6, y_pos, 0]))
            self.add_fixed_in_frame_mobjects(layer_label)
            self.play(FadeIn(layer_label), run_time=0.3)

            for mod_idx, module in enumerate(layer_modules[:8]):  # Max 8 modules per layer
                x_pos = (mod_idx - len(layer_modules) / 2) * module_spacing
                position = np.array([x_pos, y_pos, 0])

                # Create module box
                module_data = self.architecture['modules'][module]
                num_functions = len(module_data['functions'])

                # Size based on complexity
                box_scale = 0.4 + min(num_functions / 15, 0.6)
                box = Cube(side_length=box_scale)

                # Color by layer
                layer_colors = [GREEN, BLUE, PURPLE, ORANGE, RED, TEAL]
                box.set_color(layer_colors[layer_idx % len(layer_colors)])
                box.set_opacity(0.7)
                box.set_sheen(0.5, direction=UP)
                box.move_to(position)

                # Module name (billboard)
                module_name = module.split('.')[-1][:15]
                label = Text(module_name, font_size=12, color=WHITE)
                label.move_to(position + DOWN * (box_scale + 0.3))
                self.add_fixed_in_frame_mobjects(label)

                # Function count
                func_count = Text(f"{num_functions} funcs", font_size=10, color=GRAY)
                func_count.move_to(position + UP * (box_scale + 0.2))
                self.add_fixed_in_frame_mobjects(func_count)

                # Store reference
                self.module_objects[module] = (box, label, position)

                # Animate appearance
                all_modules.add(box)
                self.play(
                    GrowFromCenter(box),
                    FadeIn(label),
                    FadeIn(func_count),
                    run_time=0.4
                )

        # Begin camera orbit
        self.begin_ambient_camera_rotation(rate=0.15)
        self.wait(5)

        # Stop orbit, prepare for phase 2
        self.stop_ambient_camera_rotation()
        self.play(FadeOut(title), run_time=0.5)

        # TRANSITION TO PHASE 2:
        # Shrink architecture to upper region, keep visible
        self.play(
            all_modules.animate.scale(0.6).shift(UP * 2),
            run_time=1.5
        )

    # ========================================================================
    # PHASE 2: DEPENDENCIES
    # ========================================================================

    def phase2_show_dependencies(self):
        """
        Phase 2: Show inter-module dependencies as flowing arrows.
        Duration: 10-15s

        - Curved arrows from module A → module B
        - Thickness proportional to call frequency
        - Color gradient: hot (frequent) → cold (rare)
        - Smooth appearance with lag_ratio
        """
        # Title
        title = Text("Inter-Module Dependencies", font_size=36, color=BLUE)
        title.to_edge(UP).shift(DOWN * 0.5)
        self.add_fixed_in_frame_mobjects(title)
        self.play(FadeIn(title), run_time=0.5)

        # Extract dependencies
        all_deps = []
        for module, data in self.architecture['modules'].items():
            for target, count in data['calls_to'].items():
                if module in self.module_objects and target in self.module_objects:
                    all_deps.append((module, target, count))

        # Sort by frequency and take top 20
        all_deps.sort(key=lambda x: x[2], reverse=True)
        top_deps = all_deps[:20]

        # Create arrows
        for source, target, count in top_deps:
            source_box, _, source_pos = self.module_objects[source]
            target_box, _, target_pos = self.module_objects[target]

            # Adjust positions for shrunk architecture
            source_pos_adjusted = source_pos * 0.6 + UP * 2
            target_pos_adjusted = target_pos * 0.6 + UP * 2

            # Thickness based on frequency
            thickness = min(count / 5, 8)

            # Color based on frequency (hot=frequent, cold=rare)
            color = interpolate_color(RED, BLUE, 1 - min(count / 100, 1))

            # Curved arrow
            arrow = CubicBezier(
                source_pos_adjusted,
                source_pos_adjusted + (target_pos_adjusted - source_pos_adjusted) * 0.3 + UP * 0.5,
                target_pos_adjusted + (source_pos_adjusted - target_pos_adjusted) * 0.3 + UP * 0.5,
                target_pos_adjusted,
                color=color,
                stroke_width=thickness
            )
            arrow.set_opacity(0.7)
            self.dependency_arrows.add(arrow)

        # Animate arrows appearing with lag
        self.play(
            *[Create(arrow) for arrow in self.dependency_arrows],
            run_time=3,
            lag_ratio=0.1
        )

        self.wait(2)
        self.play(FadeOut(title), run_time=0.5)

        # TRANSITION TO PHASE 3:
        # Fade dependencies to background (30% opacity), keep visible
        self.play(
            self.dependency_arrows.animate.set_opacity(0.3),
            run_time=1
        )

    # ========================================================================
    # PHASE 3: RECOMMENDATIONS
    # ========================================================================

    def phase3_show_recommendations(self):
        """
        Phase 3: Show architectural recommendations.
        Duration: 15-20s

        - Floating recommendation cards
        - Green checkmarks for implemented patterns
        - Yellow warnings for suggested improvements
        - Smooth entrance from right side
        """
        # Title
        title = Text("Architectural Recommendations", font_size=36, color=GREEN)
        title.to_edge(UP).shift(DOWN * 0.5)
        self.add_fixed_in_frame_mobjects(title)
        self.play(FadeIn(title), run_time=0.5)

        # Pan camera slightly to right
        self.play(
            self.camera.frame.animate.shift(RIGHT * 2),
            run_time=1.5
        )

        # Create recommendation cards
        recommendations = [
            ("Reduce inter-module coupling", "HIGH", GREEN),
            ("Group related modules into components", "MEDIUM", YELLOW),
            ("Add clear layer boundaries", "MEDIUM", YELLOW),
            ("Consider dependency injection", "LOW", BLUE)
        ]

        y_pos = 2
        for rec_text, priority, color in recommendations:
            # Card background
            card = Rectangle(width=5, height=0.8, fill_opacity=0.2, fill_color=color, stroke_color=color)
            card.move_to(np.array([5, y_pos, 0]))

            # Checkmark/bullet
            icon = Text("✓" if color == GREEN else "•", font_size=24, color=color)
            icon.move_to(card.get_left() + RIGHT * 0.3)

            # Recommendation text
            rec_label = Text(rec_text[:40], font_size=14, color=WHITE)
            rec_label.move_to(card.get_center() + RIGHT * 0.5)

            # Priority badge
            priority_badge = Text(priority, font_size=10, color=color)
            priority_badge.move_to(card.get_right() + LEFT * 0.5)

            card_group = VGroup(card, icon, rec_label, priority_badge)
            self.add_fixed_in_frame_mobjects(card_group)
            self.recommendation_cards.add(card_group)

            # Animate entrance from right
            card_group.shift(RIGHT * 3)
            self.play(
                card_group.animate.shift(LEFT * 3),
                run_time=0.5
            )

            y_pos -= 1

        self.wait(2)
        self.play(FadeOut(title), run_time=0.5)

        # TRANSITION TO PHASE 4:
        # Move recommendations to left sidebar, shrink
        self.play(
            self.recommendation_cards.animate.scale(0.5).to_edge(LEFT).shift(DOWN),
            self.camera.frame.animate.shift(LEFT * 2),  # Return camera to center
            run_time=1.5
        )

    # ========================================================================
    # PHASE 4: DATA FLOW THROUGH CALL TREE
    # ========================================================================

    def phase4_data_flow_call_tree(self):
        """
        Phase 4: Data flows through complete call tree with parallel branches.
        Duration: 20-40s

        - Build call tree structure (tree = multiple branches)
        - Show ALL branches simultaneously (no stacking)
        - Each function = 3D box with tensor shape labels
        - Arrows show data flow
        - Camera follows data smoothly
        - Micro-animations show operations
        - Parallel branches spread in 3D space (X, Y, Z)
        """
        # Title
        title = Text("Data Flow Through Execution", font_size=36, color=BLUE)
        title.to_edge(UP)
        self.add_fixed_in_frame_mobjects(title)
        self.play(FadeIn(title), run_time=0.5)

        # Extract call tree
        calls = self.trace_data.get('calls', [])

        # Build tree structure
        call_tree = self._build_call_tree(calls)

        # Layout tree in 3D space (breadth-first with proper spacing)
        positions = self._layout_call_tree_3d(call_tree)

        # Visualize tree
        self._visualize_call_tree(call_tree, positions)

        # Animate data flowing through tree
        self._animate_data_flow_through_tree(call_tree, positions)

        self.wait(2)
        self.play(FadeOut(title), run_time=0.5)

    def _build_call_tree(self, calls):
        """
        Build call tree structure.
        Returns: Dict[call_id] -> {parent_id, children: List[call_id], data: call_dict}
        """
        tree = {}

        # First pass: create nodes
        for call in calls:
            if call.get('type') == 'call':
                call_id = call.get('call_id')
                tree[call_id] = {
                    'parent_id': call.get('parent_id'),
                    'children': [],
                    'data': call
                }

        # Second pass: link children
        for call_id, node in tree.items():
            parent_id = node['parent_id']
            if parent_id and parent_id in tree:
                tree[parent_id]['children'].append(call_id)

        return tree

    def _layout_call_tree_3d(self, tree):
        """
        Layout call tree in 3D space using modified Reingold-Tilford algorithm.
        Parallel branches spread in X (horizontal) and Z (depth).
        Depth spreads in Y (vertical).

        Returns: Dict[call_id] -> np.array([x, y, z])
        """
        positions = {}

        # Find root nodes (no parent)
        roots = [call_id for call_id, node in tree.items() if not node['parent_id'] or node['parent_id'] not in tree]

        # Breadth-first layout
        queue = [(root, 0, 0, 0) for root in roots]  # (call_id, depth, branch_index, parent_x)
        branch_counter = defaultdict(int)

        while queue:
            call_id, depth, branch_idx, parent_x = queue.pop(0)

            if call_id not in tree:
                continue

            # Position calculation
            y = -depth * 1.5  # Vertical depth
            x = parent_x + (branch_idx - tree[call_id]['children'] / 2) * 2.0  # Horizontal spread
            z = -depth * 1.0  # Z depth for 3D effect

            positions[call_id] = np.array([x, y, z])

            # Queue children
            children = tree[call_id]['children']
            for child_idx, child_id in enumerate(children):
                queue.append((child_id, depth + 1, child_idx, x))

        return positions

    def _visualize_call_tree(self, tree, positions):
        """
        Create 3D visualization of call tree.
        Each node = 3D box with function name and tensor shapes.
        """
        for call_id, position in positions.items():
            if call_id not in tree:
                continue

            node = tree[call_id]
            call_data = node['data']

            # Create function box
            func_name = call_data.get('function', 'func')[:20]

            box = Cube(side_length=0.5)
            box.set_color(BLUE)
            box.set_opacity(0.7)
            box.set_sheen(0.5, direction=UP)
            box.move_to(position)

            # Function label (billboard)
            label = Text(func_name, font_size=12, color=WHITE)
            label.move_to(position + DOWN * 0.4)
            self.add_fixed_in_frame_mobjects(label)

            # Store reference
            self.call_tree_objects[call_id] = (box, label, position)

            # Animate appearance
            self.play(FadeIn(box), FadeIn(label), run_time=0.2)

            # Draw arrow from parent
            if node['parent_id'] and node['parent_id'] in self.call_tree_objects:
                parent_box, _, parent_pos = self.call_tree_objects[node['parent_id']]

                arrow = Arrow3D(
                    start=parent_pos + DOWN * 0.3,
                    end=position + UP * 0.3,
                    color=GRAY,
                    thickness=0.02
                )
                self.play(Create(arrow), run_time=0.2)

    def _animate_data_flow_through_tree(self, tree, positions):
        """
        Animate data flowing through tree with smooth camera tracking.
        """
        # Find root nodes
        roots = [call_id for call_id, node in tree.items() if not node['parent_id'] or node['parent_id'] not in tree]

        for root in roots:
            self._animate_branch_flow(root, tree, positions)

    def _animate_branch_flow(self, call_id, tree, positions):
        """Recursively animate data flow through branch."""
        if call_id not in tree or call_id not in self.call_tree_objects:
            return

        box, label, position = self.call_tree_objects[call_id]

        # Focus camera on this node
        self.play(
            self.camera.frame.animate.move_to(position),
            run_time=0.5
        )

        # Highlight box
        self.play(
            box.animate.set_opacity(1).scale(1.2),
            run_time=0.3
        )

        # Micro-animation (if available)
        if self.micro_animator:
            try:
                call_data = tree[call_id]['data']
                metadata = {
                    'operation': call_data.get('function', ''),
                    'function': call_data.get('function', ''),
                    'type': 'method_call'
                }
                self.micro_animator.animate_operation(position, metadata)
            except:
                pass

        # Return to normal
        self.play(
            box.animate.set_opacity(0.7).scale(1/1.2),
            run_time=0.2
        )

        # Recurse to children
        node = tree[call_id]
        for child_id in node['children']:
            self._animate_branch_flow(child_id, tree, positions)


# Main entry point
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        logger.info("Usage: python coherent_unified_viz.py <trace_json_file>")
        sys.exit(1)

    trace_file = sys.argv[1]

    from manim import config
    config.quality = 'medium_quality'
    config.output_file = 'coherent_unified'

    scene = CoherentUnifiedScene(trace_file)
    scene.render()

    logger.info(f"Coherent unified visualization saved")
