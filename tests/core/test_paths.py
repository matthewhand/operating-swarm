"""
Comprehensive tests for paths module
===================================

Tests XDG-compliant directory management and path resolution.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from swarm.core.paths import (
    APP_AUTHOR,
    APP_NAME,
    ensure_swarm_directories_exist,
    get_project_root_dir,
    get_swarm_config_file,
    get_user_bin_dir,
    get_user_blueprints_dir,
    get_user_cache_dir_for_swarm,
    get_user_config_dir_for_swarm,
    get_user_data_dir_for_swarm,
)


class TestPathConstants:
    """Test path constants and basic setup."""

    def test_app_constants(self):
        """Test that app constants are properly defined."""
        assert APP_NAME == "swarm"
        assert APP_AUTHOR == "OpenSwarm"


class TestUserDataDirectory:
    """Test user data directory functionality."""

    def test_get_user_data_dir_for_swarm_default(self):
        """Test default user data directory path."""
        with patch.dict(os.environ, {}, clear=True):
            path = get_user_data_dir_for_swarm()
            assert isinstance(path, Path)
            # Note: In this environment, path does not include APP_AUTHOR; check for appname only
            assert "swarm" in str(path).lower()

    def test_get_user_data_dir_for_swarm_override(self):
        """Test user data directory with environment override."""
        override_path = "/custom/swarm/data"
        with patch.dict(os.environ, {"SWARM_USER_DATA_DIR": override_path}):
            path = get_user_data_dir_for_swarm()
            assert str(path) == override_path

    def test_get_user_data_dir_for_swarm_path_type(self):
        """Test that user data directory returns Path object."""
        path = get_user_data_dir_for_swarm()
        assert isinstance(path, Path)


class TestUserBlueprintsDirectory:
    """Test user blueprints directory functionality."""

    def test_get_user_blueprints_dir_structure(self):
        """Test that blueprints directory is subdirectory of data directory."""
        data_dir = get_user_data_dir_for_swarm()
        blueprints_dir = get_user_blueprints_dir()

        assert blueprints_dir.parent == data_dir
        assert blueprints_dir.name == "blueprints"

    def test_get_user_blueprints_dir_path_type(self):
        """Test that blueprints directory returns Path object."""
        path = get_user_blueprints_dir()
        assert isinstance(path, Path)


class TestUserBinDirectory:
    """Test user bin directory functionality."""

    def test_get_user_bin_dir_structure(self):
        """Test that bin directory is subdirectory of data directory."""
        data_dir = get_user_data_dir_for_swarm()
        bin_dir = get_user_bin_dir()

        assert bin_dir.parent == data_dir
        assert bin_dir.name == "bin"

    def test_get_user_bin_dir_path_type(self):
        """Test that bin directory returns Path object."""
        path = get_user_bin_dir()
        assert isinstance(path, Path)


class TestUserCacheDirectory:
    """Test user cache directory functionality."""

    def test_get_user_cache_dir_for_swarm_path_type(self):
        """Test that cache directory returns Path object."""
        path = get_user_cache_dir_for_swarm()
        assert isinstance(path, Path)

    def test_get_user_cache_dir_for_swarm_contains_app_info(self):
        """Test that cache directory path contains app information."""
        path = get_user_cache_dir_for_swarm()
        path_str = str(path)
        # Cache dir does not include APP_AUTHOR on Linux; check for appname only
        assert "swarm" in path_str.lower()


class TestUserConfigDirectory:
    """Test user config directory functionality."""

    def test_get_user_config_dir_for_swarm_path_type(self):
        """Test that config directory returns Path object."""
        path = get_user_config_dir_for_swarm()
        assert isinstance(path, Path)

    def test_get_user_config_dir_for_swarm_contains_app_info(self):
        """Test that config directory path contains app information."""
        path = get_user_config_dir_for_swarm()
        path_str = str(path)
        # Note: In this environment, path does not include APP_AUTHOR; check for appname only
        assert "swarm" in path_str.lower()


class TestSwarmConfigFile:
    """Test swarm config file path functionality."""

    def test_get_swarm_config_file_default(self):
        """Test default config file path.

        ``swarm_config.json`` is the name every reader/writer uses; the previous
        ``config.yaml`` default named a file nothing wrote and loaded as JSON.
        """
        config_dir = get_user_config_dir_for_swarm()
        config_file = get_swarm_config_file()

        assert config_file.parent == config_dir
        assert config_file.name == "swarm_config.json"

    def test_get_swarm_config_file_custom_name(self):
        """Test config file path with custom filename."""
        config_dir = get_user_config_dir_for_swarm()
        config_file = get_swarm_config_file("custom.json")

        assert config_file.parent == config_dir
        assert config_file.name == "custom.json"

    def test_get_swarm_config_file_path_type(self):
        """Test that config file returns Path object."""
        path = get_swarm_config_file()
        assert isinstance(path, Path)


class TestProjectRootDirectory:
    """Test project root directory functionality."""

    def test_get_project_root_dir_path_type(self):
        """Test that project root directory returns Path object."""
        path = get_project_root_dir()
        assert isinstance(path, Path)

    def test_get_project_root_dir_is_absolute(self):
        """Test that project root directory is an absolute path."""
        path = get_project_root_dir()
        assert path.is_absolute()

    def test_get_project_root_dir_contains_src(self):
        """Test that project root directory contains src directory."""
        root_dir = get_project_root_dir()
        src_dir = root_dir / "src"
        assert src_dir.is_dir()
        assert (root_dir / "pyproject.toml").exists()


class TestEnsureSwarmDirectoriesExist:
    """Test directory creation functionality."""

    def test_ensure_swarm_directories_exist_creates_directories(self):
        """Test that ensure_swarm_directories_exist creates required directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Mock the directory functions to use our temp directory
            with patch('swarm.core.paths.get_user_data_dir_for_swarm', return_value=temp_path / "data"), \
                 patch('swarm.core.paths.get_user_blueprints_dir', return_value=temp_path / "data" / "blueprints"), \
                 patch('swarm.core.paths.get_user_bin_dir', return_value=temp_path / "data" / "bin"), \
                 patch('swarm.core.paths.get_user_cache_dir_for_swarm', return_value=temp_path / "cache"), \
                 patch('swarm.core.paths.get_user_config_dir_for_swarm', return_value=temp_path / "config"):

                ensure_swarm_directories_exist()

                # Check that directories were created
                assert (temp_path / "data").exists()
                assert (temp_path / "data" / "blueprints").exists()
                assert (temp_path / "data" / "bin").exists()
                assert (temp_path / "cache").exists()
                assert (temp_path / "config").exists()

    def test_ensure_swarm_directories_exist_idempotent(self):
        """Test that ensure_swarm_directories_exist is idempotent."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            with patch('swarm.core.paths.get_user_data_dir_for_swarm', return_value=temp_path / "data"), \
                 patch('swarm.core.paths.get_user_blueprints_dir', return_value=temp_path / "data" / "blueprints"), \
                 patch('swarm.core.paths.get_user_bin_dir', return_value=temp_path / "data" / "bin"), \
                 patch('swarm.core.paths.get_user_cache_dir_for_swarm', return_value=temp_path / "cache"), \
                 patch('swarm.core.paths.get_user_config_dir_for_swarm', return_value=temp_path / "config"):

                # Call multiple times
                ensure_swarm_directories_exist()
                ensure_swarm_directories_exist()
                ensure_swarm_directories_exist()

                # Should still exist and be directories
                assert (temp_path / "data").exists()
                assert (temp_path / "data").is_dir()

    def test_ensure_swarm_directories_exist_tolerates_broken_cache_root(self):
        """Broken XDG cache symlink must not prevent other dirs from being created."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            broken = temp_path / "broken-cache-link"
            broken.symlink_to(temp_path / "does-not-exist")
            # platformdirs-style: parent is broken symlink, child is .../swarm
            bad_cache = broken / "OpenSwarm" / "swarm"

            with patch('swarm.core.paths.get_user_data_dir_for_swarm', return_value=temp_path / "data"), \
                 patch('swarm.core.paths.get_user_blueprints_dir', return_value=temp_path / "data" / "blueprints"), \
                 patch('swarm.core.paths.get_user_bin_dir', return_value=temp_path / "data" / "bin"), \
                 patch('swarm.core.paths.get_user_cache_dir_for_swarm', return_value=bad_cache), \
                 patch('swarm.core.paths.get_user_config_dir_for_swarm', return_value=temp_path / "config"):

                ensure_swarm_directories_exist()  # must not raise

                assert (temp_path / "data").is_dir()
                assert (temp_path / "config").is_dir()
                assert not bad_cache.exists()


