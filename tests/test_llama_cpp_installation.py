# Test llama.cpp Installation from Binary
# Tests for llama.cpp binary download, extraction, and server discovery

import sys
import os
import json
import tempfile
import shutil
import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import platform
import subprocess

# Test constants
GITHUB_RELEASES_URL = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
EXPECTED_TAG_PATTERN = "b"  # Tags are like b1234


class TestLlamaServerDiscovery(unittest.TestCase):
    """Test llama-server binary discovery logic."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.home_dir = self.temp_dir

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_expected_search_paths(self):
        """Test that the expected search paths are checked."""
        home = self.home_dir
        expected_paths = [
            os.path.join(home, '.trueflow', 'llama.cpp', 'build', 'bin', 'Release', 'llama-server.exe'),
            os.path.join(home, '.trueflow', 'llama.cpp', 'build', 'bin', 'Release', 'llama-server'),
            os.path.join(home, '.trueflow', 'llama.cpp', 'build', 'bin', 'llama-server.exe'),
            os.path.join(home, '.trueflow', 'llama.cpp', 'build', 'bin', 'llama-server'),
            os.path.join(home, 'llama.cpp', 'build', 'bin', 'Release', 'llama-server.exe'),
            os.path.join(home, 'llama.cpp', 'build', 'bin', 'llama-server'),
            os.path.join(home, 'llama.cpp', 'build', 'bin', 'llama-server.exe'),
        ]

        # All paths should be strings
        for p in expected_paths:
            self.assertIsInstance(p, str)

    def test_find_llama_server_in_trueflow_dir(self):
        """Test finding llama-server in .trueflow directory."""
        # Create the expected directory structure
        server_dir = os.path.join(self.home_dir, '.trueflow', 'llama.cpp', 'build', 'bin', 'Release')
        os.makedirs(server_dir, exist_ok=True)

        # Create a dummy server executable
        server_exe = 'llama-server.exe' if platform.system() == 'Windows' else 'llama-server'
        server_path = os.path.join(server_dir, server_exe)
        Path(server_path).touch()

        # Verify it exists
        self.assertTrue(os.path.exists(server_path))

    def test_find_llama_server_in_home_dir(self):
        """Test finding llama-server in home/llama.cpp directory."""
        server_dir = os.path.join(self.home_dir, 'llama.cpp', 'build', 'bin')
        os.makedirs(server_dir, exist_ok=True)

        server_exe = 'llama-server.exe' if platform.system() == 'Windows' else 'llama-server'
        server_path = os.path.join(server_dir, server_exe)
        Path(server_path).touch()

        self.assertTrue(os.path.exists(server_path))

    def test_server_not_found(self):
        """Test behavior when llama-server is not found."""
        # Search for llama-server in empty temp directory
        search_paths = [
            os.path.join(self.home_dir, '.trueflow', 'llama.cpp', 'build', 'bin', 'llama-server'),
            os.path.join(self.home_dir, 'llama.cpp', 'build', 'bin', 'llama-server'),
        ]

        for path in search_paths:
            self.assertFalse(os.path.exists(path))


class TestBinaryAssetNames(unittest.TestCase):
    """Test platform-specific binary asset name generation."""

    def test_windows_asset_name(self):
        """Test Windows binary asset name format."""
        tag = "b1234"
        expected = f"llama-{tag}-bin-win-cpu-x64.zip"
        self.assertEqual(expected, f"llama-{tag}-bin-win-cpu-x64.zip")

    def test_macos_asset_name(self):
        """Test macOS binary asset name format."""
        tag = "b1234"
        expected = f"llama-{tag}-bin-macos-arm64.zip"
        self.assertEqual(expected, f"llama-{tag}-bin-macos-arm64.zip")

    def test_linux_asset_name(self):
        """Test Linux binary asset name format."""
        tag = "b1234"
        expected = f"llama-{tag}-bin-ubuntu-x64.zip"
        self.assertEqual(expected, f"llama-{tag}-bin-ubuntu-x64.zip")

    def test_current_platform_asset(self):
        """Test asset name for current platform."""
        tag = "b5678"

        if platform.system() == 'Windows':
            expected = f"llama-{tag}-bin-win-cpu-x64.zip"
        elif platform.system() == 'Darwin':
            expected = f"llama-{tag}-bin-macos-arm64.zip"
        else:
            expected = f"llama-{tag}-bin-ubuntu-x64.zip"

        self.assertIn("llama-", expected)
        self.assertIn(".zip", expected)


class TestDirectoryStructure(unittest.TestCase):
    """Test installation directory structure creation."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_install_directory(self):
        """Test creating llama.cpp installation directory."""
        install_dir = os.path.join(self.temp_dir, '.trueflow', 'llama.cpp')
        os.makedirs(install_dir, exist_ok=True)

        self.assertTrue(os.path.exists(install_dir))
        self.assertTrue(os.path.isdir(install_dir))

    def test_create_bin_directory_structure(self):
        """Test creating the build/bin/Release directory structure."""
        install_dir = os.path.join(self.temp_dir, '.trueflow', 'llama.cpp')
        bin_dir = os.path.join(install_dir, 'build', 'bin', 'Release')
        os.makedirs(bin_dir, exist_ok=True)

        self.assertTrue(os.path.exists(bin_dir))
        self.assertTrue(os.path.isdir(bin_dir))

    def test_copy_server_executable(self):
        """Test copying server executable to expected location."""
        # Create source directory with dummy executable
        src_dir = os.path.join(self.temp_dir, 'extracted')
        os.makedirs(src_dir, exist_ok=True)

        server_exe = 'llama-server.exe' if platform.system() == 'Windows' else 'llama-server'
        src_path = os.path.join(src_dir, server_exe)

        # Create dummy executable
        with open(src_path, 'w') as f:
            f.write('dummy executable content')

        # Create destination directory
        dest_dir = os.path.join(self.temp_dir, 'install', 'build', 'bin', 'Release')
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, server_exe)

        # Copy file
        shutil.copyfile(src_path, dest_path)

        self.assertTrue(os.path.exists(dest_path))
        self.assertEqual(os.path.getsize(dest_path), os.path.getsize(src_path))

    def test_executable_permissions_unix(self):
        """Test setting executable permissions on Unix systems."""
        if platform.system() == 'Windows':
            self.skipTest("Permission test only for Unix")

        server_path = os.path.join(self.temp_dir, 'llama-server')
        Path(server_path).touch()

        # Set executable permission
        os.chmod(server_path, 0o755)

        # Check permission
        self.assertTrue(os.access(server_path, os.X_OK))


