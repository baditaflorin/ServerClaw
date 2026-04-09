from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass


DEFAULT_QUERY_URL = os.environ.get("LV3_WEB_SEARCH_QUERY_URL", "http://search.localhost/search?q=<query>&format=json")


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    content: str


class WebSearchClient:
    def __init__(self, query_url_template: str | None = None, *, timeout_seconds: int = 10) -> None:
        candidate = query_url_template or os.environ.get("LV3_WEB_SEARCH_QUERY_URL") or DEFAULT_QUERY_URL
        self.query_url_template = candidate.strip()
        self.timeout_seconds = timeout_seconds

    def build_url(self, query: str, *, max_results: int = 5) -> str:
        encoded = urllib.parse.quote(query, safe="")
        url = self.query_url_template.replace("<query>", encoded)
        parsed = urllib.parse.urlsplit(url)
        params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if not any(key == "results" for key, _value in params):
            params.append(("results", str(max_results)))
        rebuilt = parsed._replace(query=urllib.parse.urlencode(params, quote_via=urllib.parse.quote))
        return urllib.parse.urlunsplit(rebuilt)

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        request = urllib.request.Request(
            self.build_url(query, max_results=max_results),
            headers={"Accept": "application/json", "User-Agent": "lv3-web-search/0.1.0"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return [
            SearchResult(
                title=str(item.get("title", "")).strip(),
                url=str(item.get("url", "")).strip(),
                content=str(item.get("content", "")).strip(),
            )
            for item in payload.get("results", [])[:max_results]
            if str(item.get("title", "")).strip() and str(item.get("url", "")).strip()
        ]
