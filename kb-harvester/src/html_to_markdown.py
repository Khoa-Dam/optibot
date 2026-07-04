from __future__ import annotations

import re
from urllib.parse import urlparse

import html2text
from bs4 import BeautifulSoup


NOISY_SELECTORS = [
    ".nav",
    ".navbar",
    ".footer",
    ".sidebar",
    ".breadcrumbs",
    ".article-votes",
    ".article-share",
    ".related-articles",
    ".recent-articles",
    ".comments",
    ".advertisement",
    ".ads",
]


def _same_domain_url_to_relative(url: str, base_url: str) -> str:
    parsed = urlparse(url)
    base = urlparse(base_url)
    if parsed.scheme in {"http", "https"} and parsed.netloc == base.netloc:
        return parsed.path or "/"
    return url


def clean_html(html: str, base_url: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")

    for tag in soup.find_all(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    for selector in NOISY_SELECTORS:
        for node in soup.select(selector):
            node.decompose()

    for link in soup.find_all("a", href=True):
        link["href"] = _same_domain_url_to_relative(link["href"], base_url)

    return str(soup)


def html_to_markdown(html: str) -> str:
    converter = html2text.HTML2Text()
    converter.body_width = 0
    converter.ignore_images = False
    converter.ignore_links = False
    converter.protect_links = True
    converter.unicode_snob = True
    converter.mark_code = True
    markdown = converter.handle(html or "")
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    return markdown.strip()
