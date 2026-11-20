"""Knowledge topic documents: quotes are evidence, the model-written summary never is, and it
keeps its label wherever it is shown."""

from plume.application.reader.use_cases import _snippet
from plume.domain.knowledge.document import SUMMARY_LABEL, without_summaries

TOPIC = """# Topic: rate limits

## Quotes from the docs (verbatim)

> Usually you will find the range above 200 requests in 10 seconds being blocked for 10 seconds.
>
> Source: https://api.backmarket.dev/bundled_openapi.yaml

## Summary of the quotes above

Requests exceeding standard rates are blocked for 10 seconds with an HTTP 429 response.

## Related

- the catalog endpoints
"""


def test_evidence_never_comes_from_the_summary() -> None:
    quotable = without_summaries(TOPIC)
    assert "above 200 requests in 10 seconds" in quotable
    assert "Requests exceeding standard rates" not in quotable
    assert "## Related" in quotable  # only the summary section goes


def test_a_snippet_from_the_summary_keeps_its_label() -> None:
    chunk = TOPIC[TOPIC.index("## Summary") :]
    assert "Summary of the quotes above" in _snippet(chunk, "429 response")
    long = "## Summary of the quotes above\n\n" + "x " * 200 + "the 429 response is returned."
    snippet = _snippet(long, "429 response")
    assert snippet.startswith(f"[{SUMMARY_LABEL}]")
    quotes = TOPIC[: TOPIC.index("## Summary")]
    assert SUMMARY_LABEL not in _snippet(quotes, "200 requests")
