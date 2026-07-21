from pathlib import Path

import pytest


pytestmark = pytest.mark.contract


README_PATH = Path(__file__).parents[2] / "README.md"


def test_documented_server_commands_disable_uvicorn_access_logs() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    assert "uv run fastapi dev" not in readme
    assert readme.count("uv run uvicorn app.main:app") == 1
    assert readme.count("--no-access-log") == 1
    assert "## Quick start" in readme
    assert "## Setup" in readme
    assert "## Status and diagnostics" not in readme
    assert "## Reference" not in readme
