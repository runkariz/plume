from collections.abc import Iterator

import pytest
from sqlalchemy import Engine

from plume.infrastructure.db.engine import make_engine


@pytest.fixture
def engine(pg_url: str) -> Iterator[Engine]:
    engine = make_engine(pg_url)
    yield engine
    engine.dispose()
