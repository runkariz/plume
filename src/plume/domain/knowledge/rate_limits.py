"""Per-operation rate limits (Core's contract): app.json ``rateLimits[]`` groups
``{scope, group, limit, windowSeconds, algorithm, notes}`` and request.json ``rateLimitCost``
``{bucket, cost}`` (bucket = a group). Values are kept verbatim; packages without them are fine."""

import json
from collections.abc import Mapping
from typing import Any


def groups(app: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    raw = (app or {}).get("rateLimits")
    return [g for g in raw if isinstance(g, dict)] if isinstance(raw, list) else []


def resolve(request: Mapping[str, Any], app_groups: list[dict[str, Any]]) -> str | None:
    """An endpoint's rate limit as JSON text: its bucket and cost, and its group (verbatim)."""
    cost = request.get("rateLimitCost")
    if not isinstance(cost, dict):
        return None
    bucket = cost.get("bucket")
    group = next((g for g in app_groups if bucket is not None and g.get("group") == bucket), None)
    value = {"bucket": bucket, "cost": cost.get("cost"), "group": group}
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def as_dict(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    value = json.loads(text)
    return value if isinstance(value, dict) else None


def describe(text: str | None) -> str:
    """ "bucket getPurchaseOrders, cost 1; 10 per 1 s (token-bucket); <notes>"."""
    rl = as_dict(text)
    if rl is None:
        return ""
    bits = [f"bucket {rl.get('bucket')}", f"cost {rl.get('cost')}"]
    g = rl.get("group") or {}
    if g.get("limit") is not None:
        rate = f"{g['limit']} per {g.get('windowSeconds', '?')} s"
        bits.append(rate + (f" ({g['algorithm']})" if g.get("algorithm") else ""))
    out = ", ".join(bits[:2]) + ("; " + bits[2] if len(bits) > 2 else "")
    if g.get("notes"):
        out += f"; {g['notes']}"
    return out


def rate(group: Mapping[str, Any]) -> float | None:
    """Requests per second a group allows (None when it states no limit/window)."""
    limit, window = group.get("limit"), group.get("windowSeconds")
    if isinstance(limit, int | float) and isinstance(window, int | float) and window > 0:
        return float(limit) / float(window)
    return None
