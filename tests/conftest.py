from pathlib import Path

import pytest

pytest_plugins = ["tests.db"]

FIXTURES = Path(__file__).parent / "fixtures"
PACKAGES = FIXTURES / "packages"


@pytest.fixture
def packages() -> Path:
    return PACKAGES
