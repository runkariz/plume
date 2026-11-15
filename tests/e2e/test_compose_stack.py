"""Runs against `docker compose up` (Postgres on 127.0.0.1:18432). Started by `make e2e`."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from plume.infrastructure.db.engine import make_engine
from plume.infrastructure.settings import Settings

pytestmark = pytest.mark.e2e


def test_compose_postgres_is_up_with_pgvector() -> None:
    engine = make_engine(Settings().sqlalchemy_url)
    try:
        with engine.begin() as conn:
            assert conn.execute(text("SELECT 1")).scalar_one() == 1
            available = conn.execute(
                text("SELECT count(*) FROM pg_available_extensions WHERE name = 'vector'")
            ).scalar_one()
        assert available == 1
    finally:
        engine.dispose()


def test_cli_migrate_against_compose() -> None:
    plume = Path(sys.executable).parent / "plume"
    first = subprocess.run(
        [str(plume), "migrate"], capture_output=True, text=True, check=False, env=os.environ.copy()
    )
    assert first.returncode == 0, first.stderr
    second = subprocess.run([str(plume), "migrate"], capture_output=True, text=True, check=False)
    assert second.returncode == 0, second.stderr
    assert "up to date: 0001" in second.stdout
