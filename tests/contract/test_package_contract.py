"""The input-package contract Plume reads (connector/package.json schemaVersion 1.x).

Runs over the fixture packages, plus any package directories listed in
PLUME_CONTRACT_PACKAGES (os.pathsep-separated), e.g. a new stream output to check before use.
See docs/package-contract.md for what is read and what is ignored.
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from plume.infrastructure.sources.stream_package import StreamPackageSource

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "packages"
EXTRA = [Path(p) for p in os.environ.get("PLUME_CONTRACT_PACKAGES", "").split(os.pathsep) if p]
PACKAGES = sorted(p for p in FIXTURES.iterdir() if p.is_dir()) + EXTRA

OPTIONAL_TYPES: dict[str, type | tuple[type, ...]] = {
    "description": str,
    "summary": str,
    "resource": str,
    "operationKind": str,
    "sideEffects": list,
    "isDeprecated": bool,
    "permissionNote": str,
    "requiredScopes": list,
    "errors": list,
    "pagination": dict,
    "businessRules": list,
    "responses": list,
    "provenance": dict,
    "docLink": str,
    "paramsContractRef": str,
    "variablesContractRef": str,
    "headersContractRef": str,
    "bodyContractRef": str,
}


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _connector(pkg: Path) -> Path:
    return pkg if (pkg / "app.json").is_file() else pkg / "connector"


@pytest.fixture(params=PACKAGES, ids=lambda p: p.name)
def connector(request: pytest.FixtureRequest) -> Path:
    return _connector(request.param)


def test_schema_version_is_1x(connector: Path) -> None:
    version = _json(connector / "package.json")["schemaVersion"]
    assert str(version).split(".")[0] == "1", version


def test_app_json_fields(connector: Path) -> None:
    app = _json(connector / "app.json")
    assert isinstance(app["name"], str)
    assert app["name"].strip()
    if "category" in app:
        assert isinstance(app["category"]["key"], str)
    if "apiVersioning" in app:
        assert isinstance(app["apiVersioning"].get("versions", []), list)


def test_endpoint_request_fields(connector: Path) -> None:
    requests = sorted((connector / "endpoints").glob("*/request.json"))
    assert requests
    for path in requests:
        req = _json(path)
        for key in ("method", "url", "name", "endpointId"):
            assert isinstance(req.get(key), str), f"{path.parent.name}: {key}"
        for key, typ in OPTIONAL_TYPES.items():
            if req.get(key) is not None:
                assert isinstance(req[key], typ), f"{path.parent.name}: {key}"
        for ref_key in ("paramsContractRef", "variablesContractRef", "bodyContractRef"):
            if req.get(ref_key):
                assert (path.parent / req[ref_key]).is_file(), f"{path.parent.name}: {ref_key}"
        for scope in req.get("requiredScopes") or []:
            assert isinstance(scope.get("scopes"), list)


def test_models_and_knowledge(connector: Path) -> None:
    for path in sorted((connector / "models").glob("*.schema.json")):
        model = _json(path)
        assert isinstance(model.get("properties", {}), dict), path.name
        assert model.get("x-complete", True) in (True, False), path.name
    for path in sorted((connector / "knowledge").glob("*.json")):
        meta = _json(path)
        assert isinstance(meta.get("title", ""), str)
        assert path.with_suffix(".md").is_file(), f"{path.name} has no .md body"


def test_reader_reads_every_endpoint(connector: Path) -> None:
    pkg = StreamPackageSource().load(str(connector))
    endpoints = [d for d in pkg.documents if d.kind.value == "endpoint"]
    assert len(endpoints) == len(list((connector / "endpoints").glob("*/request.json")))
    # Unresolved include tags are a content gap in the package (flagged on the document, reported
    # to the producer), not a reading failure; every other warning fails the contract.
    assert [w for w in pkg.warnings if "unresolved include" not in w] == []