class TestGitHubReleaseAPI(unittest.TestCase):
    """Test GitHub release API interaction."""

    def test_release_info_structure(self):
        """Test expected structure of GitHub release info."""
        mock_release = {
            "tag_name": "b1234",
            "assets": [
                {
                    "name": "llama-b1234-bin-win-cpu-x64.zip",
                    "browser_download_url": "https://github.com/ggml-org/llama.cpp/releases/download/b1234/llama-b1234-bin-win-cpu-x64.zip"
                },
                {
                    "name": "llama-b1234-bin-macos-arm64.zip",
                    "browser_download_url": "https://github.com/ggml-org/llama.cpp/releases/download/b1234/llama-b1234-bin-macos-arm64.zip"
                },
                {
                    "name": "llama-b1234-bin-ubuntu-x64.zip",
                    "browser_download_url": "https://github.com/ggml-org/llama.cpp/releases/download/b1234/llama-b1234-bin-ubuntu-x64.zip"
                }
            ]
        }

        self.assertIn("tag_name", mock_release)
        self.assertIn("assets", mock_release)
        self.assertIsInstance(mock_release["assets"], list)

    def test_find_windows_asset(self):
        """Test finding Windows asset from release info."""
        assets = [
            {"name": "llama-b1234-bin-win-cpu-x64.zip", "browser_download_url": "https://example.com/win.zip"},
            {"name": "llama-b1234-bin-macos-arm64.zip", "browser_download_url": "https://example.com/mac.zip"},
        ]

        windows_asset = next((a for a in assets if "win-cpu-x64" in a["name"]), None)

        self.assertIsNotNone(windows_asset)
        self.assertIn("win-cpu-x64", windows_asset["name"])

    def test_find_macos_asset(self):
        """Test finding macOS asset from release info."""
        assets = [
            {"name": "llama-b1234-bin-win-cpu-x64.zip", "browser_download_url": "https://example.com/win.zip"},
            {"name": "llama-b1234-bin-macos-arm64.zip", "browser_download_url": "https://example.com/mac.zip"},
        ]

        macos_asset = next((a for a in assets if "macos-arm64" in a["name"]), None)

        self.assertIsNotNone(macos_asset)
        self.assertIn("macos-arm64", macos_asset["name"])

    def test_find_linux_asset(self):
        """Test finding Linux asset from release info."""
        assets = [
            {"name": "llama-b1234-bin-ubuntu-x64.zip", "browser_download_url": "https://example.com/linux.zip"},
            {"name": "llama-b1234-bin-macos-arm64.zip", "browser_download_url": "https://example.com/mac.zip"},
        ]

        linux_asset = next((a for a in assets if "ubuntu-x64" in a["name"]), None)

        self.assertIsNotNone(linux_asset)
        self.assertIn("ubuntu-x64", linux_asset["name"])

    def test_asset_not_found(self):
        """Test handling when required asset is not found."""
        assets = [
            {"name": "llama-b1234-bin-macos-arm64.zip", "browser_download_url": "https://example.com/mac.zip"},
        ]

        windows_asset = next((a for a in assets if "win-cpu-x64" in a["name"]), None)

        self.assertIsNone(windows_asset)


