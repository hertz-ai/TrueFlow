"""
Local LLM Server for TrueFlow - Qwen3-VL-2B via llama.cpp

This module provides:
1. Automatic model downloading from HuggingFace
2. llama.cpp server management (start/stop)
3. OpenAI-compatible API endpoint
4. CPU-optimized inference for code explanation

Model: unsloth/Qwen3-VL-2B-Instruct-GGUF (Q4_K_XL quantization)
Size: ~1.5GB (fits in 4GB RAM)
Speed: ~10-20 tokens/sec on CPU
"""

import os
import sys
import json
import time
import shutil
import signal
import platform
import subprocess
import threading
from pathlib import Path
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass
import urllib.request
import urllib.error

# Setup logging
try:
    from logging_config import setup_logger
    logger = setup_logger(__name__)
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Configuration for a GGUF model."""
    repo_id: str
    model_file: str
    mmproj_file: Optional[str]  # For vision models
    size_mb: int
    description: str


# Available models - from https://docs.unsloth.ai/models/qwen3-vl-how-to-run-and-fine-tune
MODELS = {
    # Qwen3-VL Vision-Language Models (recommended for code understanding)
    "qwen3-vl-2b": ModelConfig(
        repo_id="unsloth/Qwen3-VL-2B-Instruct-GGUF",
        model_file="Qwen3-VL-2B-Instruct-UD-Q4_K_XL.gguf",
        mmproj_file="mmproj-F16.gguf",  # Vision projector
        size_mb=1500,
        description="Qwen3-VL 2B - Vision+text, best for code analysis with diagrams"
    ),
    "qwen3-vl-2b-thinking": ModelConfig(
        repo_id="unsloth/Qwen3-VL-2B-Thinking-GGUF",
        model_file="Qwen3-VL-2B-Thinking-UD-Q4_K_XL.gguf",
        mmproj_file="mmproj-F16.gguf",
        size_mb=1500,
        description="Qwen3-VL 2B Thinking - Chain-of-thought reasoning"
    ),
    "qwen3-vl-4b": ModelConfig(
        repo_id="unsloth/Qwen3-VL-4B-Instruct-GGUF",
        model_file="Qwen3-VL-4B-Instruct-UD-Q4_K_XL.gguf",
        mmproj_file="mmproj-F16.gguf",
        size_mb=2800,
        description="Qwen3-VL 4B - Better quality, needs ~6GB RAM"
    ),
    "qwen3-vl-8b": ModelConfig(
        repo_id="unsloth/Qwen3-VL-8B-Instruct-GGUF",
        model_file="Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf",
        mmproj_file="mmproj-F16.gguf",
        size_mb=5000,
        description="Qwen3-VL 8B - Best quality, needs ~10GB RAM"
    ),
    # Text-only models (faster, no vision support)
    "qwen3-2b-text": ModelConfig(
        repo_id="unsloth/Qwen3-2B-Instruct-GGUF",
        model_file="Qwen3-2B-Instruct-Q4_K_M.gguf",
        mmproj_file=None,  # Text-only
        size_mb=1100,
        description="Qwen3 2B - Text-only, fastest"
    ),
}


class ModelManager:
    """Manages model downloading and storage."""

    def __init__(self, models_dir: Optional[Path] = None):
        if models_dir is None:
            # Default: ~/.trueflow/models/
            self.models_dir = Path.home() / ".trueflow" / "models"
        else:
            self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def get_model_path(self, model_name: str) -> Optional[Path]:
        """Get path to model file, or None if not downloaded."""
        if model_name not in MODELS:
            return None
        config = MODELS[model_name]
        model_path = self.models_dir / config.model_file
        if model_path.exists():
            return model_path
        return None

    def get_mmproj_path(self, model_name: str) -> Optional[Path]:
        """Get path to vision projector file."""
        if model_name not in MODELS:
            return None
        config = MODELS[model_name]
        if config.mmproj_file is None:
            return None
        mmproj_path = self.models_dir / config.mmproj_file
        if mmproj_path.exists():
            return mmproj_path
        return None

    def is_downloaded(self, model_name: str) -> bool:
        """Check if model is fully downloaded."""
        model_path = self.get_model_path(model_name)
        if model_path is None:
            return False

        # For vision models, also check mmproj
        config = MODELS.get(model_name)
        if config and config.mmproj_file:
            mmproj_path = self.get_mmproj_path(model_name)
            if mmproj_path is None:
                return False

        return True

    def download_model(
        self,
        model_name: str,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> bool:
        """
        Download model from HuggingFace.

        Args:
            model_name: Name of model (e.g., "qwen3-vl-2b")
            progress_callback: Optional callback(status_msg, progress_pct)

        Returns:
            True if successful
        """
        if model_name not in MODELS:
            logger.error(f"Unknown model: {model_name}")
            return False

        config = MODELS[model_name]

        def report(msg: str, pct: float):
            logger.info(f"{msg} ({pct:.1f}%)")
            if progress_callback:
                progress_callback(msg, pct)

        try:
            # Try using huggingface_hub if available
            try:
                from huggingface_hub import hf_hub_download
                report(f"Downloading {config.model_file}...", 0)

                # Download main model
                hf_hub_download(
                    repo_id=config.repo_id,
                    filename=config.model_file,
                    local_dir=str(self.models_dir),
                    local_dir_use_symlinks=False
                )
                report(f"Downloaded {config.model_file}", 50)

                # Download vision projector if needed
                if config.mmproj_file:
                    report(f"Downloading {config.mmproj_file}...", 50)
                    hf_hub_download(
                        repo_id=config.repo_id,
                        filename=config.mmproj_file,
                        local_dir=str(self.models_dir),
                        local_dir_use_symlinks=False
                    )
                    report(f"Downloaded {config.mmproj_file}", 100)
                else:
                    report("Download complete", 100)

                return True

            except ImportError:
                # Fall back to direct URL download
                report("huggingface_hub not installed, using direct download", 0)
                return self._download_direct(config, report)

        except Exception as e:
            logger.error(f"Download failed: {e}")
            return False

    def _download_direct(
        self,
        config: ModelConfig,
        report: Callable[[str, float], None]
    ) -> bool:
        """Download using direct HTTP."""
        base_url = f"https://huggingface.co/{config.repo_id}/resolve/main"

        files_to_download = [config.model_file]
        if config.mmproj_file:
            files_to_download.append(config.mmproj_file)

        for i, filename in enumerate(files_to_download):
            url = f"{base_url}/{filename}"
            dest = self.models_dir / filename

            report(f"Downloading {filename}...", (i / len(files_to_download)) * 100)

            try:
                # Download with progress
                self._download_file(url, dest, report)
            except Exception as e:
                logger.error(f"Failed to download {filename}: {e}")
                return False

        report("Download complete", 100)
        return True

    def _download_file(
        self,
        url: str,
        dest: Path,
        report: Callable[[str, float], None]
    ):
        """Download a single file with progress."""
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'TrueFlow/1.0')

        with urllib.request.urlopen(req) as response:
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            chunk_size = 1024 * 1024  # 1MB chunks

            with open(dest, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = (downloaded / total_size) * 100
                        report(f"Downloading... {downloaded // (1024*1024)}MB", pct)

    def list_available_models(self) -> List[Dict]:
        """List all available models with download status."""
        result = []
        for name, config in MODELS.items():
            result.append({
                "name": name,
                "description": config.description,
                "size_mb": config.size_mb,
                "downloaded": self.is_downloaded(name),
                "has_vision": config.mmproj_file is not None
            })
        return result


class LlamaCppServer:
    """
    Manages a llama.cpp server process.

    Provides OpenAI-compatible API at http://localhost:8080
    """

    def __init__(
        self,
        llama_cpp_path: Optional[Path] = None,
        port: int = 8080,
        n_ctx: int = 4096,
        n_threads: Optional[int] = None
    ):
        self.port = port
        self.n_ctx = n_ctx
        self.n_threads = n_threads or (os.cpu_count() or 4)
        self.process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

        # Find llama.cpp installation
        if llama_cpp_path:
            self.llama_cpp_path = Path(llama_cpp_path)
        else:
            self.llama_cpp_path = self._find_llama_cpp()

        self.model_manager = ModelManager()

    def _find_llama_cpp(self) -> Optional[Path]:
        """Find llama.cpp installation."""
        # Check common locations
        possible_paths = [
            Path.home() / "llama.cpp",
            Path.home() / ".trueflow" / "llama.cpp",
            Path("/usr/local/llama.cpp"),
            Path("C:/llama.cpp"),
        ]

        # Also check PATH
        server_names = ["llama-server", "llama-server.exe", "server", "server.exe"]
        for name in server_names:
            which = shutil.which(name)
            if which:
                return Path(which).parent.parent

        for path in possible_paths:
            if path.exists():
                return path

        return None

    def _get_server_executable(self) -> Optional[Path]:
        """Get path to llama-server executable."""
        if self.llama_cpp_path is None:
            return None

        # Check various possible locations
        possible_names = [
            self.llama_cpp_path / "build" / "bin" / "llama-server",
            self.llama_cpp_path / "build" / "bin" / "llama-server.exe",
            self.llama_cpp_path / "llama-server",
            self.llama_cpp_path / "llama-server.exe",
            self.llama_cpp_path / "server",
            self.llama_cpp_path / "server.exe",
        ]

        for path in possible_names:
            if path.exists():
                return path

        return None

    def is_installed(self) -> bool:
        """Check if llama.cpp is installed."""
        return self._get_server_executable() is not None

    def install_llama_cpp(
        self,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> bool:
        """
        Install llama.cpp from source (CPU-only build).

        This builds llama.cpp for CPU inference without CUDA.
        """
        def report(msg: str, pct: float):
            logger.info(f"{msg} ({pct:.1f}%)")
            if progress_callback:
                progress_callback(msg, pct)

        install_dir = Path.home() / ".trueflow" / "llama.cpp"

        try:
            report("Cloning llama.cpp repository...", 0)

            # Clone repo
            if install_dir.exists():
                shutil.rmtree(install_dir)

            subprocess.run(
                ["git", "clone", "--depth", "1", "https://github.com/ggml-org/llama.cpp", str(install_dir)],
                check=True,
                capture_output=True
            )
            report("Repository cloned", 20)

            # Build (CPU-only)
            report("Building llama.cpp (CPU-only)...", 30)

            build_dir = install_dir / "build"
            build_dir.mkdir(exist_ok=True)

            # CMake configure
            cmake_args = [
                "cmake", "..",
                "-DBUILD_SHARED_LIBS=OFF",
                "-DGGML_CUDA=OFF",  # CPU-only
                "-DLLAMA_CURL=OFF",
            ]

            subprocess.run(cmake_args, cwd=build_dir, check=True, capture_output=True)
            report("CMake configured", 50)

            # CMake build
            build_args = ["cmake", "--build", ".", "--config", "Release", "-j"]
            subprocess.run(build_args, cwd=build_dir, check=True, capture_output=True)
            report("Build complete", 100)

            self.llama_cpp_path = install_dir
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Build failed: {e.stderr.decode() if e.stderr else str(e)}")
            return False
        except Exception as e:
            logger.error(f"Installation failed: {e}")
            return False

    def start(
        self,
        model_name: str = "qwen3-vl-2b",
        callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Start the llama.cpp server with specified model.

        Args:
            model_name: Model to load
            callback: Optional callback for server output

        Returns:
            True if server started successfully
        """
        with self._lock:
            if self.process is not None:
                logger.warning("Server already running")
                return True

            # Get paths
            server_exe = self._get_server_executable()
            if server_exe is None:
                logger.error("llama.cpp server not found. Call install_llama_cpp() first.")
                return False

            model_path = self.model_manager.get_model_path(model_name)
            if model_path is None:
                logger.error(f"Model {model_name} not downloaded. Call download_model() first.")
                return False

            # Build command
            cmd = [
                str(server_exe),
                "--model", str(model_path),
                "--port", str(self.port),
                "--ctx-size", str(self.n_ctx),
                "--threads", str(self.n_threads),
                "--host", "127.0.0.1",
            ]

            # Add vision projector if available
            mmproj_path = self.model_manager.get_mmproj_path(model_name)
            if mmproj_path:
                cmd.extend(["--mmproj", str(mmproj_path)])

            logger.info(f"Starting server: {' '.join(cmd)}")

            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                # Wait for server to be ready
                ready = self._wait_for_ready(timeout=60, callback=callback)
                if not ready:
                    self.stop()
                    return False

                logger.info(f"Server started on port {self.port}")
                return True

            except Exception as e:
                logger.error(f"Failed to start server: {e}")
                return False

    def _wait_for_ready(
        self,
        timeout: int = 60,
        callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """Wait for server to be ready."""
        import urllib.request
        import urllib.error

        start_time = time.time()
        health_url = f"http://127.0.0.1:{self.port}/health"

        while time.time() - start_time < timeout:
            # Read any output
            if self.process and self.process.stdout:
                try:
                    line = self.process.stdout.readline()
                    if line and callback:
                        callback(line.strip())
                except:
                    pass

            # Check if process died
            if self.process and self.process.poll() is not None:
                logger.error("Server process died")
                return False

            # Check health endpoint
            try:
                req = urllib.request.urlopen(health_url, timeout=2)
                if req.status == 200:
                    return True
            except urllib.error.URLError:
                pass

            time.sleep(0.5)

        logger.error("Server startup timeout")
        return False

    def stop(self):
        """Stop the llama.cpp server."""
        with self._lock:
            if self.process is None:
                return

            logger.info("Stopping server...")

            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

            self.process = None
            logger.info("Server stopped")

    def is_running(self) -> bool:
        """Check if server is running."""
        with self._lock:
            return self.process is not None and self.process.poll() is None

    def get_api_base(self) -> str:
        """Get the API base URL."""
        return f"http://127.0.0.1:{self.port}/v1"


class LocalLLMService:
    """
    High-level service for local LLM inference.

    Usage:
        service = LocalLLMService()
        service.ensure_ready()  # Downloads model and starts server if needed
        response = service.generate("Explain this code...")

    Supports:
        - Preset models by name (e.g., "qwen3-vl-2b")
        - Custom model paths (e.g., "/path/to/model.gguf")
        - Custom HuggingFace URLs
    """

    def __init__(self, model_name: str = "qwen3-vl-2b", model_path: Optional[str] = None):
        """
        Initialize the LLM service.

        Args:
            model_name: Preset model name (used if model_path is None)
            model_path: Direct path to a GGUF model file (overrides model_name)
        """
        self.model_name = model_name
        self.model_path = model_path  # Custom model path
        self.server = LlamaCppServer()
        self.model_manager = ModelManager()

    def ensure_ready(
        self,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> bool:
        """
        Ensure the LLM service is ready to use.

        Downloads model and starts server if needed.
        Supports custom model paths - if model_path is set, uses that directly.
        """
        def report(msg: str, pct: float):
            if progress_callback:
                progress_callback(msg, pct)
            logger.info(f"{msg} ({pct:.1f}%)")

        # Step 1: Check/install llama.cpp
        if not self.server.is_installed():
            report("Installing llama.cpp...", 0)
            if not self.server.install_llama_cpp(progress_callback):
                return False
            report("llama.cpp installed", 25)
        else:
            report("llama.cpp found", 25)

        # Step 2: Check model availability
        if self.model_path:
            # Using custom model path
            if not Path(self.model_path).exists():
                logger.error(f"Custom model not found: {self.model_path}")
                return False
            report(f"Using custom model: {Path(self.model_path).name}", 75)
        else:
            # Using preset model
            if not self.model_manager.is_downloaded(self.model_name):
                report(f"Downloading {self.model_name}...", 25)
                if not self.model_manager.download_model(self.model_name, progress_callback):
                    return False
                report("Model downloaded", 75)
            else:
                report("Model found", 75)

        # Step 3: Start server
        if not self.server.is_running():
            report("Starting LLM server...", 75)
            # Use custom path or preset
            model_to_load = self.model_path if self.model_path else self.model_name
            if not self.server.start(model_to_load):
                return False
            report("Server ready", 100)
        else:
            report("Server already running", 100)

        return True

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.7
    ) -> str:
        """
        Generate text using the local LLM.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            Generated text
        """
        import urllib.request
        import json

        if not self.server.is_running():
            raise RuntimeError("LLM server not running. Call ensure_ready() first.")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        request_data = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        url = f"{self.server.get_api_base()}/chat/completions"
        req = urllib.request.Request(
            url,
            data=json.dumps(request_data).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result['choices'][0]['message']['content']
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return f"[Error: {e}]"

    def explain_trace(self, trace_data: Dict) -> str:
        """Explain a code execution trace."""
        calls = trace_data.get('calls', [])
        functions = [c.get('function', '') for c in calls if c.get('type') == 'call'][:20]
        modules = list(set(c.get('module', '') for c in calls if c.get('module')))[:10]

        prompt = f"""Analyze this code execution and explain what it does:

Functions called: {', '.join(functions)}
Modules: {', '.join(modules)}

In 2-3 sentences:
1. What is this code doing at a high level?
2. What design pattern does it follow?
3. Why might someone write code like this?"""

        system_prompt = "You are a code analysis expert. Be concise and technical."
        return self.generate(prompt, system_prompt)

    def explain_function(self, function_name: str, source_code: str) -> str:
        """Explain what a function does."""
        prompt = f"""Explain this function:

Name: {function_name}
Code:
```python
{source_code[:1000]}
```

In 2-3 sentences:
1. What does this function do?
2. What are its inputs and outputs?
3. Any potential issues or improvements?"""

        system_prompt = "You are a code review expert. Be concise and practical."
        return self.generate(prompt, system_prompt)

    def stop(self):
        """Stop the LLM service."""
        self.server.stop()


# Singleton instance
_service: Optional[LocalLLMService] = None


def get_local_llm_service() -> LocalLLMService:
    """Get the singleton LocalLLMService instance."""
    global _service
    if _service is None:
        _service = LocalLLMService()
    return _service


if __name__ == "__main__":
    # Test the local LLM service
    import argparse

    parser = argparse.ArgumentParser(description="TrueFlow Local LLM Service")
    parser.add_argument("--download", action="store_true", help="Download model")
    parser.add_argument("--install", action="store_true", help="Install llama.cpp")
    parser.add_argument("--start", action="store_true", help="Start server")
    parser.add_argument("--test", action="store_true", help="Test generation")
    parser.add_argument("--model", default="qwen3-vl-2b", help="Model name")

    args = parser.parse_args()

    service = LocalLLMService(args.model)

    if args.download:
        print("Downloading model...")
        service.model_manager.download_model(args.model, lambda m, p: print(f"  {m} ({p:.0f}%)"))

    if args.install:
        print("Installing llama.cpp...")
        service.server.install_llama_cpp(lambda m, p: print(f"  {m} ({p:.0f}%)"))

    if args.start or args.test:
        print("Ensuring LLM service is ready...")
        if not service.ensure_ready(lambda m, p: print(f"  {m} ({p:.0f}%)")):
            print("Failed to start service")
            sys.exit(1)

    if args.test:
        print("\nTesting generation...")
        response = service.generate(
            "What is recursion in programming?",
            "You are a helpful programming tutor."
        )
        print(f"\nResponse:\n{response}")

    if not any([args.download, args.install, args.start, args.test]):
        print("Available models:")
        for model in service.model_manager.list_available_models():
            status = "downloaded" if model['downloaded'] else "not downloaded"
            vision = " (vision)" if model['has_vision'] else ""
            print(f"  {model['name']}: {model['description']}{vision} [{status}]")
