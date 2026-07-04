# kb-harvester

One-shot RAG ingestion pipeline for the OptiBot Mini-Clone take-home. It fetches public Zendesk Help Center articles, writes clean per-article Markdown, detects deltas with hashes, uploads changed files to an OpenAI Vector Store by API, and records run logs.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env
python -m src.main
```

## Environment

```env
HELP_CENTER_BASE_URL=https://support.optisigns.com
HELP_CENTER_LOCALE=en-us
ARTICLE_LIMIT=30
OUTPUT_DIR=data/markdown
MANIFEST_PATH=data/manifest.json
LOG_DIR=logs
OPENAI_STATE_PATH=data/openai_state.json
OPENAI_API_KEY=
OPENAI_VECTOR_STORE_NAME=OptiBot Knowledge Base
OPENAI_ASSISTANT_NAME=OptiBot Mini Clone
OPENAI_MODEL=gpt-4.1-mini
SKIP_OPENAI_UPLOAD=false
```

Use `SKIP_OPENAI_UPLOAD=true` to run scraper, Markdown generation, manifest update, and logs without OpenAI upload.

## Docker

```bash
docker build -t kb-harvester .
docker run --env-file .env kb-harvester
```

## Outputs

- `data/markdown/*.md`: normalized article Markdown with frontmatter and `Article URL:`.
- `data/manifest.json`: article hash manifest plus uploaded OpenAI file IDs when available.
- `data/openai_state.json`: persisted vector store and assistant IDs.
- `logs/last-run.json`: latest run counts, statuses, upload result, and warnings.

Chunking strategy: OpenAI Vector Store platform-managed chunking. Markdown files are normalized per article, with title/frontmatter/source URL included before upload.

Delta detection: each article document is hashed after Markdown normalization. New hashes are `added`, changed hashes are `updated`, unchanged hashes are `skipped`; only added/updated files are uploaded.

Daily job logs: <add deployed job logs URL here>

Screenshot: `screenshots/assistant-youtube-answer.png`

## Verification

```bash
find data/markdown -name "*.md" | wc -l
grep -R "Article URL:" data/markdown | head
grep -R "^# " data/markdown | head
cat logs/last-run.json
```
