# Reported questions

When Plume does not give a reader's LLM what it needs, the LLM can report the question. Only
what it sends to these tools is stored: never the chat, never any other tool call. Off by
default: `PLUME_REPORTS=on` (on in dev; in prod only after the owner's go and a privacy notice).

## MCP tools (reader server, only when on)

| Tool | What it does |
|---|---|
| `find_reported_questions(api, question)` | Up to 5 similar reports for the API: id, redacted question, status (with the reason when answered / out-of-scope), report and note counts. |
| `report_question(api, question, what_was_tried?, what_was_missing?)` | A new report, or, when a report with the same words or very similar meaning exists, a note on it (`merged: true`, and the message says so). |
| `add_to_report(id, note)` | A note on a report; its report count goes up. |

The server instructions (rule 8) and the tool descriptions say when to use them and to write
the question in general terms with no user data. `search_docs` with no results,
`find_fact` with `found: false` and `check_call` with `not_documented` carry a `report_hint`.

## Privacy

- **Redaction before storage** of question, what_was_tried, what_was_missing, note and the
  client name (`src/plume/domain/reports/redact.py`):
  - URLs lose their query string;
  - tokens, keys, JWTs, secret key=value pairs, emails, account numbers, IP addresses and long
    digit runs are replaced by markers.
  - Owner choices (switchable): 7–8 digit error codes after "error" / "code" / "errorCode" are
    kept (`PLUME_REPORTS_KEEP_ERROR_CODES`), and so is the RPC `method=` value
    (`PLUME_REPORTS_KEEP_RPC_METHOD`).
- **Unsafe text:** a question the rules cannot make safe (something secret-looking survives,
  or it is mostly markers) is refused with a request to rephrase; other fields are left out.
- **Stored with each report:** API, build, time, client name, a keyed hash of the MCP session
  id (`PLUME_REPORTS_SALT`) and the redaction count. No IP address, no identity.
- **Limits:** 1,000 characters per field; `PLUME_REPORTS_PER_HOUR` (10) reports and notes per
  session per hour. Over a limit the call is refused politely.
- **Retention:** open reports with no activity for `PLUME_REPORTS_RETENTION_DAYS` (90) are
  purged (lazily, once a day, and by `plume reports purge`). Triaged reports stay.
- **Near-duplicates:** the same words, or cosine similarity of the question embeddings (the
  search embedder) of at least `PLUME_REPORTS_DUPLICATE_SIMILARITY` (0.92).

## Maintainers

- HTTP (bearer maintainer token):
  - `GET /v1/maintainer/reports?api=&status=`: most reported first;
  - `GET /v1/maintainer/reports/{id}`: with its notes;
  - `PATCH /v1/maintainer/reports/{id}` with `{"status": "answered|search-miss|package-gap|out-of-scope|open", "reason": "..."}`.
- CLI:
  - `plume reports export [--api] [--status] [--since YYYY-MM-DD] [--notes/--no-notes] [--out]` (JSON lines);
  - `plume reports set-status <id> <status> [--reason]`;
  - `plume reports purge [--older-than DAYS]`.
