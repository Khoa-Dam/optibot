from __future__ import annotations

import hashlib
import json
from pathlib import Path

from slugify import slugify


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as manifest_file:
        return json.load(manifest_file)


def save_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as manifest_file:
        json.dump(manifest, manifest_file, indent=2, ensure_ascii=False)
        manifest_file.write("\n")


def create_slug(title: str, article_id: str, used_slugs: set[str]) -> str:
    base_slug = slugify(title or f"article-{article_id}", lowercase=True)
    base_slug = base_slug.strip("-") or f"article-{article_id}"
    candidate = base_slug
    if candidate in used_slugs:
        candidate = f"{base_slug}-{article_id}"
    used_slugs.add(candidate)
    return candidate


def create_content_hash(content: str) -> str:
    normalized = "\n".join(line.rstrip() for line in content.strip().splitlines())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _escape_yaml(value: object) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


def build_markdown_document(article: dict, body_markdown: str) -> str:
    title = article.get("title") or f"Article {article.get('id', '')}".strip()
    source_url = article.get("html_url") or ""
    document = f'''---
title: "{_escape_yaml(title)}"
source_url: "{_escape_yaml(source_url)}"
article_id: "{_escape_yaml(article.get("id"))}"
updated_at: "{_escape_yaml(article.get("updated_at"))}"
edited_at: "{_escape_yaml(article.get("edited_at"))}"
---

# {title}

Article URL: {source_url}

{body_markdown.strip()}
'''
    return document.strip() + "\n"


def save_markdown_file(output_dir: Path, slug: str, markdown: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{slug}.md"
    path.write_text(markdown, encoding="utf-8")
    return path
