# Hivemind

A personal knowledge tool that turns raw text into structured, searchable notes.

## Features right now
- Save notes from raw text
- Upload PDF files
- Paste screenshot images for text extraction
- Generate summary + tags
- Store tags in database
- Search by content, summary, and tags with semantic ranking
- Simple web UI for add/search/list notes

## Tech Stack
- FastAPI
- SQLite
- SQLAlchemy
- OpenAI API (optional, fallback exists)

## How to run
```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Then open `frontend/index.html` in your browser.

Optional (for real AI output instead of fallback):

PowerShell:
```bash
$env:OPENAI_API_KEY="your_key_here"
```

You can also place the key in a local `.env` file:

```bash
OPENAI_API_KEY=your_key_here
```

Without `OPENAI_API_KEY`, the app uses local fallback logic for summaries/tags/embeddings.

## Reindex old notes after updates

If you improved summary/tag logic and want old notes to use it too:

- Open `http://127.0.0.1:8000/docs`
- Run `POST /admin/reindex`

This recomputes summary, tags, and embeddings for all saved notes.

## Quick AI check

1. Start backend (`uvicorn backend.main:app --reload`)
2. Save one new note in frontend or `POST /note`
3. Run `POST /admin/reindex` once if you want old notes refreshed too
4. Confirm summaries/tags now look more semantic than fallback output

## Stability notes

- Backend now reads database path from project root (`hivemind.db`) to avoid accidental duplicate DB files.
- Frontend requests use a timeout and will show a clear error if backend is down.

## File ingest

- PDF files are read as text and saved as notes.
- Screenshot/image ingest uses OpenAI to extract text from the image first.
- In frontend, you can either choose a PDF/image file or focus the paste box and press `Ctrl+V` after using Snipping Tool.
