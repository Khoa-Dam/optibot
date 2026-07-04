from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ASSISTANT_SYSTEM_PROMPT = """You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply."""


def load_openai_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as state_file:
        return json.load(state_file)


def save_openai_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as state_file:
        json.dump(state, state_file, indent=2, ensure_ascii=False)
        state_file.write("\n")


def get_or_create_vector_store(client, name: str) -> str:
    vector_stores = client.vector_stores.list(limit=100)
    for vector_store in vector_stores.data:
        if vector_store.name == name:
            return vector_store.id
    return client.vector_stores.create(name=name).id


def get_or_create_assistant(client, name: str, model: str, vector_store_id: str) -> str:
    assistants = client.beta.assistants.list(limit=100)
    for assistant in assistants.data:
        if assistant.name == name:
            client.beta.assistants.update(
                assistant_id=assistant.id,
                instructions=ASSISTANT_SYSTEM_PROMPT,
                model=model,
                tools=[{"type": "file_search"}],
                tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}},
            )
            return assistant.id

    assistant = client.beta.assistants.create(
        name=name,
        instructions=ASSISTANT_SYSTEM_PROMPT,
        model=model,
        tools=[{"type": "file_search"}],
        tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}},
    )
    return assistant.id


def detach_vector_store_file(client, vector_store_id: str, openai_file_id: str) -> str | None:
    if not openai_file_id:
        return None
    try:
        client.vector_stores.files.delete(
            vector_store_id=vector_store_id,
            file_id=openai_file_id,
        )
        return None
    except Exception as exc:
        return f"Could not detach previous OpenAI file {openai_file_id}: {exc}"


def upload_markdown_files(client, vector_store_id: str, file_paths: list[Path]) -> dict:
    if not file_paths:
        return {
            "vector_store_id": vector_store_id,
            "files_uploaded": 0,
            "uploaded_files": [],
            "message": "No changed files to upload.",
            "chunking_strategy": "platform-managed by OpenAI Vector Store",
        }

    file_streams = [path.open("rb") for path in file_paths]
    try:
        file_batch = client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store_id,
            files=file_streams,
        )
    finally:
        for stream in file_streams:
            stream.close()

    uploaded_files = _list_batch_files(client, vector_store_id, file_batch.id, file_paths)
    return {
        "vector_store_id": vector_store_id,
        "files_uploaded": len(file_paths),
        "uploaded_files": uploaded_files,
        "file_batch_id": file_batch.id,
        "file_batch_status": file_batch.status,
        "file_counts": _to_plain(getattr(file_batch, "file_counts", None)),
        "chunking_strategy": "platform-managed by OpenAI Vector Store",
    }


def _list_batch_files(client, vector_store_id: str, batch_id: str, file_paths: list[Path]) -> list[dict]:
    batch_files = client.vector_stores.file_batches.list_files(
        vector_store_id=vector_store_id,
        batch_id=batch_id,
        limit=100,
    )
    file_ids = [item.id for item in batch_files.data]
    return [
        {"path": str(path), "openai_file_id": file_ids[index] if index < len(file_ids) else None}
        for index, path in enumerate(file_paths)
    ]


def _to_plain(value: object) -> object:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value
