from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


load_dotenv()


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    help_center_base_url: str
    help_center_locale: str
    article_limit: int
    output_dir: Path
    manifest_path: Path
    openai_state_path: Path
    gemini_state_path: Path
    log_dir: Path
    openai_api_key: str
    openai_vector_store_name: str
    openai_assistant_name: str
    openai_model: str
    skip_openai_upload: bool
    gemini_api_key: str
    gemini_model: str
    gemini_file_search_store_display_name: str
    skip_gemini_upload: bool
    force_upload_all: bool
    gemini_upload_limit: int
    gemini_operation_timeout_seconds: int
    skip_gemini_query: bool
    gemini_reupload_existing: bool


HELP_CENTER_BASE_URL = os.getenv("HELP_CENTER_BASE_URL", "https://support.optisigns.com").rstrip("/")
HELP_CENTER_LOCALE = os.getenv("HELP_CENTER_LOCALE", "en-us")
ARTICLE_LIMIT = _get_int("ARTICLE_LIMIT", 30)

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "data/markdown"))
MANIFEST_PATH = Path(os.getenv("MANIFEST_PATH", "data/manifest.json"))
OPENAI_STATE_PATH = Path(os.getenv("OPENAI_STATE_PATH", "data/openai_state.json"))
GEMINI_STATE_PATH = Path(os.getenv("GEMINI_STATE_PATH", "data/gemini_state.json"))
LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_VECTOR_STORE_NAME = os.getenv("OPENAI_VECTOR_STORE_NAME", "OptiBot Knowledge Base")
OPENAI_ASSISTANT_NAME = os.getenv("OPENAI_ASSISTANT_NAME", "OptiBot Mini Clone")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
SKIP_OPENAI_UPLOAD = _get_bool("SKIP_OPENAI_UPLOAD", False)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_FILE_SEARCH_STORE_DISPLAY_NAME = os.getenv(
    "GEMINI_FILE_SEARCH_STORE_DISPLAY_NAME",
    "optibot-kb-harvester",
)
SKIP_GEMINI_UPLOAD = _get_bool("SKIP_GEMINI_UPLOAD", False)
FORCE_UPLOAD_ALL = _get_bool("FORCE_UPLOAD_ALL", False)
GEMINI_UPLOAD_LIMIT = _get_int("GEMINI_UPLOAD_LIMIT", 0)
GEMINI_OPERATION_TIMEOUT_SECONDS = _get_int("GEMINI_OPERATION_TIMEOUT_SECONDS", 180)
SKIP_GEMINI_QUERY = _get_bool("SKIP_GEMINI_QUERY", False)
GEMINI_REUPLOAD_EXISTING = _get_bool("GEMINI_REUPLOAD_EXISTING", False)

config = Config(
    help_center_base_url=HELP_CENTER_BASE_URL,
    help_center_locale=HELP_CENTER_LOCALE,
    article_limit=ARTICLE_LIMIT,
    output_dir=OUTPUT_DIR,
    manifest_path=MANIFEST_PATH,
    openai_state_path=OPENAI_STATE_PATH,
    gemini_state_path=GEMINI_STATE_PATH,
    log_dir=LOG_DIR,
    openai_api_key=OPENAI_API_KEY,
    openai_vector_store_name=OPENAI_VECTOR_STORE_NAME,
    openai_assistant_name=OPENAI_ASSISTANT_NAME,
    openai_model=OPENAI_MODEL,
    skip_openai_upload=SKIP_OPENAI_UPLOAD,
    gemini_api_key=GEMINI_API_KEY,
    gemini_model=GEMINI_MODEL,
    gemini_file_search_store_display_name=GEMINI_FILE_SEARCH_STORE_DISPLAY_NAME,
    skip_gemini_upload=SKIP_GEMINI_UPLOAD,
    force_upload_all=FORCE_UPLOAD_ALL,
    gemini_upload_limit=GEMINI_UPLOAD_LIMIT,
    gemini_operation_timeout_seconds=GEMINI_OPERATION_TIMEOUT_SECONDS,
    skip_gemini_query=SKIP_GEMINI_QUERY,
    gemini_reupload_existing=GEMINI_REUPLOAD_EXISTING,
)
