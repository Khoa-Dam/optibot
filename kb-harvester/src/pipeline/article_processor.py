from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import config
from ..file_store import (
    build_markdown_document,
    create_content_hash,
    create_slug,
    save_markdown_file,
)
from ..html_to_markdown import clean_html, html_to_markdown


def process_article(article: dict[str, Any], manifest: dict, used_slugs: set[str]) -> tuple[dict[str, Any], Path | None]:
    article_id = str(article.get("id") or "")
    previous = manifest.get(article_id) or {}
    title = article.get("title") or f"Article {article_id}"

    if not article.get("body"):
        return {
            "article_id": article_id,
            "title": title,
            "slug": previous.get("slug") or create_slug(title, article_id, used_slugs),
            "status": "skipped_no_body",
            "source_url": article.get("html_url") or "",
            "file": previous.get("file"),
            "hash": previous.get("hash"),
        }, None

    slug = previous.get("slug") or create_slug(title, article_id, used_slugs)
    cleaned = clean_html(article["body"], config.help_center_base_url)
    body_markdown = html_to_markdown(cleaned)
    markdown = build_markdown_document(article, body_markdown)
    content_hash = create_content_hash(markdown)

    status = "skipped"
    file_path = config.output_dir / f"{slug}.md"
    if not previous:
        status = "added"
    elif previous.get("hash") != content_hash:
        status = "updated"

    if status in {"added", "updated"}:
        file_path = save_markdown_file(config.output_dir, slug, markdown)

    manifest[article_id] = {
        "article_id": article_id,
        "title": title,
        "slug": slug,
        "source_url": article.get("html_url") or "",
        "updated_at": article.get("updated_at") or "",
        "edited_at": article.get("edited_at") or "",
        "file": str(file_path),
        "hash": content_hash,
        **({"openai_file_id": previous["openai_file_id"]} if previous.get("openai_file_id") else {}),
    }

    return {
        "article_id": article_id,
        "title": title,
        "slug": slug,
        "status": status,
        "source_url": article.get("html_url") or "",
        "file": str(file_path),
        "hash": content_hash,
    }, file_path if status in {"added", "updated"} else None


def process_articles(articles: list[dict], manifest: dict) -> tuple[list[dict[str, Any]], list[Path], int]:
    used_slugs = {entry.get("slug") for entry in manifest.values() if entry.get("slug")}
    article_logs: list[dict[str, Any]] = []
    changed_files: list[Path] = []
    failed = 0

    for article in articles:
        try:
            article_log, changed_file = process_article(article, manifest, used_slugs)
            article_logs.append(article_log)
            if changed_file:
                changed_files.append(changed_file)
        except Exception as exc:
            failed += 1
            article_logs.append({
                "article_id": str(article.get("id") or ""),
                "title": article.get("title") or "",
                "status": "failed",
                "source_url": article.get("html_url") or "",
                "error": str(exc),
            })

    return article_logs, changed_files, failed


def summarize_article_statuses(article_logs: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "added": sum(1 for item in article_logs if item["status"] == "added"),
        "updated": sum(1 for item in article_logs if item["status"] == "updated"),
        "skipped": sum(1 for item in article_logs if item["status"] == "skipped"),
    }
