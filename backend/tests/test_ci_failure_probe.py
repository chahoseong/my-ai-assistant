import pytest


@pytest.mark.unit
def test_ci_detects_pytest_failure() -> None:
    assert False, "intentional CI failure probe"
