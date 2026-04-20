# Hivemind

A personal knowledge tool that turns raw text into structured, searchable notes.

## Features right now
- Save notes from raw text
- Generate summary + tags
- Store tags in database
- Search by content, summary, and tags
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
