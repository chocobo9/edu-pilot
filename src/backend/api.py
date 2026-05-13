from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.backend.auth import (
    AuthUser,
    authenticate_user,
    create_access_token,
    get_current_user,
    get_password_hash,
    resolve_role,
    _get_conn as get_auth_conn,
)
from src.backend.schemas import (
    AuthResponse,
    ChatRequest,
    CurrentUserResponse,
    LoginRequest,
    MessageInfo,
    RegisterRequest,
    SessionDeleteResponse,
    SessionInfo,
    SessionListResponse,
    SessionMessagesResponse,
)

DB_PATH = os.getenv("EDUPILOT_DB", "data/edupilot.db")
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

_loop_states: dict[str, object] = {}
_mcp_manager = None
_mcp_tool_specs: list = []


def _init_chat_tables() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            session_id TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(username, session_id)
        );
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            session_id TEXT NOT NULL,
            message_type TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.close()


def _save_chat_message(username: str, session_id: str, msg_type: str, content: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO chat_sessions (username, session_id, updated_at) VALUES (?, ?, ?)",
            (username, session_id, now),
        )
        conn.execute(
            "INSERT INTO chat_messages (username, session_id, message_type, content, timestamp) VALUES (?, ?, ?, ?, ?)",
            (username, session_id, msg_type, content, now),
        )
        conn.commit()
    finally:
        conn.close()


