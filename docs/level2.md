# Level 2: Claude Code as the client

`tests/live_claude/` runs Claude Code headless (`claude -p`) with this repo's plugin against a
**running** Plume stack and checks invariants from what Plume stored, not from Claude's prose.
It is opt-in and uses Claude usage.

```bash
PLUME_L2_API=http://127.0.0.1:18490 \
PLUME_L2_MCP=http://127.0.0.1:18491/mcp \
PLUME_L2_TOKEN_FILE=/path/to/.maintainer-token \
PLUME_L2_OUT=/path/to/results \
PLUME_L2_BUDGET_USD=2 \
make e2e-live-claude
```

| Variable | Default | |
|---|---|---|
| `PLUME_L2_API` | `http://127.0.0.1:18490` | HTTP API of the stack |
| `PLUME_L2_MCP` | `http://127.0.0.1:18491/mcp` | reader MCP; the maintainer MCP is `<…>/maintainer/mcp` |
| `PLUME_L2_TOKEN_FILE` | – | maintainer token file (model cases skip without it) |
| `PLUME_L2_BUDGET_USD` | `2` | `--max-budget-usd` per prompt |
| `PLUME_L2_MIN_COVERAGE` | `0.3` | minimum mapped/total fields per API in a model |
| `PLUME_L2_MODEL` | Claude Code default | `--model` |
| `PLUME_L2_OUT` | `.` | results file `level2-<time>.json` |

Each run writes a temporary MCP config (mode 600, removed afterwards) with the reader server
`plume` and, with a token, `plume-maintainer`; it passes `--plugin-dir plugin`,
`--strict-mcp-config`, `--allowedTools mcp__plume__* mcp__plume-maintainer__*`,
`--output-format stream-json --verbose` and `--no-session-persistence`.

## Cases and invariants

Canonical models (step 3): "Build a canonical Order model for Shopify and Mirakl", a
Product/Offer model, and an Order model over Shopify + WooCommerce + Mirakl.
- Claude read `get_model_context`; a draft was accepted; when a draft was refused, a later one
  was accepted (Claude fixed it).
- A new snapshot exists (`GET /v1/models` before/after).
- 100% of its citations hold: each quote is re-checked against the cited document of the
  pinned build over HTTP.
- No invented fields: every source path is found by `find-fact` in the pinned build.
- Coverage per API ≥ `PLUME_L2_MIN_COVERAGE`.

Reader questions (step 4): cancelling a fulfilled Shopify order, the Mirakl call that accepts an
offer, a WooCommerce variation `sku`, and a made-up Shopify field.
- Plume tools were used, without tool errors.
- The answer cites a Plume document (a source URL or document id it read).
- If the answer says "not documented", a `find_fact` call on that API returned
  `found:false` with `complete:true`.

The result file lists, per case: PASS/FAIL per check with detail, cost (USD), turns, seconds,
tool calls and the answer text.
