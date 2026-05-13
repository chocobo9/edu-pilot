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

## Prompts & skills

Long-form LLM instructions live in **Markdown skills** under `src/backend/skills/`. Each skill is a folder containing `SKILL.md` with optional YAML frontmatter (`name`, `description`). At runtime, `src/backend/skills/loader.py` scans these files and `load_skill("<name>")` returns the document body.

**Wired into the main system prompt** (`assemble_prompt` in `src/backend/prompt.py`, via `src/backend/state.py`):

| Skill `name` (frontmatter) | When it is used |
|----------------------------|-----------------|
| `base-role` | Core assistant role and safety rules (always). |
| `route-intake`, `route-school-match`, `route-visa-advisory`, `route-timeline`, `route-general-qa` | The **Current Mode** section for the active route (`school_match` → `route-school-match`, etc.). Unknown routes fall back to `route-general-qa`. |

**Still assembled in code** (not full documents in skills): section headings and text for known profile fields, advisor notes, and past session summaries—those blocks are built from live data so the model sees current state.

**Other shipped skills** (same directory; loaded through helpers in `src/backend/memory.py` when you call `get_extraction_prompt()` / `get_summarization_prompt()`): `extraction`, `summarization`. Use them to keep entity-extraction or summarization prompts in Markdown instead of string literals in callers.


