"""
Test Manim output path configuration
"""
import sys
from pathlib import Path

# Add visualizer to path
sys.path.insert(0, str(Path(__file__).parent / 'pycharm-plugin' / 'manim_visualizer'))

from manim import config

# Test configuration
project_root = Path(__file__).parent
plugin_root = project_root / '.pycharm_plugin'
plugin_root.mkdir(parents=True, exist_ok=True)

print("Testing Manim Path Configuration")
print("=" * 60)

# Configuration 1: Default
print("\n1. DEFAULT MANIM CONFIG:")
print(f"   media_dir: {config.media_dir}")
print(f"   video_dir template: videos/{{module_name}}/{{quality}}")
print(f"   Full path: {{media_dir}}/videos/{{module_name}}/{{quality}}/{{output_file}}.mp4")

# Configuration 2: Our setup
config.media_dir = str(plugin_root)
config.quality = 'medium_quality'
config.output_file = 'video_test_123'
config['video_dir'] = '{media_dir}/manim/videos/{quality}'

print("\n2. OUR PLUGIN CONFIG:")
print(f"   media_dir: {config.media_dir}")
print(f"   video_dir: {config['video_dir']}")
print(f"   quality: {config.quality}")
print(f"   output_file: {config.output_file}")

# Expand the template
video_dir_expanded = config['video_dir'].format(
    media_dir=config.media_dir,
    quality=config.quality
)
print(f"   Expanded video_dir: {video_dir_expanded}")
print(f"   Full expected path: {video_dir_expanded}/{config.output_file}.mp4")

# Expected vs current
print("\n3. PATH COMPARISON:")
print(f"   Expected: .pycharm_plugin/manim/videos/medium_quality/video_test_123.mp4")
print(f"   Actual:   {Path(video_dir_expanded).relative_to(project_root)}/{config.output_file}.mp4")

# Check if they match
expected_path = plugin_root / 'manim' / 'videos' / 'medium_quality' / f'{config.output_file}.mp4'
actual_path = Path(video_dir_expanded) / f'{config.output_file}.mp4'

if str(expected_path) == str(actual_path):
    print("\n   ✓ PATHS MATCH! Configuration is correct.")
else:
    print("\n   ✗ PATHS DON'T MATCH!")
    print(f"   Expected: {expected_path}")
    print(f"   Actual:   {actual_path}")

print("\n" + "=" * 60)
