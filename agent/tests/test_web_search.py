import pytest

from tools import duckduckgo_search_url


def test_duckduckgo_search_url_encodes_query() -> None:
    assert (
        duckduckgo_search_url("  current weather in New York  ")
        == "https://duckduckgo.com/?q=current+weather+in+New+York"
    )


def test_duckduckgo_search_url_rejects_empty_query() -> None:
    with pytest.raises(ValueError, match="query cannot be empty"):
        duckduckgo_search_url("  ")


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("trip.com", "https://trip.com"),
        ("www.google.com/maps", "https://www.google.com/maps"),
        ("https://example.com", "https://example.com"),
        ("http://localhost:3000", "http://localhost:3000"),
    ],
)
def test_bare_domains_get_https(given: str, expected: str) -> None:
    from tools import normalize_url

    assert normalize_url(given) == expected


@pytest.mark.parametrize("given", ["javascript:alert(1)", "file:///etc/passwd", "not a url"])
def test_non_web_addresses_are_left_for_validation(given: str) -> None:
    from tools import normalize_url

    assert normalize_url(given) == given.strip()
