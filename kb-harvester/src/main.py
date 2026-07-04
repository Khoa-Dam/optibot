from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any

from .config import config
from .file_store import (
    build_markdown_document,
    create_content_hash,
    create_slug,
    load_manifest,
    save_manifest,
    save_markdown_file,
)
from .gemini_uploader import (
    YOUTUBE_TEST_QUERY,
    create_client,
    get_or_create_file_search_store,
    load_gemini_state,
    query_file_search_store,
    save_gemini_state,
    select_files_for_upload,
    upload_markdown_files_to_store,
)
from .html_to_markdown import clean_html, html_to_markdown
from .zendesk_client import fetch_articles


def ensure_dirs() -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    config.openai_state_path.parent.mkdir(parents=True, exist_ok=True)
    config.gemini_state_path.parent.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)


def process_article(article: dict, manifest: dict, used_slugs: set[str]) -> tuple[dict, Path | None]:
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


def upload_changed_files(
    changed_files: list[Path],
    manifest: dict,
) -> dict[str, Any]:
    if config.skip_gemini_upload:
        return {
            "provider": "gemini",
            "files_uploaded": 0,
            "uploaded_files": [],
            "message": "Gemini upload skipped by SKIP_GEMINI_UPLOAD=true",
        }
    if not config.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is required unless SKIP_GEMINI_UPLOAD=true")

    client = create_client(config.gemini_api_key)
    state = load_gemini_state(config.gemini_state_path)
    store = get_or_create_file_search_store(
        client,
        config.gemini_file_search_store_display_name,
        state,
    )
    files_to_upload = select_files_for_upload(
        changed_files,
        manifest,
        state,
        config.output_dir,
        config.force_upload_all,
    )
    upload_result = upload_markdown_files_to_store(client, store.name, files_to_upload, manifest)
    query_result = query_file_search_store(client, config.gemini_model, store.name, YOUTUBE_TEST_QUERY)

    existing_uploads = {
        item.get("source_filename"): item
        for item in state.get("uploaded_files", [])
    }
    for item in upload_result["uploaded_files"]:
        existing_uploads[item["source_filename"]] = item

    next_state = {
        "file_search_store_name": store.name,
        "file_search_store_display_name": getattr(store, "display_name", None)
        or config.gemini_file_search_store_display_name,
        "model": config.gemini_model,
        "uploaded_files": list(existing_uploads.values()),
        "last_query": query_result,
        "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    save_gemini_state(config.gemini_state_path, next_state)

    upload_result["file_search_store_name"] = store.name
    upload_result["file_search_store_display_name"] = next_state["file_search_store_display_name"]
    upload_result["model"] = config.gemini_model
    upload_result["query"] = query_result
    return upload_result

def write_run_log(run_log: dict[str, Any]) -> Path:
    path = config.log_dir / "last-run.json"
    path.write_text(json.dumps(run_log, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ensure_dirs()
    manifest = load_manifest(config.manifest_path)
    used_slugs = {entry.get("slug") for entry in manifest.values() if entry.get("slug")}
    articles = fetch_articles(config.article_limit)

    article_logs: list[dict] = []
    changed_files: list[Path] = []
    changed_articles: list[dict] = []
    failed = 0

    for article in articles:
        try:
            article_log, changed_file = process_article(article, manifest, used_slugs)
            article_logs.append(article_log)
            if changed_file:
                changed_files.append(changed_file)
                changed_articles.append(article_log)
        except Exception as exc:
            failed += 1
            article_logs.append({
                "article_id": str(article.get("id") or ""),
                "title": article.get("title") or "",
                "status": "failed",
                "source_url": article.get("html_url") or "",
                "error": str(exc),
            })

    counts = {
        "added": sum(1 for item in article_logs if item["status"] == "added"),
        "updated": sum(1 for item in article_logs if item["status"] == "updated"),
        "skipped": sum(1 for item in article_logs if item["status"] == "skipped"),
    }
    run_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    try:
        upload_result = upload_changed_files(changed_files, manifest)
    except Exception as exc:
        save_manifest(config.manifest_path, manifest)
        failure_result = {
            "provider": "gemini",
            "status": "failed",
            "files_uploaded": 0,
            "uploaded_files": [],
            "error": str(exc),
        }
        write_run_log({
            "run_at": run_at,
            "fetched": len(articles),
            **counts,
            "failed": failed,
            "uploaded_files": 0,
            "gemini_file_search_store_name": None,
            "gemini_file_search_store_display_name": None,
            "upload": failure_result,
            "articles": article_logs,
        })
        raise

    save_manifest(config.manifest_path, manifest)

    run_log = {
        "run_at": run_at,
        "fetched": len(articles),
        **counts,
        "failed": failed,
        "uploaded_files": upload_result.get("files_uploaded", upload_result.get("uploaded_files", 0)),
        "gemini_file_search_store_name": upload_result.get("file_search_store_name"),
        "gemini_file_search_store_display_name": upload_result.get("file_search_store_display_name"),
        "upload": upload_result,
        "articles": article_logs,
    }
    run_log_path = write_run_log(run_log)

    print("Run complete")
    print(f"Fetched articles: {len(articles)}")
    print(f"Added: {counts['added']}")
    print(f"Updated: {counts['updated']}")
    print(f"Skipped: {counts['skipped']}")
    print(f"Failed: {failed}")
    print(f"Uploaded files: {run_log['uploaded_files']}")
    if upload_result.get("message"):
        print(upload_result["message"])
    print(f"Output dir: {config.output_dir}")
    print(f"Manifest: {config.manifest_path}")
    print(f"Run log: {run_log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
