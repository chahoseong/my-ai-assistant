import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_load_database_settings_reads_database_url() -> None:
    config = importlib.import_module("app.config")

    settings = config.load_database_settings(
        {"DATABASE_URL": "postgresql+asyncpg://assistant:assistant@db/assistant_dev"}
    )

    assert settings.url == "postgresql+asyncpg://assistant:assistant@db/assistant_dev"


def test_load_database_settings_rejects_missing_database_url() -> None:
    config = importlib.import_module("app.config")

    with pytest.raises(ValueError, match="DATABASE_URL must be set"):
        config.load_database_settings({})


def test_unit_tests_can_run_without_database_urls() -> None:
    test_environment = dict(os.environ)
    test_environment.pop("DATABASE_URL", None)
    test_environment.pop("TEST_DATABASE_URL", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_config.py::test_load_database_settings_reads_database_url",
        ],
        cwd=PROJECT_ROOT,
        env=test_environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
