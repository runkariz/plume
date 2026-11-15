## REST Admin API Request Rate Limits

- Requests are limited to 40 requests per app per store per minute, replenishing at 2 requests per second.
- Shopify Plus stores receive a 10x increase to the rate limit (400 requests per minute).
- Responses include the 'X-Shopify-Shop-Api-Call-Limit' header showing current request count versus total allowed (e.g., 40/40).
- Exceeding the rate limit returns a 429 Too Many Requests status code with a 'Retry-After' header indicating the number of seconds to wait before retrying.

> Source: https://shopify.dev/docs/api/admin-rest
