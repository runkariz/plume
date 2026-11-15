"""Level 2, steps 3-4 (e2e-test-plan.md): Claude Code as the real client of a running stack.

Opt-in and billed (Claude usage): `make e2e-live-claude` with PLUME_L2_RUN=1. Settings:
PLUME_L2_API, PLUME_L2_MCP, PLUME_L2_TOKEN_FILE (maintainer token file), PLUME_L2_BUDGET_USD
(per prompt, default 2), PLUME_L2_MIN_COVERAGE (default 0.3), PLUME_L2_OUT (results dir),
PLUME_L2_MODEL. Results (PASS/FAIL per invariant, cost, turns, tool calls) go to
PLUME_L2_OUT/level2-<time>.json.
"""

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.live_claude.harness import Check, Run, Stack, check_model, check_reader, run_claude

pytestmark = pytest.mark.claude_live

MODEL_PROMPTS = [
    (
        "order-shopify-mirakl",
        ["shopify", "mirakl"],
        "Build a canonical Order model for Shopify and Mirakl with Plume, and save it.",
    ),
    (
        "product-offer-shopify-mirakl",
        ["shopify", "mirakl"],
        "Build a canonical Product/Offer model for Shopify and Mirakl with Plume, and save it.",
    ),
    (
        "order-three-apis",
        ["shopify", "woocommerce", "mirakl"],
        "Build a canonical Order model for Shopify, WooCommerce and Mirakl with Plume; save it.",
    ),
]
READER_PROMPTS = [
    (
        "cancel-fulfilled-order",
        "shopify",
        "Using Plume: can I cancel a fulfilled order in Shopify? Cite the docs.",
    ),
    (
        "mirakl-accept-offer",
        "mirakl",
        "Using Plume: which Mirakl API call accepts an offer (or an order line)? Cite the docs.",
    ),
    (
        "woo-variation-sku",
        "woocommerce",
        "Using Plume: is there a sku field on WooCommerce product variations? Cite the docs.",
    ),
    (
        "shopify-loyalty",
        "shopify",
        "Using Plume: does the Shopify Admin REST customer resource document a loyalty_points "
        "field? Answer precisely and cite.",
    ),
]
RESULTS: list[dict[str, Any]] = []


@pytest.fixture(scope="module")
def stack() -> Stack:
    if os.environ.get("PLUME_L2_RUN") != "1":
        pytest.skip("Level 2 Claude runs are opt-in: PLUME_L2_RUN=1 (uses Claude usage)")
    s = Stack.from_env()
    try:
        httpx.get(f"{s.api}/health", timeout=5).raise_for_status()
    except httpx.HTTPError as exc:
        pytest.skip(f"no Plume stack at {s.api}: {exc}")
    return s


def _budget() -> float:
    return float(os.environ.get("PLUME_L2_BUDGET_USD", "2"))


def _record(case: str, run: Run, checks: list[Check]) -> None:
    RESULTS.append(
        {
            "case": case,
            "prompt": run.prompt,
            "exit_code": run.exit_code,
            "passed": all(c.passed for c in checks),
            "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks],
            "cost_usd": run.cost_usd,
            "turns": run.turns,
            "seconds": run.seconds,
            "tools": [c.name for c in run.calls],
            "answer": run.text[:4000],
        }
    )
    out = Path(os.environ.get("PLUME_L2_OUT", "."))
    out.mkdir(parents=True, exist_ok=True)
    stamp = os.environ.setdefault("PLUME_L2_STAMP", time.strftime("%Y%m%d-%H%M%S"))
    (out / f"level2-{stamp}.json").write_text(json.dumps(RESULTS, indent=2), encoding="utf-8")


def _fail_message(checks: list[Check]) -> str:
    return "; ".join(f"{c.name}: {c.detail}" for c in checks if not c.passed)


@pytest.mark.parametrize(
    ("case", "apis", "prompt"), MODEL_PROMPTS, ids=[m[0] for m in MODEL_PROMPTS]
)
def test_canonical_model(stack: Stack, case: str, apis: list[str], prompt: str) -> None:
    if stack.token_file is None:
        pytest.skip("PLUME_L2_TOKEN_FILE is needed for the maintainer MCP")
    with httpx.Client(base_url=stack.api, timeout=30) as http:
        before = {m["id"] for m in http.get("/v1/models", params={"limit": 200}).json()["items"]}
    run = run_claude(stack, prompt, _budget())
    min_cov = float(os.environ.get("PLUME_L2_MIN_COVERAGE", "0.3"))
    checks = check_model(stack, run, before, min_cov)
    _record(case, run, checks)
    assert all(c.passed for c in checks), _fail_message(checks)


@pytest.mark.parametrize(
    ("case", "api", "prompt"), READER_PROMPTS, ids=[r[0] for r in READER_PROMPTS]
)
def test_reader_question(stack: Stack, case: str, api: str, prompt: str) -> None:
    run = run_claude(stack, prompt, _budget())
    checks = check_reader(run, api)
    _record(case, run, checks)
    assert all(c.passed for c in checks), _fail_message(checks)
