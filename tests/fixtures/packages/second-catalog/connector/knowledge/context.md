# Second Catalog API (version 1.0.0)

A second shop catalog API (made-up data, local test fixture). Same behaviour as the first one, its own connector for the single-production-environment retest.

## Servers
- http://127.0.0.1:18091

## Authentication
- catalogKey: API key in header "X-Catalog-Key"
  The shop's own API key.

## Error format
Error responses (400, 410) carry:
```json
{ "error": "string", "message": "string" }
```

