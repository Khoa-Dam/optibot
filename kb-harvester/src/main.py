from __future__ import annotations

from datetime import UTC, datetime
import sys
from typing import Any

from .config import config
from .file_store import load_manifest, save_manifest
from .pipeline.article_processor import process_articles, summarize_article_statuses
from .pipeline.gemini_pipeline import upload_changed_files
from .pipeline.run_log import ensure_dirs, write_run_log
from .zendesk_client import fetch_articles


def main() -> int:
    ensure_dirs()
    manifest = load_manifest(config.manifest_path)
    articles = fetch_articles(config.article_limit)
    article_logs, changed_files, failed = process_articles(articles, manifest)
    counts = summarize_article_statuses(article_logs)
    run_at = _utc_now()

    try:
        upload_result = upload_changed_files(changed_files, manifest)
    except Exception as exc:
        save_manifest(config.manifest_path, manifest)
        failure_result = _build_upload_failure(exc)
        write_run_log(_build_run_log(run_at, articles, counts, failed, failure_result, article_logs))
        raise

    save_manifest(config.manifest_path, manifest)
    run_log = _build_run_log(run_at, articles, counts, failed, upload_result, article_logs)
    run_log_path = write_run_log(run_log)
    _print_summary(len(articles), counts, failed, run_log, upload_result, run_log_path)
    return 0


def _build_upload_failure(exc: Exception) -> dict[str, Any]:
    return {
        "provider": "gemini",
        "status": "failed",
        "files_uploaded": getattr(exc, "files_uploaded", 0),
        "uploaded_files": [],
        "error": str(exc),
        "file_search_store_name": getattr(exc, "file_search_store_name", None),
        "current_filename": getattr(exc, "current_filename", None),
        "operation_name": getattr(exc, "operation_name", None),
    }


def _build_run_log(
    run_at: str,
    articles: list[dict],
    counts: dict[str, int],
    failed: int,
    upload_result: dict[str, Any],
    article_logs: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
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


def _print_summary(
    fetched: int,
    counts: dict[str, int],
    failed: int,
    run_log: dict[str, Any],
    upload_result: dict[str, Any],
    run_log_path: object,
) -> None:
    print("Run complete")
    print(f"Fetched articles: {fetched}")
    print("Added: {}".format(counts["added"]))
    print("Updated: {}".format(counts["updated"]))
    print("Skipped: {}".format(counts["skipped"]))
    print(f"Failed: {failed}")
    print("Uploaded files: {}".format(run_log["uploaded_files"]))
    if upload_result.get("message"):
        print(upload_result["message"])
    print(f"Output dir: {config.output_dir}")
    print(f"Manifest: {config.manifest_path}")
    print(f"Run log: {run_log_path}")

def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    sys.exit(main())
