"""Level 2 harness: run Claude Code headless against a running Plume stack and check invariants.

Claude's text varies; the invariants are checked against what Plume stored and what the MCP
tools returned, never against wording alone.
"""

import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugin"
NOT_DOCUMENTED = ("not documented", "isn't documented", "is not documented", "no documented")
NOT_DOCUMENTED_CHECK = "'not documented' backed by find_fact (complete, or hedged when not)"
HEDGES = (
    "not exhaustive",
    "incomplete",
    "partial",
    "may exist",
    "might exist",
    "not proven",
    "can't confirm",
    "cannot confirm",
    "couldn't confirm",
    "could not confirm",
    "not be complete",
    "not complete",
)


@dataclass(frozen=True)
class Stack:
    api: str  # http://127.0.0.1:18490
    mcp: str  # http://127.0.0.1:18491/mcp
    maintainer_mcp: str  # http://127.0.0.1:18491/maintainer/mcp
    token_file: Path | None

    @classmethod
    def from_env(cls) -> "Stack":
        api = os.environ.get("PLUME_L2_API", "http://127.0.0.1:18490").rstrip("/")
        mcp = os.environ.get("PLUME_L2_MCP", "http://127.0.0.1:18491/mcp")
        token = os.environ.get("PLUME_L2_TOKEN_FILE")
        return cls(
            api=api,
            mcp=mcp,
            maintainer_mcp=mcp.replace("/mcp", "/maintainer/mcp"),
            token_file=Path(token) if token else None,
        )


@dataclass
class ToolCall:
    name: str
    input: dict[str, Any]
    result: Any = None
    is_error: bool = False


@dataclass
class Run:
    prompt: str
    exit_code: int
    text: str
    calls: list[ToolCall] = field(default_factory=list)
    cost_usd: float | None = None
    turns: int | None = None
    seconds: float = 0.0
    stderr: str = ""

    def tool(self, suffix: str) -> list[ToolCall]:
        return [c for c in self.calls if c.name.endswith("__" + suffix)]


def _structured(content: Any) -> Any:
    """A tool_result's content -> the JSON object the tool returned (when it is JSON)."""
    if isinstance(content, list):
        texts = [c.get("text", "") for c in content if isinstance(c, dict)]
        content = "".join(texts)
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content
    return content


def parse_stream(lines: list[str], prompt: str = "", exit_code: int = 0) -> Run:
    """Parse ``claude -p --output-format stream-json --verbose`` output."""
    run = Run(prompt=prompt, exit_code=exit_code, text="")
    pending: dict[str, ToolCall] = {}
    for raw in lines:
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = msg.get("type")
        content = (msg.get("message") or {}).get("content") or []
        if kind == "assistant":
            for part in content:
                if part.get("type") == "tool_use":
                    call = ToolCall(part.get("name", ""), part.get("input") or {})
                    pending[part.get("id", "")] = call
                    run.calls.append(call)
        elif kind == "user":
            for part in content if isinstance(content, list) else []:
                if part.get("type") == "tool_result" and part.get("tool_use_id") in pending:
                    call = pending[part["tool_use_id"]]
                    call.result = _structured(part.get("content"))
                    call.is_error = bool(part.get("is_error"))
        elif kind == "result":
            run.text = msg.get("result") or ""
            run.cost_usd = msg.get("total_cost_usd")
            run.turns = msg.get("num_turns")
    return run


@contextmanager
def mcp_config(stack: Stack) -> Iterator[Path]:
    """A temporary MCP config (mode 600, deleted afterwards): reader + maintainer servers."""
    servers: dict[str, Any] = {"plume": {"type": "http", "url": stack.mcp}}
    if stack.token_file is not None:
        token = stack.token_file.read_text(encoding="utf-8").strip()
        servers["plume-maintainer"] = {
            "type": "http",
            "url": stack.maintainer_mcp,
            "headers": {"Authorization": f"Bearer {token}"},
        }
    tmp = Path(tempfile.mkdtemp(prefix="plume-l2-"))
    path = tmp / "mcp.json"
    try:
        path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        yield path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_claude(stack: Stack, prompt: str, budget_usd: float, timeout: int = 900) -> Run:
    claude = shutil.which("claude")
    if claude is None:
        raise RuntimeError("the claude CLI is not on PATH")
    with mcp_config(stack) as cfg:
        cmd = [
            claude,
            "-p",
            prompt,
            "--plugin-dir",
            str(PLUGIN),
            "--mcp-config",
            str(cfg),
            "--strict-mcp-config",
            "--allowedTools",
            "mcp__plume__*",
            "mcp__plume-maintainer__*",
            "--output-format",
            "stream-json",
            "--verbose",
            "--max-budget-usd",
            str(budget_usd),
            "--no-session-persistence",
        ]
        model = os.environ.get("PLUME_L2_MODEL")
        if model:
            cmd += ["--model", model]
        start = time.monotonic()
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False, cwd=ROOT
        )
    run = parse_stream(proc.stdout.splitlines(), prompt, proc.returncode)
    run.seconds = round(time.monotonic() - start, 1)
    run.stderr = proc.stderr[-2000:]
    return run


