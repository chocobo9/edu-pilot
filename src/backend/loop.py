from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from src.backend.llm import LLMClient, LLMResponse
from src.backend.prompt import assemble_prompt
from src.backend.state import (
    ROUTE_SEARCH_KEYWORDS,
    ROUTE_TOOLS,
    UserProfile,
    classify_intent,
    determine_route,
)
from src.backend.tools import ToolRegistry

MAX_TOOL_ROUNDS = 10


@dataclass
class LoopState:
    messages: list[dict] = field(default_factory=list)
    turn_count: int = 0
    done: bool = False
    max_turns: int = 20
    profile: UserProfile = field(default_factory=UserProfile)
    current_route: str = "intake"


def _load_relevant_summaries(memory, user_id: str, route: str) -> list[str]:
    """Load summaries relevant to current route via keyword search, fallback to recent."""
    keywords = ROUTE_SEARCH_KEYWORDS.get(route, [])
    if keywords:
        results = memory.search_summaries(user_id, keywords, limit=3)
        if results:
            return results
    return memory.load_recent_summaries(user_id, limit=2)


def extract_notes(llm: LLMClient, recent_messages: list[dict], turn: int) -> list[dict]:
    """Extract free-text notes from last exchange. Silent on failure."""
    prompt = (
        "Given this dialogue exchange, extract any notable user preferences, "
        "constraints, context, or decisions that are NOT structured profile fields.\n"
        "Return a JSON array: [{\"content\": \"...\", \"category\": \"preference|constraint|context|decision\"}]\n"
        "If nothing notable, return [].\n"
        "Do NOT extract: GPA, university, major, language scores, target country/programs/intake, "
        "budget, work experience, nationality — those are profile fields handled separately."
    )
    try:
        response = llm.chat([
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(recent_messages, ensure_ascii=False)},
        ])
        parsed = json.loads(response.content)
        if isinstance(parsed, list):
            return [n for n in parsed if isinstance(n, dict) and "content" in n and "category" in n]
        return []
    except Exception:
        return []


def _generate_summary(llm: LLMClient, messages: list[dict]) -> str:
    """Generate a conversation summary via LLM. Returns empty string on failure."""
    try:
        user_assistant = [m for m in messages if m.get("role") in ("user", "assistant") and m.get("content")]
        if not user_assistant:
            return ""
        response = llm.chat([
            {"role": "system", "content": (
                "Summarize this study-abroad advisory conversation in 2-3 sentences. "
                "Focus on: what the student asked about, what was recommended, "
                "and any decisions made. Be concise."
            )},
            {"role": "user", "content": json.dumps(user_assistant[-10:], ensure_ascii=False)},
        ])
        return response.content or ""
    except Exception:
        return ""


