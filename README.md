# EduPilot

Conversational study-abroad advisory agent: **bare-metal** Python harness (no LangChain/LangGraph). Includes agent loop, tool dispatch, SQLite-backed memory and checkpoints, compaction, prompt assembly, and optional MCP routing.

**Other languages:** [简体中文](docs/README.zh-CN.md)

## Requirements

- Python 3.11+
- An OpenAI-compatible API key (e.g. DeepSeek)

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate      # macOS / Linux

pip install -r requirements.txt
copy .env.example .env           # then edit .env — never commit real keys
```

## Run

**Web UI + API** (from repo root):

```bash
uvicorn src.backend.api:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` for the frontend.

**CLI agent loop** (optional):

```bash
python -m src.backend.loop
```

## Tests

```bash
pytest tests/ -v
```



