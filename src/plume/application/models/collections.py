"""The "My models" link: a collection lists lineages of a user's models and sets. No accounts:
the link is the identity, and it only lists (anyone with a model's link can already read it).
See docs/design/my-models-link.md."""

import hashlib
import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from plume.application.errors import NotFoundError
from plume.application.models.concepts import ModelInputError
from plume.application.ports.collection_repo import KIND_MODEL, KIND_SET, CollectionRepo

__all__ = ["KIND_MODEL", "KIND_SET", "CollectionRef", "Collections", "owner_key_hash"]
from plume.application.ports.model_repo import ModelRepo
from plume.application.ports.model_set_repo import ModelSetRepo
from plume.domain.models.model_set import ModelSetSnapshot
from plume.domain.models.snapshot import ModelSnapshot, Visibility
from plume.domain.shared.clock import Clock

MAX_COLLECTION_ITEMS = 500
MAX_MERGE_SOURCES = 20


def owner_key_hash(key: str) -> str:
    """Old per-model owner keys are kept only as this hash (transition to collections)."""
    return hashlib.sha256(key.strip().encode()).hexdigest()


def new_collection_id() -> str:
    """128 random bits: whoever has the id can see the list."""
    return "c-" + secrets.token_urlsafe(16)


@dataclass(frozen=True, slots=True)
class CollectionRef:
    collection_id: str
    created: bool
    note: str | None = None


@dataclass(frozen=True, slots=True)
class CollectionContent:
    collection_id: str
    merged_into: str | None
    models: list[ModelSnapshot]
    sets: list[ModelSetSnapshot]
    # listed id -> the lineage's newest version when it is newer than the one saved into this
    # collection (someone else with the model's link added it): "a newer version exists"
    newer: dict[str, ModelSnapshot | ModelSetSnapshot] = field(default_factory=dict)


DISCARDED = Visibility.DISCARDED


def _own[T](versions: list[T], saved: str | None, id_of: Callable[[T], str]) -> T | None:
    """The version saved into the collection (the lineage's latest when none is recorded:
    items from old owner keys)."""
    if not versions:
        return None
    if saved:
        for v in versions:
            if id_of(v) == saved:
                return v
    return versions[-1]


class Collections:
    def __init__(
        self, repo: CollectionRepo, models: ModelRepo, sets: ModelSetRepo, clock: Clock
    ) -> None:
        self._repo = repo
        self._models = models
        self._sets = sets
        self._clock = clock

    def _create(self, note: str | None = None) -> CollectionRef:
        cid = new_collection_id()
        self._repo.create(cid, self._clock.now())
        return CollectionRef(cid, True, note)

    def ensure(self, collection_id: str | None) -> CollectionRef:
        """The collection to save into: the given one (following a merge), or a new one."""
        wanted = (collection_id or "").strip()
        if not wanted:
            return self._create()
        c = self._repo.get(wanted)
        if c is not None and c.merged_into:
            c = self._repo.get(c.merged_into) or c
        if c is None:
            return self._create(f"{wanted[:40]} is not a My models link here; a new one was made")
        return CollectionRef(c.collection_id, False)

    def save(
        self,
        collection_id: str | None,
        kind: str,
        lineage_id: str,
        version_id: str | None = None,
    ) -> CollectionRef:
        """Put a lineage in the caller's collection, or in a new one. Never answer with a
        collection the caller did not send: a lineage may already sit in its author's link,
        and anyone with a model's link may add a version (that must not reveal the author's
        list). A retry without the link therefore gets a new link too."""
        ref = self.ensure(collection_id)
        items = self._repo.items(ref.collection_id)
        held = {(k, lin) for k, lin, _ in items}
        if (kind, lineage_id) not in held and len(items) >= MAX_COLLECTION_ITEMS:
            raise ModelInputError(
                f"this My models link holds {MAX_COLLECTION_ITEMS} models and sets already; "
                "save without it to start a new one"
            )
        self._repo.add(ref.collection_id, kind, lineage_id, self._clock.now(), version_id)
        return ref

    def content(self, collection_id: str) -> CollectionContent:
        c = self._repo.get(collection_id.strip())
        if c is None:
            raise NotFoundError(f"My models link {collection_id[:40]} not found")
        models: list[ModelSnapshot] = []
        sets: list[ModelSetSnapshot] = []
        newer: dict[str, ModelSnapshot | ModelSetSnapshot] = {}
        for kind, lineage_id, saved in self._repo.items(c.collection_id):
            if kind == KIND_MODEL:
                mv = [s for s in self._models.lineage(lineage_id) if s.visibility != DISCARDED]
                own_model = _own(mv, saved, lambda s: s.snapshot_id)
                if own_model is not None:
                    models.append(own_model)
                    if mv[-1].version > own_model.version:
                        newer[own_model.snapshot_id] = mv[-1]
            elif kind == KIND_SET:
                sv = [s for s in self._sets.lineage(lineage_id) if s.visibility != DISCARDED]
                own_set = _own(sv, saved, lambda s: s.set_id)
                if own_set is not None:
                    sets.append(own_set)
                    if sv[-1].version > own_set.version:
                        newer[own_set.set_id] = sv[-1]
        models.sort(key=lambda s: s.created_at, reverse=True)
        sets.sort(key=lambda s: s.created_at, reverse=True)
        return CollectionContent(c.collection_id, c.merged_into, models, sets, newer)

    def merge(self, into: str, sources: Sequence[str]) -> CollectionContent:
        """Move every lineage of ``sources`` into ``into``; the sources then point to it."""
        target = self._repo.get(into.strip())
        if target is None:
            raise NotFoundError(f"My models link {into[:40]} not found")
        wanted = [s.strip() for s in dict.fromkeys(sources) if s.strip() and s.strip() != into]
        if not wanted:
            raise ModelInputError("name at least one other My models link to merge")
        if len(wanted) > MAX_MERGE_SOURCES:
            raise ModelInputError(f"at most {MAX_MERGE_SOURCES} links per merge")
        found = [self._repo.get(s) for s in wanted]
        missing = [s for s, c in zip(wanted, found, strict=True) if c is None]
        if missing:
            raise NotFoundError(f"My models link(s) not found: {', '.join(missing)}")
        incoming = {(k, lin) for s in wanted for k, lin, _ in self._repo.items(s)}
        total = len({(k, lin) for k, lin, _ in self._repo.items(target.collection_id)} | incoming)
        if total > MAX_COLLECTION_ITEMS:
            raise ModelInputError(
                f"the merged link would hold {total} models and sets (at most "
                f"{MAX_COLLECTION_ITEMS})"
            )
        now = self._clock.now()
        for s in wanted:
            self._repo.merge(target.collection_id, s, now)
        return self.content(target.collection_id)

    def for_owner_keys(self, owner_keys: Sequence[str]) -> list[str]:
        """Collections migrated from these old owner keys (transition)."""
        keys = [k for k in dict.fromkeys(owner_keys) if isinstance(k, str) and k.strip()]
        return self._repo.for_legacy_keys([owner_key_hash(k) for k in keys])