class TestPathRelationships:
    """Test relationships between different path functions."""

    def test_directory_hierarchy(self):
        """Test that directory hierarchy is maintained."""
        data_dir = get_user_data_dir_for_swarm()
        blueprints_dir = get_user_blueprints_dir()
        bin_dir = get_user_bin_dir()

        # All should be under the data directory
        assert blueprints_dir.parent == data_dir
        assert bin_dir.parent == data_dir

    def test_config_vs_data_separation(self):
        """Test that config and data directories are separate."""
        data_dir = get_user_data_dir_for_swarm()
        config_dir = get_user_config_dir_for_swarm()
        cache_dir = get_user_cache_dir_for_swarm()

        # These should be different directories
        assert data_dir != config_dir
        assert data_dir != cache_dir
        assert config_dir != cache_dir


class TestCrossPlatformCompatibility:
    """Test cross-platform path compatibility."""

    def test_paths_work_on_different_platforms(self):
        """Test that paths work regardless of platform."""
        # These functions should work on any platform supported by platformdirs
        data_dir = get_user_data_dir_for_swarm()
        config_dir = get_user_config_dir_for_swarm()
        cache_dir = get_user_cache_dir_for_swarm()

        # All should be valid paths
        assert data_dir is not None
        assert config_dir is not None
        assert cache_dir is not None

        # All should be absolute paths
        assert data_dir.is_absolute()
        assert config_dir.is_absolute()
        assert cache_dir.is_absolute()

    def test_config_file_extension_handling(self):
        """Test that config file handles different extensions."""
        extensions = ["yaml", "yml", "json", "toml", "ini"]

        for ext in extensions:
            filename = f"config.{ext}"
            config_file = get_swarm_config_file(filename)
            assert config_file.name == filename
            assert config_file.suffix == f".{ext}"


