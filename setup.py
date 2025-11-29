"""
Setup script for manim_visualizer plugin

This installs manim_visualizer as a Python package with all dependencies including Manim.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read requirements
requirements_file = Path(__file__).parent / "manim_visualizer" / "requirements.txt"
if requirements_file.exists():
    with open(requirements_file) as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]
else:
    requirements = [
        "manim>=0.18.0",
        "numpy>=1.24.0",
        "pillow>=10.0.0",
        "ffmpeg-python>=0.2.0",
        "pycairo>=1.23.0",
    ]

# Read README for long description
readme_file = Path(__file__).parent / "manim_visualizer" / "README.md"
long_description = ""
if readme_file.exists():
    with open(readme_file, encoding='utf-8') as f:
        long_description = f.read()

setup(
    name="manim-visualizer",
    version="1.0.0",
    author="Crawl4AI Team",
    description="Learning cycle visualization with Manim for PyCharm plugin",
    long_description=long_description,
    long_description_content_type="text/markdown",

    # Package discovery
    packages=find_packages(include=["manim_visualizer", "manim_visualizer.*"]),

    # Dependencies - Manim included!
    install_requires=requirements,

    # Optional dependencies
    extras_require={
        'dev': [
            'pytest>=7.0.0',
            'black>=23.0.0',
            'mypy>=1.0.0',
        ],
        'performance': [
            'numba>=0.57.0',
            'scipy>=1.11.0',
        ]
    },

    # Python version requirement
    python_requires='>=3.10',

    # Entry points
    entry_points={
        'console_scripts': [
            'manim-viz=manim_visualizer.cli:main',
        ],
    },

    # Package data
    package_data={
        'manim_visualizer': [
            'requirements.txt',
            '*.md',
        ],
    },

    # Classifiers
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Debuggers',
        'Topic :: Multimedia :: Video',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
    ],

    # Project URLs
    project_urls={
        'Source': 'https://github.com/your-org/crawl4ai',
        'Documentation': 'https://github.com/your-org/crawl4ai/tree/main/pycharm-plugin/manim_visualizer',
    },
)
