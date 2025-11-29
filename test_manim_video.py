"""
Test Manim video generation manually with an existing trace file.
"""
import sys
from pathlib import Path

# Add manim_visualizer to path
project_root = Path(__file__).parent
visualizer_path = project_root / "pycharm-plugin" / "manim_visualizer"
sys.path.insert(0, str(visualizer_path))

# Find a trace file
trace_dir = project_root / ".pycharm_plugin" / "manim" / "traces"
trace_files = list(trace_dir.glob("trace_cycle_*.json"))

if not trace_files:
    print("ERROR: No trace files found in", trace_dir)
    sys.exit(1)

trace_file = str(trace_files[-1])  # Use most recent
print(f"Testing with trace file: {trace_file}")

# Configure Manim output
from manim import config
plugin_media = project_root / ".pycharm_plugin" / "manim" / "media"
plugin_media.mkdir(parents=True, exist_ok=True)

config.media_dir = str(plugin_media)
config.quality = 'medium_quality'
config.output_file = 'test_video'
config['video_dir'] = '{media_dir}/videos/{quality}'
config['images_dir'] = '{media_dir}/images/{quality}'
config['text_dir'] = '{media_dir}/texts'

print(f"Manim media configured to: {config.media_dir}/")

# Try importing and rendering
try:
    print("\n1. Trying SystemArchitecture3DScene...")
    from system_architecture_3d import SystemArchitecture3DScene

    scene = SystemArchitecture3DScene(trace_file=trace_file)
    scene.render()

    print('\nVideo saved to:', scene.renderer.file_writer.movie_file_path)
    print("SUCCESS!")

except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()

    # Try fallback
    print("\n2. Trying fallback CoherentUnifiedScene...")
    try:
        from coherent_unified_viz import CoherentUnifiedScene

        scene = CoherentUnifiedScene(trace_file=trace_file)
        scene.render()

        print('\nVideo saved to:', scene.renderer.file_writer.movie_file_path)
        print("SUCCESS with fallback!")

    except Exception as e2:
        print(f"\nFallback also failed: {e2}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
