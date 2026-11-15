# Test Catalog API (version 1.0.0)

A small shop catalog API (made-up data, local test fixture). Every shop has its own API key and only ever sees its own products and orders. Lists are paged with a cursor token and can be searched.

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

