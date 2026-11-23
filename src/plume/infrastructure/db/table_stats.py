import logging
import time

from sqlalchemy import Engine, text

logger = logging.getLogger(__name__)
TABLES = ("documents", "chunks", "facts", "build_items")


class PostgresTableStats:
    """ANALYZE of the tables a load or a restore fills: sample-based, reads only, no lock that
    blocks reads or writes."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def refresh(self) -> float:
        start = time.monotonic()
        with self._engine.begin() as conn:
            conn.execute(text(f"ANALYZE {', '.join(TABLES)}"))
        took = time.monotonic() - start
        logger.info("analyzed %s in %.2f s", ", ".join(TABLES), took)
        return took
