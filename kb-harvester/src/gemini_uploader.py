from __future__ import annotations

import base64
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


class GeminiUploadError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        file_search_store_name: str | None = None,
        files_uploaded: int = 0,
        current_filename: str | None = None,
        operation_name: str | None = None,
    ) -> None:
        super().__init__(message)
        self.file_search_store_name = file_search_store_name
        self.files_uploaded = files_uploaded
        self.current_filename = current_filename
        self.operation_name = operation_name


def load_gemini_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as state_file:
            return json.load(state_file)
    except json.JSONDecodeError:
        recovered = recover_gemini_state_prefix(path)
        if recovered is not None:
            return recovered
        raise


def recover_gemini_state_prefix(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    marker = '\n  "last_query"'
    marker_index = text.find(marker)
    if marker_index == -1:
        return None
    prefix = text[:marker_index].rstrip().rstrip(",") + "\n}\n"
    try:
        return json.loads(prefix)
    except json.JSONDecodeError:
        return None


def save_gemini_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as state_file:
        json.dump(to_json_safe(state), state_file, indent=2, ensure_ascii=False)
        state_file.write("\n")
    tmp_path.replace(path)


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
    reupload_existing: bool = False,
) -> list[Path]:
    if force_upload_all:
        candidates = sorted(output_dir.glob("*.md"))
    elif changed_files:
        candidates = changed_files
    else:
        candidates = [Path(entry.get("file", "")) for entry in manifest.values()]

    candidates = [path for path in candidates if path.exists()]
    if reupload_existing:
        return candidates

    uploaded_hashes = {
        item.get("source_hash")
        for item in state.get("uploaded_files", [])
        if item.get("source_hash")
    }
    if not uploaded_hashes:
        return candidates

    hash_by_file = {
        entry.get("file"): entry.get("hash")
        for entry in manifest.values()
    }
    return [
        path for path in candidates
        if hash_by_file.get(str(path)) not in uploaded_hashes
    ]


def upload_markdown_files_to_store(
    client,
    file_search_store_name: str,
    file_paths: list[Path],
    manifest: dict,
    operation_timeout_seconds: int,
) -> dict[str, Any]:
    uploaded_files: list[dict[str, Any]] = []
    total = len(file_paths)
    for index, path in enumerate(file_paths, start=1):
        print(f"[Gemini] Uploading {index}/{total}: {path.name}", flush=True)
        try:
            operation = client.file_search_stores.upload_to_file_search_store(
                file=str(path),
                file_search_store_name=file_search_store_name,
                config={"display_name": path.name},
            )
            operation_name = get_operation_name(operation)
            if operation_name:
                print(f"[Gemini] Operation {index}/{total}: {operation_name}", flush=True)
            operation = poll_operation(
                client,
                operation,
                operation_timeout_seconds,
                current_filename=str(path),
                files_uploaded=len(uploaded_files),
                file_search_store_name=file_search_store_name,
            )
        except GeminiUploadError:
            raise
        except Exception as exc:
            raise GeminiUploadError(
                f"Gemini upload failed for {path.name}: {exc}",
                file_search_store_name=file_search_store_name,
                files_uploaded=len(uploaded_files),
                current_filename=str(path),
                operation_name=locals().get("operation_name"),
            ) from exc

        uploaded_files.append(build_upload_record(path, manifest, operation))
        print(f"[Gemini] Uploaded {index}/{total}: {path.name}", flush=True)

    return {
        "provider": "gemini",
        "status": "succeeded",
        "files_uploaded": len(uploaded_files),
        "uploaded_files": uploaded_files,
        "message": "No changed files to upload." if not uploaded_files else None,
    }


def poll_operation(
    client,
    operation,
    timeout_seconds: int,
    *,
    current_filename: str,
    files_uploaded: int,
    file_search_store_name: str,
):
    started_at = time.monotonic()
    operation_name = get_operation_name(operation)
    while not operation.done:
        if time.monotonic() - started_at >= timeout_seconds:
            raise GeminiUploadError(
                f"Gemini upload timed out after {timeout_seconds}s for {current_filename}",
                file_search_store_name=file_search_store_name,
                files_uploaded=files_uploaded,
                current_filename=current_filename,
                operation_name=operation_name,
            )
        time.sleep(POLL_INTERVAL_SECONDS)
        operation = client.operations.get(operation)
    return operation


def get_operation_name(operation: object) -> str | None:
    operation_data = to_plain(operation)
    if isinstance(operation_data, dict):
        return operation_data.get("name")
    return getattr(operation, "name", None)


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
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return {
        "query": query,
        "answer": getattr(response, "text", "") or "",
        "model": model,
        "file_search_store_name": file_search_store_name,
        "created_at": now,
        "updated_at": now,
    }


def to_json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_json_safe(item) for item in value]
    if hasattr(value, "model_dump"):
        return to_json_safe(value.model_dump())
    if hasattr(value, "to_json_dict"):
        return to_json_safe(value.to_json_dict())
    if hasattr(value, "to_dict"):
        return to_json_safe(value.to_dict())
    return str(value)


def to_plain(value: object) -> object:
    return to_json_safe(value)
