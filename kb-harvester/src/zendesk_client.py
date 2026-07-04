from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin

import requests

from .config import HELP_CENTER_BASE_URL, HELP_CENTER_LOCALE


MAX_RETRIES = 3
REQUEST_TIMEOUT = 30


class ZendeskAPIError(RuntimeError):
    pass


def _articles_url() -> str:
    return urljoin(
        f"{HELP_CENTER_BASE_URL}/",
        f"api/v2/help_center/{HELP_CENTER_LOCALE}/articles.json",
    )


def _next_page_url(payload: dict[str, Any]) -> str | None:
    links = payload.get("links") or {}
    return payload.get("next_page") or links.get("next")


def _request_page(url: str, params: dict[str, Any] | None) -> dict[str, Any]:
    backoff_seconds = 1
    for attempt in range(1, MAX_RETRIES + 1):
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if response.status_code == 429 and attempt < MAX_RETRIES:
            retry_after = response.headers.get("Retry-After")
            sleep_seconds = int(retry_after) if retry_after and retry_after.isdigit() else backoff_seconds
            time.sleep(sleep_seconds)
            backoff_seconds *= 2
            continue
        if response.ok:
            return response.json()
        raise ZendeskAPIError(
            f"Zendesk API request failed: {response.status_code} {response.text[:300]}"
        )
    raise ZendeskAPIError("Zendesk API rate limit retries exhausted")


def _normalize_article(article: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(article.get("id", "")),
        "title": article.get("title") or "",
        "body": article.get("body") or "",
        "html_url": article.get("html_url") or "",
        "section_id": article.get("section_id"),
        "updated_at": article.get("updated_at") or "",
        "edited_at": article.get("edited_at") or "",
        "locale": article.get("locale") or HELP_CENTER_LOCALE,
    }


def fetch_articles(limit: int) -> list[dict]:
    if limit < 1:
        raise ValueError("limit must be greater than 0")

    articles: list[dict] = []
    url = _articles_url()
    params: dict[str, Any] | None = {
        "per_page": 100,
        "sort_by": "updated_at",
        "sort_order": "desc",
    }

    while url and len(articles) < limit:
        payload = _request_page(url, params)
        page_articles = payload.get("articles")
        if not isinstance(page_articles, list):
            raise ZendeskAPIError("Zendesk API response did not include articles")

        for article in page_articles:
            if len(articles) >= limit:
                break
            if article.get("draft") is True:
                continue
            articles.append(_normalize_article(article))

        url = _next_page_url(payload)
        params = None

    if len(articles) < limit:
        raise ZendeskAPIError(f"Fetched {len(articles)} public articles, expected {limit}")
    return articles
