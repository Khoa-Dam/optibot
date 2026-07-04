from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import time
from typing import Any

from google import genai
from google.genai import types


SYSTEM_INSTRUCTION = """You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply."""

YOUTUBE_TEST_QUERY = "How do I add a YouTube video?"
EMBEDDING_MODEL = "models/gemini-embedding-2"
POLL_INTERVAL_SECONDS = 5


def load_gemini_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as state_file:
        return json.load(state_file)


def save_gemini_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as state_file:
        json.dump(state, state_file, indent=2, ensure_ascii=False)
        state_file.write("\n")


def create_client(api_key: str):
    return genai.Client(api_key=api_key)


def get_or_create_file_search_store(client, display_name: str, state: dict[str, Any]):
    state_name = state.get("file_search_store_name")
    if state_name:
        return client.file_search_stores.get(name=state_name)

    for store in client.file_search_stores.list():
        if getattr(store, "display_name", None) == display_name:
            return store

    return client.file_search_stores.create(
        config={
            "display_name": display_name,
            "embedding_model": EMBEDDING_MODEL,
        }
    )


def select_files_for_upload(
    changed_files: list[Path],
    manifest: dict,
    state: dict[str, Any],
    output_dir: Path,
    force_upload_all: bool,
) -> list[Path]:
    if force_upload_all:
        return sorted(output_dir.glob("*.md"))
    if changed_files:
        return changed_files
    uploaded = state.get("uploaded_files") or []
    if not uploaded:
        return sorted(output_dir.glob("*.md"))
    uploaded_by_path = {item.get("source_filename"): item for item in uploaded}
    missing: list[Path] = []
    for entry in manifest.values():
        file_path = Path(entry.get("file", ""))
        uploaded_entry = uploaded_by_path.get(str(file_path))
        if not uploaded_entry or uploaded_entry.get("source_hash") != entry.get("hash"):
            missing.append(file_path)
    return [path for path in missing if path.exists()]


def upload_markdown_files_to_store(
    client,
    file_search_store_name: str,
    file_paths: list[Path],
    manifest: dict,
) -> dict[str, Any]:
    uploaded_files: list[dict[str, Any]] = []
    for path in file_paths:
        operation = client.file_search_stores.upload_to_file_search_store(
            file=str(path),
            file_search_store_name=file_search_store_name,
            config={"display_name": path.name},
        )
        operation = poll_operation(client, operation)
        uploaded_files.append(build_upload_record(path, manifest, operation))

    return {
        "provider": "gemini",
        "files_uploaded": len(uploaded_files),
        "uploaded_files": uploaded_files,
        "message": "No changed files to upload." if not uploaded_files else None,
    }


def poll_operation(client, operation):
    while not operation.done:
        time.sleep(POLL_INTERVAL_SECONDS)
        operation = client.operations.get(operation)
    return operation


def build_upload_record(path: Path, manifest: dict, operation: object) -> dict[str, Any]:
    manifest_entry = next(
        (entry for entry in manifest.values() if entry.get("file") == str(path)),
        {},
    )
    operation_data = to_plain(operation)
    return {
        "source_filename": str(path),
        "source_hash": manifest_entry.get("hash"),
        "article_id": manifest_entry.get("article_id"),
        "gemini_operation_name": operation_data.get("name") if isinstance(operation_data, dict) else None,
        "gemini_response": operation_data.get("response") if isinstance(operation_data, dict) else None,
        "uploaded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def query_file_search_store(client, model: str, file_search_store_name: str, query: str) -> dict[str, Any]:
    response = client.models.generate_content(
        model=model,
        contents=query,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[
                types.Tool(
                    file_search=types.FileSearch(
                        file_search_store_names=[file_search_store_name],
                    )
                )
            ],
        ),
    )
    return {
        "query": query,
        "answer": getattr(response, "text", "") or "",
        "raw_response": to_plain(response),
    }


def to_plain(value: object) -> object:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "to_json_dict"):
        return value.to_json_dict()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value