class TestPathSecurity:
    """Test path security and safety."""

    def test_no_path_traversal_in_config_filename(self):
        """Test that config filename cannot contain path traversal."""
        # This should be safe - platformdirs should handle this
        safe_filename = get_swarm_config_file("../../../etc/passwd")
        config_dir = get_user_config_dir_for_swarm()

        # The file should still be within the config directory
        assert safe_filename.parent == config_dir
        assert safe_filename.name == "passwd"  # Path traversal is prevented, only basename is used

    def test_environment_override_security(self):
        """Test that environment override is handled safely."""
        # Test with various override values
        test_paths = [
            "/valid/path",
            "/tmp/test",
            "~/test/path",
            "$HOME/test"
        ]

        for test_path in test_paths:
            with patch.dict(os.environ, {"SWARM_USER_DATA_DIR": test_path}):
                path = get_user_data_dir_for_swarm()
                # Should return a Path object regardless of input
                assert isinstance(path, Path)


class TestPlatformDirsIntegration:
    """Test integration with platformdirs library."""

    @patch("swarm.core.paths.platformdirs.user_data_dir")
    def test_get_user_data_dir_calls_platformdirs(self, mock_user_data_dir):
        """Test that get_user_data_dir_for_swarm calls platformdirs correctly."""
        mock_user_data_dir.return_value = "/mock/data/dir"
        with patch.dict(os.environ, {}, clear=True):
            path = get_user_data_dir_for_swarm()
            assert str(path) == "/mock/data/dir"
            mock_user_data_dir.assert_called_once_with(
                appname=APP_NAME, appauthor=APP_AUTHOR
            )

    @patch("swarm.core.paths.platformdirs.user_cache_dir")
    def test_get_user_cache_dir_calls_platformdirs(self, mock_user_cache_dir):
        """Test that get_user_cache_dir_for_swarm calls platformdirs correctly."""
        mock_user_cache_dir.return_value = "/mock/cache/dir"
        path = get_user_cache_dir_for_swarm()
        assert str(path) == "/mock/cache/dir"
        mock_user_cache_dir.assert_called_once_with(
            appname=APP_NAME, appauthor=APP_AUTHOR
        )

    @patch("swarm.core.paths.platformdirs.user_config_dir")
    def test_get_user_config_dir_calls_platformdirs(self, mock_user_config_dir):
        """Test that get_user_config_dir_for_swarm calls platformdirs correctly."""
        mock_user_config_dir.return_value = "/mock/config/dir"
        path = get_user_config_dir_for_swarm()
        assert str(path) == "/mock/config/dir"
        mock_user_config_dir.assert_called_once_with(
            appname=APP_NAME, appauthor=APP_AUTHOR
        )


class TestCrossPlatformMocks:
    """Test path behavior with simulated platforms."""

    @patch("sys.platform", "win32")
    @patch("swarm.core.paths.platformdirs.user_data_dir")
    def test_get_user_data_dir_windows_mock(self, mock_user_data_dir):
        """Test user data directory resolution on simulated Windows."""
        mock_user_data_dir.return_value = "C:\\Users\\Test\\AppData\\Local\\OpenSwarm\\swarm"
        with patch.dict(os.environ, {}, clear=True):
            path = get_user_data_dir_for_swarm()
            assert str(path) == "C:\\Users\\Test\\AppData\\Local\\OpenSwarm\\swarm"

    @patch("sys.platform", "linux")
    @patch("swarm.core.paths.platformdirs.user_data_dir")
    def test_get_user_data_dir_linux_mock(self, mock_user_data_dir):
        """Test user data directory resolution on simulated Linux."""
        mock_user_data_dir.return_value = "/home/test/.local/share/swarm"
        with patch.dict(os.environ, {}, clear=True):
            path = get_user_data_dir_for_swarm()
            assert str(path) == "/home/test/.local/share/swarm"