def create_app() -> FastAPI:
    application = FastAPI(title="EduPilot API")

    @application.on_event("startup")
    async def _startup():
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        _init_chat_tables()

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def _no_cache(request, call_next):
        response = await call_next(request)
        p = request.url.path or ""
        if p == "/" or p.endswith((".html", ".js", ".css")):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    # --- Auth routes ---

    @application.post("/auth/register", response_model=AuthResponse)
    async def register(request: RegisterRequest):
        username = (request.username or "").strip()
        password = (request.password or "").strip()
        if not username or not password:
            raise HTTPException(status_code=400, detail="Username and password required")

        conn = get_auth_conn()
        try:
            exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
            if exists:
                raise HTTPException(status_code=409, detail="Username already exists")
            role = resolve_role(request.role, request.admin_code)
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, get_password_hash(password), role),
            )
            conn.commit()
        finally:
            conn.close()

        token = create_access_token(username=username, role=role)
        return AuthResponse(access_token=token, username=username, role=role)

    @application.post("/auth/login", response_model=AuthResponse)
    async def login(request: LoginRequest):
        user = authenticate_user(request.username, request.password)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        token = create_access_token(username=user.username, role=user.role)
        return AuthResponse(access_token=token, username=user.username, role=user.role)

    @application.get("/auth/me", response_model=CurrentUserResponse)
    async def me(current_user: AuthUser = Depends(get_current_user)):
        return CurrentUserResponse(username=current_user.username, role=current_user.role)

    # --- Chat stream ---

    @application.post("/chat/stream")
    async def chat_stream(request: ChatRequest, current_user: AuthUser = Depends(get_current_user)):
        session_id = request.session_id or f"session_{uuid.uuid4().hex[:8]}"
        user_id = current_user.username

        async def event_generator():
            try:
                from src.backend.checkpoint import Checkpoint, CheckpointStore, deserialize_state, serialize_state
                from src.backend.compact import TOKEN_THRESHOLD, compact_messages, estimate_tokens
                from src.backend.llm import LLMClient
                from src.backend.loop import LoopState, MAX_TOOL_ROUNDS, _load_relevant_summaries, extract_notes
                from src.backend.memory import MemoryStore
                from src.backend.prompt import assemble_prompt
                from src.backend.state import ROUTE_TOOLS, classify_intent, determine_route
                from src.backend.tools import ToolRegistry
                from src.backend.tools_impl.profile import register_profile_tools
                from src.backend.tools_impl.school import register_school_tools
                from src.backend.tools_impl.timeline import register_timeline_tools
                from src.backend.tools_impl.visa import register_visa_tools

                cache_key = f"{user_id}:{session_id}"
                if cache_key in _loop_states:
                    state, memory, cp_store, llm, registry = _loop_states[cache_key]
                else:
                    llm = LLMClient()
                    memory = MemoryStore(db_path=DB_PATH)
                    cp_store = CheckpointStore(db_path=DB_PATH)
                    state = LoopState()
                    registry = ToolRegistry()
                    register_school_tools(registry)
                    register_visa_tools(registry)
                    register_timeline_tools(registry)
                    register_profile_tools(
                        registry,
                        get_profile=lambda: state.profile,
                        set_field=lambda f, v: setattr(state.profile, f, v),
                        save_note=lambda content, category: (
                            memory.add_note(user_id, content, category, state.turn_count),
                            f"Note saved: [{category}] {content}",
                        )[-1],
                    )

                    loaded = memory.load_profile(user_id)
                    if loaded:
                        state.profile = loaded

                    cp = cp_store.load_latest(user_id)
                    if cp and cp_store.is_recent(cp):
                        restored = deserialize_state(cp.state_json)
                        state.messages = restored.messages
                        state.turn_count = restored.turn_count
                        state.profile = restored.profile
                        state.current_route = restored.current_route

                    _loop_states[cache_key] = (state, memory, cp_store, llm, registry)

                notes = memory.load_notes(user_id)
                summaries = _load_relevant_summaries(memory, user_id, state.current_route)

                state.messages.append({"role": "user", "content": request.message})
                _save_chat_message(user_id, session_id, "human", request.message)

                if estimate_tokens(state.messages) > TOKEN_THRESHOLD:
                    state.messages, _ = await asyncio.to_thread(compact_messages, state.messages, llm)

                full_response = ""
                tool_rounds = 0
                while tool_rounds < MAX_TOOL_ROUNDS:
                    system_prompt = assemble_prompt(state.profile, state.current_route, notes=notes, summaries=summaries)
                    messages_with_system = [{"role": "system", "content": system_prompt}] + state.messages
                    route_tool_names = ROUTE_TOOLS.get(state.current_route, [])
                    tool_schemas = registry.schemas_for_names(route_tool_names)

                    response = await asyncio.to_thread(llm.chat, messages_with_system, tool_schemas)

                    if response.tool_calls:
                        state.messages.append({
                            "role": "assistant", "content": response.content,
                            "tool_calls": [
                                {"id": tc.id, "type": "function",
                                 "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
                                for tc in response.tool_calls
                            ],
                        })
                        for tc in response.tool_calls:
                            calling_data = {"type": "tool_call", "name": tc.name, "arguments": tc.arguments, "status": "calling"}
                            yield f"data: {json.dumps(calling_data, ensure_ascii=False)}\n\n"
                            result = registry.dispatch(tc.name, tc.arguments)
                            state.messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                            done_data = {"type": "tool_call", "name": tc.name, "status": "done", "preview": result[:80]}
                            yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"
                        tool_rounds += 1
                    else:
                        full_response = response.content or ""
                        state.messages.append({"role": "assistant", "content": full_response})
                        chunk_data = {"type": "content", "content": full_response}
                        yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
                        break

                _save_chat_message(user_id, session_id, "ai", full_response)

                memory.save_profile(user_id, state.profile)
                try:
                    extracted = await asyncio.to_thread(extract_notes, llm, state.messages[-2:], state.turn_count)
                    for note in extracted:
                        memory.add_note(user_id, note["content"], note["category"], state.turn_count)
                except Exception:
                    pass

                intent = classify_intent(request.message, state.current_route)
                state.current_route = determine_route(state.profile, intent)

                cp_store.save(Checkpoint(
                    user_id=user_id, session_id=session_id,
                    state_json=serialize_state(state),
                    turn_count=state.turn_count, routing_context=state.current_route,
                ))
                state.turn_count += 1

                yield "data: [DONE]\n\n"

            except Exception as e:
                error_data = {"type": "error", "content": str(e)}
                yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    # --- Session management ---

    @application.get("/chat/sessions", response_model=SessionListResponse)
    async def list_sessions(current_user: AuthUser = Depends(get_current_user)):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT cs.session_id, cs.updated_at,
                       (SELECT COUNT(*) FROM chat_messages cm WHERE cm.username = cs.username AND cm.session_id = cs.session_id) as message_count
                FROM chat_sessions cs WHERE cs.username = ?
                ORDER BY cs.updated_at DESC
            """, (current_user.username,)).fetchall()
            sessions = [SessionInfo(session_id=r["session_id"], updated_at=r["updated_at"], message_count=r["message_count"]) for r in rows]
            return SessionListResponse(sessions=sessions)
        finally:
            conn.close()

    @application.get("/chat/sessions/{session_id}", response_model=SessionMessagesResponse)
    async def get_session_messages(session_id: str, current_user: AuthUser = Depends(get_current_user)):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT message_type, content, timestamp FROM chat_messages WHERE username = ? AND session_id = ? ORDER BY id",
                (current_user.username, session_id),
            ).fetchall()
            messages = [MessageInfo(type=r["message_type"], content=r["content"], timestamp=r["timestamp"]) for r in rows]
            return SessionMessagesResponse(messages=messages)
        finally:
            conn.close()

    @application.delete("/chat/sessions/{session_id}", response_model=SessionDeleteResponse)
    async def delete_session(session_id: str, current_user: AuthUser = Depends(get_current_user)):
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute("DELETE FROM chat_messages WHERE username = ? AND session_id = ?", (current_user.username, session_id))
            conn.execute("DELETE FROM chat_sessions WHERE username = ? AND session_id = ?", (current_user.username, session_id))
            conn.commit()
            cache_key = f"{current_user.username}:{session_id}"
            _loop_states.pop(cache_key, None)
            return SessionDeleteResponse(session_id=session_id, message="Session deleted")
        finally:
            conn.close()

    # --- Static frontend ---
    if FRONTEND_DIR.exists():
        application.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")

    return application


app = create_app()
