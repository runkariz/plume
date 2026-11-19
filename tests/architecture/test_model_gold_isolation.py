"""Model gold is for scoring only: the generator's prompts, context and examples are never built
from it, so no module that writes or prepares a model may import gold (held-out scores stay
meaningful)."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "plume"
GENERATOR = [
    "application/models/generate.py",
    "application/models/sessions.py",
    "application/models/model_sets.py",
    "application/models/concepts.py",
    "application/models/relations.py",
    "infrastructure/llm",
]
GOLD = (
    "plume.domain.models.model_gold",
    "plume.domain.models.model_eval",
    "plume.application.models.model_eval",
    "plume.application.ports.model_gold",
    "plume.infrastructure.models",
)


def _imports(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def test_the_generator_never_imports_model_gold() -> None:
    files = [
        f
        for entry in GENERATOR
        for f in ((SRC / entry).rglob("*.py") if (SRC / entry).is_dir() else [SRC / entry])
    ]
    assert len(files) >= len(GENERATOR)
    leaks = {
        str(f.relative_to(SRC)): sorted(m for m in _imports(f) if m.startswith(GOLD)) for f in files
    }
    assert {f: m for f, m in leaks.items() if m} == {}