def agent_loop(
    state: LoopState,
    llm: LLMClient,
    tools: ToolRegistry | None = None,
    memory=None,
    checkpoint_store=None,
    user_id: str = "default",
    session_id: str = "",
) -> LoopState:
    """Main agent loop. Runs a multi-turn CLI conversation."""
    # Pre-loop: load profile and context from memory
    notes = []
    summaries = []
    if memory:
        loaded = memory.load_profile(user_id)
        if loaded:
            state.profile = loaded
        notes = memory.load_notes(user_id)
        summaries = _load_relevant_summaries(memory, user_id, state.current_route)

    # Pre-loop: resume from checkpoint (wins over memory-loaded state)
    if checkpoint_store:
        from src.backend.checkpoint import deserialize_state
        cp = checkpoint_store.load_latest(user_id)
        if cp and checkpoint_store.is_recent(cp):
            restored = deserialize_state(cp.state_json)
            state.messages = restored.messages
            state.turn_count = restored.turn_count
            state.profile = restored.profile
            state.current_route = restored.current_route
            if memory:
                notes = memory.load_notes(user_id)
                summaries = _load_relevant_summaries(memory, user_id, state.current_route)
            print(f"[Resumed session from turn {state.turn_count}]")

    while not state.done and state.turn_count < state.max_turns:
        try:
            user_input = input("> ").strip()
        except EOFError:
            state.done = True
            break
        if user_input.lower() in ("quit", "exit", "q"):
            state.done = True
            break

        state.messages.append({"role": "user", "content": user_input})

        # Compaction check before LLM call
        from src.backend.compact import TOKEN_THRESHOLD, compact_messages, estimate_tokens, save_transcript
        if estimate_tokens(state.messages) > TOKEN_THRESHOLD:
            transcript_path = save_transcript(state.messages, user_id, state.turn_count)
            state.messages, _ = compact_messages(state.messages, llm)
            if transcript_path:
                print(f"[Compacted: transcript saved to {transcript_path}]")

        tool_rounds = 0
        while tool_rounds < MAX_TOOL_ROUNDS:
            system_prompt = assemble_prompt(
                state.profile, state.current_route,
                notes=notes, summaries=summaries,
            )
            messages_with_system = [{"role": "system", "content": system_prompt}] + state.messages

            route_tool_names = list(ROUTE_TOOLS.get(state.current_route, []))
            if tools:
                route_tool_names += tools.mcp_tool_names()
            tool_schemas = tools.schemas_for_names(route_tool_names) if tools else None

            response = llm.chat(messages_with_system, tool_schemas)

            if response.tool_calls:
                state.messages.append({
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in response.tool_calls
                    ],
                })
                for tc in response.tool_calls:
                    result = tools.dispatch(tc.name, tc.arguments) if tools else "Error: Tool not available"
                    state.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
                tool_rounds += 1
            else:
                state.messages.append({"role": "assistant", "content": response.content})
                print(f"Agent: {response.content}")
                break

        # Post-turn: persist profile + extract notes
        if memory:
            memory.save_profile(user_id, state.profile)
            extracted = extract_notes(llm, state.messages[-2:], state.turn_count)
            for note in extracted:
                memory.add_note(user_id, note["content"], note["category"], state.turn_count)
            notes = memory.load_notes(user_id)

        intent = classify_intent(user_input, state.current_route)
        state.current_route = determine_route(state.profile, intent)

        # Refresh summaries when route changes
        if memory:
            summaries = _load_relevant_summaries(memory, user_id, state.current_route)

        # Post-turn: save checkpoint
        if checkpoint_store:
            from src.backend.checkpoint import Checkpoint, serialize_state
            checkpoint_store.save(Checkpoint(
                user_id=user_id,
                session_id=session_id,
                state_json=serialize_state(state),
                turn_count=state.turn_count,
                routing_context=state.current_route,
            ))

        state.turn_count += 1

    # Post-loop: generate summary + dream
    if memory and state.turn_count > 0:
        summary = _generate_summary(llm, state.messages)
        if summary:
            memory.save_summary(user_id, session_id, summary, state.turn_count)
            memory.dream(user_id, summary, llm)
        memory.close()

    return state


def main(user_id: str = "default") -> None:
    from src.backend.checkpoint import CheckpointStore
    from src.backend.memory import MemoryStore
    from src.backend.tools_impl.profile import register_profile_tools
    from src.backend.tools_impl.school import register_school_tools
    from src.backend.tools_impl.timeline import register_timeline_tools
    from src.backend.tools_impl.visa import register_visa_tools

    print("EduPilot — Study Abroad Advisory Agent")
    print("Type 'quit' to exit.\n")

    session_id = str(uuid.uuid4())
    llm = LLMClient()
    memory = MemoryStore()
    checkpoint_store = CheckpointStore()
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

    # MCP: connect to external tool servers (optional)
    from src.backend.mcp import MCPManager, load_mcp_configs, register_mcp_tools
    mcp_manager = MCPManager()
    for config in load_mcp_configs():
        mcp_manager.connect(config)
    existing_tool_names = {s["function"]["name"] for s in registry.schemas()}
    register_mcp_tools(registry, mcp_manager, existing_names=existing_tool_names)

    try:
        agent_loop(state, llm, registry, memory=memory, checkpoint_store=checkpoint_store,
                   user_id=user_id, session_id=session_id)
    except KeyboardInterrupt:
        print("\n\nSession interrupted.")
    finally:
        mcp_manager.disconnect_all()
        checkpoint_store.close()
        llm.close()
        print("Goodbye!")


if __name__ == "__main__":
    main()
