from platform.web.search import SearchResult, WebSearchClient


def test_build_url_injects_encoded_query_and_results_limit() -> None:
    client = WebSearchClient("http://search.example.com/search?q=<query>&format=json")
    url = client.build_url('fatal: keycloak "redirect_uri"', max_results=3)
    assert "q=fatal%3A%20keycloak%20%22redirect_uri%22" in url
    assert "results=3" in url
    assert "format=json" in url


def test_search_returns_normalized_results(monkeypatch) -> None:
    payload = b'{"results":[{"title":"One","url":"https://example.com/1","content":"alpha"},{"title":"","url":"https://example.com/2"},{"title":"Two","url":"https://example.com/2"}]}'

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return payload

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=10: FakeResponse())
    client = WebSearchClient("http://search.example.com/search?q=<query>&format=json")
    results = client.search("proxmox")

    assert results == [
        SearchResult(title="One", url="https://example.com/1", content="alpha"),
        SearchResult(title="Two", url="https://example.com/2", content=""),
    ]
