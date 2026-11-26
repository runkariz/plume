"""The API card's projection of the latest notes exists three times: card_of (on save),
CARD_SQL (rows without a stored card) and migration 0022's frozen backfill. They must agree."""

import importlib.util
from pathlib import Path

from plume.infrastructure.db.repos.release_notes_repo import CARD_ITEM_KEYS, CARD_SQL, card_of

MIGRATION = (
    Path(__file__).parents[3]
    / "src/plume/infrastructure/db/migrations/versions/0022_release_notes_card.py"
)


def test_the_sql_copies_and_the_python_keys_agree() -> None:
    spec = importlib.util.spec_from_file_location("m0022", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.CARD == CARD_SQL
    assert [k for k in CARD_ITEM_KEYS if f"'{k}', i->'{k}'" not in CARD_SQL] == []


def test_card_of_keeps_the_visible_items_five_keys() -> None:
    notes = {"api": "a", "to": "b2", "toDocsAsOf": "2026-11-27", "review": "kept", "items": [
        {"visibleToUsers": True, "class": "confirmed", "breaking": True, "quote": "x" * 999},
        {"visibleToUsers": False, "class": "likely"},
    ]}  # fmt: skip
    assert card_of(notes) == {"api": "a", "to": "b2", "toDocsAsOf": "2026-11-27", "items": [
        {"visibleToUsers": True, "class": "confirmed", "breaking": True, "wordingOnly": None,
         "kind": None}]}  # fmt: skip