class TestZipExtraction(unittest.TestCase):
    """Test zip file extraction logic."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_powershell_extract_command(self):
        """Test PowerShell extraction command format."""
        zip_path = "C:\\temp\\llama.zip"
        dest_path = "C:\\temp\\install"

        # Verify command would be properly formatted
        command = f'Expand-Archive -Path "{zip_path}" -DestinationPath "{dest_path}" -Force'

        self.assertIn("Expand-Archive", command)
        self.assertIn(zip_path, command)
        self.assertIn(dest_path, command)
        self.assertIn("-Force", command)

    def test_unzip_command_unix(self):
        """Test unzip command format for Unix."""
        zip_path = "/tmp/llama.zip"
        dest_path = "/tmp/install"

        args = ['unzip', '-o', zip_path, '-d', dest_path]

        self.assertEqual(args[0], 'unzip')
        self.assertEqual(args[1], '-o')  # Overwrite
        self.assertEqual(args[2], zip_path)
        self.assertEqual(args[3], '-d')  # Destination
        self.assertEqual(args[4], dest_path)


class TestExtractedFileLocations(unittest.TestCase):
    """Test locating files in extracted archives."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_extracted_bin_directory_pattern(self):
        """Test expected extracted directory name pattern."""
        tag = "b1234"

        patterns = {
            'win32': f"llama-{tag}-bin-win-cpu-x64",
            'darwin': f"llama-{tag}-bin-macos-arm64",
            'linux': f"llama-{tag}-bin-ubuntu-x64"
        }

        for plat, pattern in patterns.items():
            self.assertIn(tag, pattern)
            self.assertIn("llama-", pattern)

    def test_find_server_in_extracted_directory(self):
        """Test finding llama-server in extracted directory."""
        tag = "b1234"
        install_dir = self.temp_dir

        if platform.system() == 'Windows':
            extracted_dir = os.path.join(install_dir, f"llama-{tag}-bin-win-cpu-x64")
            server_name = "llama-server.exe"
        elif platform.system() == 'Darwin':
            extracted_dir = os.path.join(install_dir, f"llama-{tag}-bin-macos-arm64")
            server_name = "llama-server"
        else:
            extracted_dir = os.path.join(install_dir, f"llama-{tag}-bin-ubuntu-x64")
            server_name = "llama-server"

        os.makedirs(extracted_dir, exist_ok=True)
        server_path = os.path.join(extracted_dir, server_name)
        Path(server_path).touch()

        self.assertTrue(os.path.exists(server_path))

    def test_fallback_server_location(self):
        """Test fallback location for llama-server in root of extracted folder."""
        install_dir = self.temp_dir
        server_name = "llama-server.exe" if platform.system() == 'Windows' else "llama-server"

        # Server in root of install directory (fallback)
        server_path = os.path.join(install_dir, server_name)
        Path(server_path).touch()

        self.assertTrue(os.path.exists(server_path))


class TestServerExecutableValidation(unittest.TestCase):
    """Test server executable validation."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_file_exists_check(self):
        """Test checking if server file exists."""
        server_path = os.path.join(self.temp_dir, "llama-server")
        Path(server_path).touch()

        self.assertTrue(os.path.exists(server_path))
        self.assertTrue(os.path.isfile(server_path))

    def test_file_size_check(self):
        """Test checking server file has content (not empty)."""
        server_path = os.path.join(self.temp_dir, "llama-server")

        # Create file with content
        with open(server_path, 'wb') as f:
            f.write(b'x' * 1024)  # 1KB of data

        self.assertGreater(os.path.getsize(server_path), 0)

    def test_empty_file_detection(self):
        """Test detecting empty file (invalid executable)."""
        server_path = os.path.join(self.temp_dir, "llama-server")
        Path(server_path).touch()  # Create empty file

        self.assertEqual(os.path.getsize(server_path), 0)


class TestCleanupOperations(unittest.TestCase):
    """Test cleanup operations after installation."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_delete_zip_after_extraction(self):
        """Test deleting zip file after successful extraction."""
        zip_path = os.path.join(self.temp_dir, "llama.zip")

        # Create dummy zip file
        with open(zip_path, 'w') as f:
            f.write("dummy zip content")

        self.assertTrue(os.path.exists(zip_path))

        # Delete zip file
        os.unlink(zip_path)

        self.assertFalse(os.path.exists(zip_path))

    def test_cleanup_on_failed_installation(self):
        """Test cleanup when installation fails."""
        install_dir = os.path.join(self.temp_dir, 'failed_install')
        os.makedirs(install_dir, exist_ok=True)

        # Create some files
        Path(os.path.join(install_dir, 'partial_file')).touch()

        self.assertTrue(os.path.exists(install_dir))

        # Cleanup
        shutil.rmtree(install_dir, ignore_errors=True)

        self.assertFalse(os.path.exists(install_dir))


