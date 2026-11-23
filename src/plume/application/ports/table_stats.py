from typing import Protocol


class TableStats(Protocol):
    def refresh(self) -> float:
        """Refresh the planner statistics of the knowledge tables after a bulk write (a load or
        a restore); returns the seconds it took. Autoanalyze waits for a share of a table to
        change, so one API's rows (Avalara: 1,176 documents) left the planner estimating 1 row
        and choosing a nested loop: 10 s per search on prod."""
        ...
