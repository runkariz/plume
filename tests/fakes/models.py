from plume.application.ports.model_repo import ModelSession
from plume.domain.models.snapshot import ModelSnapshot


class InMemoryModelRepo:
    def __init__(self) -> None:
        self.sessions: dict[str, ModelSession] = {}
        self.snapshots: dict[str, ModelSnapshot] = {}

    def save_session(self, session: ModelSession) -> None:
        if session.session_id in self.sessions:
            raise ValueError("duplicate session")
        self.sessions[session.session_id] = session

    def get_session(self, session_id: str) -> ModelSession | None:
        return self.sessions.get(session_id)

    def save_snapshot(self, snapshot: ModelSnapshot) -> bool:
        if snapshot.snapshot_id in self.snapshots:
            return False
        self.snapshots[snapshot.snapshot_id] = snapshot
        return True

    def get_snapshot(self, snapshot_id: str) -> ModelSnapshot | None:
        return self.snapshots.get(snapshot_id)

    def list_snapshots(self, api: str | None = None, limit: int = 50) -> list[ModelSnapshot]:
        items = [
            s for s in self.snapshots.values() if api is None or api in {i.api for i in s.inputs}
        ]
        return sorted(items, key=lambda s: (-s.created_at.timestamp(), s.snapshot_id))[:limit]