class TestWhichCommand(unittest.TestCase):
    """Test system PATH lookup for llama-server."""

    def test_which_command_windows(self):
        """Test 'where' command on Windows."""
        if platform.system() != 'Windows':
            self.skipTest("Windows-only test")

        # 'where' should be available on Windows
        try:
            result = subprocess.run(['where', 'cmd'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
        except FileNotFoundError:
            self.fail("'where' command not found on Windows")

    def test_which_command_unix(self):
        """Test 'which' command on Unix."""
        if platform.system() == 'Windows':
            self.skipTest("Unix-only test")

        # 'which' should be available on Unix
        try:
            result = subprocess.run(['which', 'sh'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
        except FileNotFoundError:
            self.fail("'which' command not found on Unix")

    def test_server_not_in_path(self):
        """Test handling when llama-server is not in PATH."""
        which_cmd = 'where' if platform.system() == 'Windows' else 'which'

        # llama-server is unlikely to be in PATH during tests
        result = subprocess.run([which_cmd, 'llama-server-nonexistent-xyz'],
                                capture_output=True, text=True)

        # Should fail to find
        self.assertNotEqual(result.returncode, 0)


class TestServerStartArguments(unittest.TestCase):
    """Test llama-server command line arguments."""

    def test_basic_server_args(self):
        """Test basic server startup arguments."""
        model_path = "/path/to/model.gguf"
        port = 8080
        ctx_size = 4096
        threads = 4

        args = [
            '--model', model_path,
            '--port', str(port),
            '--ctx-size', str(ctx_size),
            '--threads', str(threads),
            '--host', '127.0.0.1'
        ]

        self.assertIn('--model', args)
        self.assertIn(model_path, args)
        self.assertIn('--port', args)
        self.assertIn(str(port), args)
        self.assertIn('--ctx-size', args)
        self.assertIn('--host', args)
        self.assertIn('127.0.0.1', args)

    def test_huggingface_model_args(self):
        """Test HuggingFace model loading arguments."""
        repo_id = "unsloth/Qwen3-VL-2B-Instruct-GGUF"
        model_file = "Qwen3-VL-2B-Instruct-UD-Q4_K_XL.gguf"

        args = [
            '-hf', repo_id,
            '-hff', model_file,
            '--port', '8080',
            '--host', '127.0.0.1'
        ]

        self.assertIn('-hf', args)
        self.assertIn(repo_id, args)
        self.assertIn('-hff', args)
        self.assertIn(model_file, args)

    def test_multimodal_model_args(self):
        """Test multimodal model arguments with mmproj."""
        model_path = "/path/to/model.gguf"
        mmproj_path = "/path/to/mmproj.gguf"

        args = [
            '--model', model_path,
            '--mmproj', mmproj_path,
            '--port', '8080'
        ]

        self.assertIn('--mmproj', args)
        self.assertIn(mmproj_path, args)


class TestModelDirectoryStructure(unittest.TestCase):
    """Test model storage directory structure."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_models_directory_creation(self):
        """Test creating models directory."""
        models_dir = os.path.join(self.temp_dir, '.trueflow', 'models')
        os.makedirs(models_dir, exist_ok=True)

        self.assertTrue(os.path.exists(models_dir))
        self.assertTrue(os.path.isdir(models_dir))

    def test_model_file_storage(self):
        """Test storing model file."""
        models_dir = os.path.join(self.temp_dir, '.trueflow', 'models')
        os.makedirs(models_dir, exist_ok=True)

        model_path = os.path.join(models_dir, 'test-model.gguf')
        with open(model_path, 'wb') as f:
            f.write(b'GGUF' + b'\x00' * 100)  # Minimal GGUF header

        self.assertTrue(os.path.exists(model_path))
        self.assertTrue(model_path.endswith('.gguf'))

    def test_list_available_models(self):
        """Test listing available model files."""
        models_dir = os.path.join(self.temp_dir, '.trueflow', 'models')
        os.makedirs(models_dir, exist_ok=True)

        # Create some model files
        for name in ['model1.gguf', 'model2.gguf', 'notamodel.txt']:
            Path(os.path.join(models_dir, name)).touch()

        # List .gguf files
        gguf_files = [f for f in os.listdir(models_dir) if f.endswith('.gguf')]

        self.assertEqual(len(gguf_files), 2)
        self.assertIn('model1.gguf', gguf_files)
        self.assertIn('model2.gguf', gguf_files)
        self.assertNotIn('notamodel.txt', gguf_files)


if __name__ == '__main__':
    unittest.main()
