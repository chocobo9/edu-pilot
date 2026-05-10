# CLAUDE.md — EduPilot

> Read this file at the start of every session.
> Read PROGRESS.md to know what to work on next.
> After completing work, update PROGRESS.md before ending the session.

---

## Project Identity

**EduPilot** is a conversational study-abroad advisory agent built as a **bare-metal harness** — no LangGraph, no LangChain, no framework. The goal is to implement production agent mechanisms from scratch: agent loop, tool dispatch, structured state, persistent memory, session checkpointing, conversation compaction, prompt assembly, and MCP capability routing.

**Tech stack constraints (hard rules):**
- Python 3.11+
- No LangGraph, no LangChain, no CrewAI, no agent frameworks of any kind
- SQLite for all persistence (memory, checkpoints, summaries)
- OpenAI-compatible API for LLM calls (DeepSeek or OpenAI endpoint)
- Standard library + minimal dependencies (httpx or requests, sqlite3, dataclasses, json, subprocess)
- pytest for testing

**Design reference:** `edupilot_plan.md` contains the full architecture — 8 modules (A–H), each with six-question spec (what problem, which layer, what state, what data structures, how it plugs into loop, runtime flow change). Consult it for any design decision.

---

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

---

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

---

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the current task.

---

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

### Don't wait for the user to report obvious problems

If you see a bug, wrong output, or deviation from the spec during your own 
testing — fix it immediately. Do not describe the problem and wait for the 
user to tell you to fix it. The user hired you to solve problems, not to 
narrate them.

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.


---

## 5. Verification Is Not Optional

**pytest alone is NOT sufficient. Every module must be verified with real interaction.**

### Three levels of verification (ALL required):

**Level 1 — Unit tests (pytest):**
- Every module gets tests. No exceptions.
- Test the happy path, one edge case, and one failure case minimum.
- Run `pytest` after every module completion. All tests must pass before moving on.

**Level 2 — Integration smoke test:**
- After completing each module, run a real interaction that exercises the new mechanism.
- Example: After Module D (Memory), run a 3-turn conversation, then verify the SQLite database actually contains extracted profile fields. Don't just assert in pytest — query the DB and show the rows.
- Example: After Module E (Checkpointing), run a conversation, kill it, resume it, and show the conversation continues from where it left off.

**Level 3 — End-to-end demo (after Module G):**
- Run the full demo scenario from `edupilot_plan.md` Section 6:
  - Session 1: new user, intake → school match → visa advisory → session close
  - Session 2: same user returns, profile loaded, GPA updated
- Capture actual agent output and verify against acceptance criteria.
- Save the demo transcript to `data/demos/`.

### Verification anti-patterns (DO NOT do these):
- ❌ Writing only pytest mocks without ever hitting the real SQLite DB
- ❌ Saying "tests pass" without showing the actual test run output
- ❌ Skipping the integration smoke test because "pytest covers it"
- ❌ Ending a session after pytest passes without running real interaction

### Verification attitude rule

When L2 smoke test reveals ANY incorrect behavior — hallucination, wrong data, 
missing fields, unexpected routing — treat it as a blocking bug. Do NOT write 
"L2 verified" and move on. Fix it, re-run, and only mark verified when the 
output is fully correct.

"It works except for X" means it does not work.

---

## 6. Code Style

```python
# Use dataclasses for all data structures
@dataclass
class UserProfile:
    gpa: float | None = None
    ...

# Type hints on all function signatures
def extract_entities(messages: list[dict]) -> list[MemoryEvent]:
    ...

# Docstrings on public functions — one line is fine
def dispatch(self, name: str, args: dict) -> str:
    """Execute a registered tool by name."""
    ...

# No classes where a function will do
# No inheritance unless there's a real second implementation
# No abstract base classes for single implementations
```

---

## 7. File Structure

```
edupilot/
├── CLAUDE.md                    # this file
├── PROGRESS.md                  # session tracker
├── edupilot_plan.md             # design reference
├── src/
│   ├── __init__.py
│   ├── loop.py                  # Module A: agent loop
│   ├── tools.py                 # Module B: tool registry + dispatch
│   ├── state.py                 # Module C: UserProfile, Intent, routing logic
│   ├── memory.py                # Module D: MemoryStore, MemoryEvent, extraction
│   ├── checkpoint.py            # Module E: CheckpointStore
│   ├── compact.py               # Module F: compaction logic
│   ├── prompt.py                # Module G: PromptAssembler
│   ├── mcp.py                   # Module H: MCPManager, MCPConnection
│   ├── llm.py                   # LLM client wrapper (OpenAI-compatible)
│   └── tools_impl/              # actual tool implementations
│       ├── school.py            # query_programs
│       ├── visa.py              # check_visa_eligibility
│       ├── timeline.py          # calculate_timeline
│       └── knowledge.py         # search_knowledge_base
├── data/
│   ├── schools.json             # program database
│   ├── visa_rules.yaml          # IRCC decision tree
│   ├── scholarships.json        # scholarship info
│   └── demos/                   # saved demo transcripts
├── tests/
│   ├── test_loop.py
│   ├── test_tools.py
│   ├── test_state.py
│   ├── test_memory.py
│   ├── test_checkpoint.py
│   ├── test_compact.py
│   ├── test_prompt.py
│   └── test_mcp.py
├── scripts/
│   └── run_demo.py              # end-to-end demo runner
├── .env                         # API keys
└── requirements.txt
```

---

## 8. Implementation Order

**Follow this order strictly. Do not skip ahead.**

Each module depends on the previous one. Implement, test, verify with real interaction, then move to the next.

```
Module A: Agent Loop       → verify: 3-turn CLI conversation works
    ↓
Module B: Tool Dispatch    → verify: agent calls a tool and uses the result
    ↓
Module C: State & Routing  → verify: routing changes based on profile completeness
    ↓
Module D: Memory System    → verify: profile persists in SQLite across separate runs
    ↓
Module E: Checkpointing    → verify: kill and resume mid-conversation
    ↓
Module F: Compaction       → verify: 15+ turn conversation triggers summary
    ↓
Module G: Prompt Assembly  → verify: system prompt changes based on route + profile
    ↓
Module H: MCP Routing      → verify: agent discovers and calls an MCP tool
```

---

## 9. LLM API Convention

```python
# All LLM calls go through src/llm.py
# Use OpenAI-compatible API format
# Support tool_calls in response parsing
# Environment variables: LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

import httpx, os, json

class LLMClient:
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        """Single LLM call. Returns parsed response with .content and .tool_calls."""
        ...
```

---

## 10. What "Done" Looks Like

A module is done when:
1. Code is written and follows the style rules above
2. pytest passes (Level 1)
3. Real interaction smoke test passes (Level 2)
4. PROGRESS.md is updated with completion log

The project is done when:
1. All 8 modules pass their individual verification
2. The full E2E demo scenario (Section 6 of edupilot_plan.md) runs successfully
3. Demo transcript is saved to `data/demos/`
4. All tests pass: `pytest tests/ -v`

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, clarifying questions come before implementation rather than after mistakes, and every module is verified with real interaction — not just pytest.
