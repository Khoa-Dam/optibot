from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import config
from ..gemini_uploader import (
    YOUTUBE_TEST_QUERY,
    create_client,
    get_or_create_file_search_store,
    load_gemini_state,
    query_file_search_store,
    save_gemini_state,
    select_files_for_upload,
    upload_markdown_files_to_store,
)


def upload_changed_files(changed_files: list[Path], manifest: dict) -> dict[str, Any]:
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
    state.update({
        "file_search_store_name": store.name,
        "file_search_store_display_name": getattr(store, "display_name", None)
        or config.gemini_file_search_store_display_name,
        "model": config.gemini_model,
        "updated_at": _utc_now(),
    })
    save_gemini_state(config.gemini_state_path, state)

    files_to_upload = select_files_for_upload(
        changed_files,
        manifest,
        state,
        config.output_dir,
        config.force_upload_all,
        config.gemini_reupload_existing,
    )
    if config.gemini_upload_limit > 0:
        files_to_upload = files_to_upload[: config.gemini_upload_limit]

    upload_result = upload_markdown_files_to_store(
        client,
        store.name,
        files_to_upload,
        manifest,
        config.gemini_operation_timeout_seconds,
    )
    query_result = _query_store_if_enabled(client, store.name)
    next_state = _build_next_state(state, store, upload_result, query_result)
    save_gemini_state(config.gemini_state_path, next_state)

    upload_result["file_search_store_name"] = store.name
    upload_result["file_search_store_display_name"] = next_state["file_search_store_display_name"]
    upload_result["model"] = config.gemini_model
    upload_result["query"] = query_result
    return upload_result


def _query_store_if_enabled(client, store_name: str) -> dict[str, Any]:
    if config.skip_gemini_query:
        return {"skipped": True, "message": "Gemini query skipped by SKIP_GEMINI_QUERY=true"}
    return query_file_search_store(client, config.gemini_model, store_name, YOUTUBE_TEST_QUERY)


def _build_next_state(state: dict[str, Any], store: object, upload_result: dict[str, Any], query_result: dict[str, Any]) -> dict[str, Any]:
    existing_uploads = {
        item.get("source_filename"): item
        for item in state.get("uploaded_files", [])
    }
    for item in upload_result["uploaded_files"]:
        existing_uploads[item["source_filename"]] = item

    return {
        "file_search_store_name": store.name,
        "file_search_store_display_name": getattr(store, "display_name", None)
        or config.gemini_file_search_store_display_name,
        "model": config.gemini_model,
        "uploaded_files": list(existing_uploads.values()),
        "last_query": query_result,
        "updated_at": _utc_now(),
    }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
