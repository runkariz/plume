"""Layer rules: import-linter contracts (.importlinter) plus a stdlib-only check on the domain."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "plume"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def test_import_linter_contracts_hold() -> None:
    lint_imports = Path(sys.executable).parent / "lint-imports"
    result = subprocess.run(
        [str(lint_imports), "--config", str(ROOT / ".importlinter"), "--no-cache"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 broken" in result.stdout


@pytest.mark.parametrize(
    "path", sorted((SRC / "domain").rglob("*.py")), ids=lambda p: str(p.relative_to(SRC))
)
def test_domain_imports_only_stdlib_and_itself(path: Path) -> None:
    for module in _imports(path):
        top = module.split(".")[0]
        assert top in sys.stdlib_module_names or module.startswith("plume.domain"), (
            f"{path.relative_to(SRC)} imports {module}"
        )


@pytest.mark.parametrize(
    "path", sorted((SRC / "application").rglob("*.py")), ids=lambda p: str(p.relative_to(SRC))
)
def test_application_imports_only_stdlib_domain_and_itself(path: Path) -> None:
    for module in _imports(path):
        top = module.split(".")[0]
        assert (
            top in sys.stdlib_module_names
            or module.startswith("plume.domain")
            or module.startswith("plume.application")
        ), f"{path.relative_to(SRC)} imports {module}"


def test_only_settings_reads_the_environment() -> None:
    offenders = []
    for path in SRC.rglob("*.py"):
        if path == SRC / "infrastructure" / "settings.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "os.environ" in text or "os.getenv" in text or "getenv(" in text:
            offenders.append(str(path.relative_to(SRC)))
    assert offenders == []
