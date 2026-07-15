from pathlib import Path

from fastapi import FastAPI

import app.main


def test_application_module_exists() -> None:
    assert (Path(__file__).parents[1] / "app" / "main.py").is_file()


def test_application_exposes_fastapi_app() -> None:
    assert isinstance(getattr(app.main, "app", None), FastAPI)