# -- invariants (checked against Plume, not Claude's prose) -------------------------------------


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


def _norm(value: str) -> str:
    return " ".join(value.replace("`", "").split()).lower()


def _quote_in(quote: str, text: str) -> bool:
    return _norm(quote) in _norm(text)


def check_model(stack: Stack, run: Run, before: set[str], min_coverage: float) -> list[Check]:
    checks: list[Check] = []
    submits = run.tool("submit_model_draft")
    accepted = [c for c in submits if isinstance(c.result, dict) and c.result.get("accepted")]
    refused = [
        c for c in submits if isinstance(c.result, dict) and c.result.get("accepted") is False
    ]
    checks.append(Check("used get_model_context", bool(run.tool("get_model_context"))))
    checks.append(Check("a draft was accepted", bool(accepted), f"{len(submits)} submit(s)"))
    if refused:
        checks.append(
            Check(
                "refusals were fixed",
                bool(accepted) and submits.index(accepted[-1]) > submits.index(refused[0]),
                "; ".join(i["code"] for c in refused for i in c.result.get("issues", []))[:300],
            )
        )
    with httpx.Client(base_url=stack.api, timeout=30) as http:
        after = {m["id"] for m in http.get("/v1/models", params={"limit": 200}).json()["items"]}
        new = sorted(after - before)
        checks.append(Check("a snapshot was stored", bool(new), ", ".join(new)))
        for sid in new:
            model = http.get(f"/v1/models/{sid}").json()
            checked = found = 0
            invented: list[str] = []
            missing: list[str] = []
            for f in model["fields"]:
                for api, src in f["sources"].items():
                    for p in src["paths"]:
                        r = http.post(
                            f"/v1/apis/{api}/find-fact",
                            json={
                                "name": p["path"],
                                "kind": "field",
                                "version": _build(model, api),
                            },
                        ).json()
                        if not r.get("found"):
                            invented.append(f"{api}:{p['path']}")
                    for e in src["evidence"]:
                        checked += 1
                        doc = http.get(
                            f"/v1/apis/{api}/documents/{e['docId']}",
                            params={"version": _build(model, api)},
                        )
                        body = doc.json() if doc.status_code == 200 else {}
                        text = " ".join(
                            [body.get("title", ""), body.get("text", "")]
                            + [x.get("description") or "" for x in body.get("fields", [])]
                        )
                        if doc.status_code == 200 and _quote_in(e["quote"], text):
                            found += 1
                        else:
                            missing.append(f"{api}:{e['docId']}")
            checks.append(
                Check(
                    f"{sid}: 100% of citations hold",
                    checked > 0 and found == checked,
                    f"{found}/{checked} {missing[:5]}",
                )
            )
            checks.append(
                Check(f"{sid}: no invented fields", not invented, ", ".join(invented[:10]))
            )
            for api, cov in model["coverage"].items():
                ratio = cov["mapped"] / cov["total"] if cov["total"] else 0.0
                checks.append(
                    Check(
                        f"{sid}: coverage {api} >= {min_coverage}",
                        ratio >= min_coverage,
                        f"{cov['mapped']}/{cov['total']}",
                    )
                )
    return checks


def _build(model: dict[str, Any], api: str) -> str | None:
    return next((i["build"] for i in model["inputs"] if i["id"] == api), None)


def check_reader(run: Run, api: str) -> list[Check]:
    plume_calls = [c for c in run.calls if c.name.startswith("mcp__plume__")]
    text = run.text.lower()
    checks = [
        Check(
            "used Plume tools", bool(plume_calls), ", ".join(sorted({c.name for c in plume_calls}))
        ),
        Check("no tool errors", not any(c.is_error for c in plume_calls)),
    ]
    sources = {
        str(c.result.get("source_url") or "")
        for c in run.tool("get_document")
        if isinstance(c.result, dict)
    } | {
        str(r.get("source_url") or "")
        for c in run.tool("search_docs")
        if isinstance(c.result, dict)
        for r in c.result.get("results", [])
    }
    cited = any(s and s.lower() in text for s in sources) or "doc_id" in text or "endpoint:" in text
    checks.append(Check("the answer cites Plume documents", cited, f"{len(sources)} sources seen"))
    if any(p in text for p in NOT_DOCUMENTED):
        absent = [
            c.result
            for c in run.tool("find_fact")
            if isinstance(c.result, dict)
            and c.result.get("found") is False
            and c.input.get("api") == api
        ]
        proven = any(r.get("complete") is True for r in absent)
        hedged = any(r.get("complete") is False for r in absent) and any(h in text for h in HEDGES)
        checks.append(
            Check(
                NOT_DOCUMENTED_CHECK,
                proven or hedged,
                "complete" if proven else "hedged" if hedged else "no matching find_fact",
            )
        )
    return checks
