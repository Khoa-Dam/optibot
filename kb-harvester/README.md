# kb-harvester

One-shot RAG ingestion pipeline for the OptiBot Mini-Clone take-home. It fetches at least 30 public Zendesk Help Center articles from `support.optisigns.com`, converts each article to clean slug-based Markdown, detects deltas with hashes, uploads changed Markdown files to Gemini File Search through API only, and records run logs.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env
# Set GEMINI_API_KEY in .env
python -m src.main
```

Important environment variables:

```env
HELP_CENTER_BASE_URL=https://support.optisigns.com
HELP_CENTER_LOCALE=en-us
ARTICLE_LIMIT=30
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_FILE_SEARCH_STORE_DISPLAY_NAME=optibot-kb-harvester
SKIP_GEMINI_UPLOAD=false
FORCE_UPLOAD_ALL=false
GEMINI_REUPLOAD_EXISTING=false
GEMINI_UPLOAD_LIMIT=0
SKIP_GEMINI_QUERY=false
```

## Docker

```bash
docker build -t kb-harvester:local .
docker run --rm --env-file .env -v "$PWD/data:/app/data" -v "$PWD/logs:/app/logs" kb-harvester:local
```

The container runs `python -m src.main` once, prints a summary, and exits. A daily scheduled job should run this same one-shot command/container.

## Outputs

- `data/markdown/*.md`: normalized article Markdown with frontmatter, headings, links, code blocks, images when present, and `Article URL:` for citations.
- `data/manifest.json`: article metadata and content hashes used for `added`, `updated`, and `skipped` detection.
- `data/gemini_state.json`: Gemini File Search Store name plus uploaded document/file operation metadata.
- `logs/last-run.json`: latest scrape counts, upload/index result, query result, and warnings.

The scraper uses Zendesk Help Center article content instead of browser scraping, which avoids nav, sidebar, footer, and other page noise.

## Gemini File Search

Markdown files are uploaded/indexed through the official Gemini API, not UI drag-and-drop. Gemini File Search is used as the Google Gemini equivalent of a vector store/knowledge base. The query uses this system instruction verbatim:

```text
You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply.
```

Chunking strategy: Gemini File Search manages chunking/indexing internally. This implementation uploads normalized Markdown documents and stores document/file operation metadata; chunk count is not directly exposed by the Gemini File Search response used here.

Delta upload: each normalized Markdown document is hashed. New files are `added`, changed files are `updated`, unchanged files are `skipped`, and only added/updated files are uploaded unless reupload is explicitly enabled.

## Verification

Verified locally: 30 Markdown files generated, 30 files uploaded/indexed, rerun uploads 0 unchanged files, and the sanity query `How do I add a YouTube video?` returns a grounded answer with an `Article URL:` citation.

```bash
find data/markdown -name "*.md" | wc -l
grep -R "Article URL:" data/markdown | head
grep -R "^# " data/markdown | head
cat logs/last-run.json
```

Daily job logs: Railway cron snapshot in `logs/railway-last-run.txt`.

Screenshot: `screenshots/assistant-youtube-answer.png`
