"""Gold sets as JSON files: ``<dir>/<api>.json``.

Format::

    {"api": "shopify", "version": "1", "questions": [
      {"id": "q1", "kind": "search", "question": "...", "expect": ["endpoint:GET~/..."]},
      {"id": "q2", "kind": "absent", "name": "loyalty_points"},
      {"id": "q3", "kind": "present", "name": "since_id"}]}
"""

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from plume.application.errors import SourcePackageError
from plume.domain.eval.gold import GoldKind, GoldQuestion, GoldSet


class JsonGoldSource:
    def __init__(self, dirs: Sequence[Path] = ()) -> None:
        self._dirs = list(dirs)

    def for_api(self, api: str) -> str | None:
        for d in self._dirs:
            path = d / f"{api}.json"
            if path.is_file():
                return str(path)
        return None

    def load(self, ref: str) -> tuple[GoldSet, str]:
        path = Path(ref)
        try:
            raw = path.read_bytes()
            data = json.loads(raw)
            questions = tuple(
                GoldQuestion(
                    qid=str(q["id"]),
                    kind=GoldKind(q.get("kind", "search")),
                    question=q.get("question", q.get("name", "")),
                    expect_docs=tuple(q.get("expect", [])),
                    fact_name=q.get("name"),
                )
                for q in data["questions"]
            )
            gold = GoldSet(
                api=data["api"], questions=questions, version=str(data.get("version", "1"))
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise SourcePackageError(f"invalid gold set {ref}: {exc}") from exc
        return gold, "sha256:" + hashlib.sha256(raw).hexdigest()
