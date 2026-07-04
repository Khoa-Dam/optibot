from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import config
from ..gemini_uploader import to_json_safe


def ensure_dirs() -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    config.openai_state_path.parent.mkdir(parents=True, exist_ok=True)
    config.gemini_state_path.parent.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)


def write_run_log(run_log: dict[str, Any]) -> Path:
    path = config.log_dir / "last-run.json"
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(to_json_safe(run_log), indent=2, ensure_ascii=False) + chr(10),
        encoding="utf-8",
    )
    tmp_path.replace(path)
    return path
