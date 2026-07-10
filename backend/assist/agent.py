"""CalibrationOS – Module 8: Admin Assist Engine – orchestration.

Hand-rolled tool-calling loop against the plain Gemini SDK (google-genai). We deliberately do
NOT use google-adk here: its minimum FastAPI requirement (>=0.115) conflicts with this app's
pinned fastapi==0.110.1, and an agent framework buys nothing this ~200-line loop doesn't do.

The loop enforces the module's safety model:
  - Tools are passed to Gemini as FunctionDeclarations only (never Python callables), so the
    SDK is structurally incapable of auto-executing anything — every function call comes back
    to us for inspection first.
  - "safe"-tier tool calls (GET-backed) are executed inline and their results fed back.
  - The first "risky"-tier tool call stops the loop cold: nothing executes, a pending-action
    record is stored, and the owner must confirm it via POST /api/assist/actions/{id}/confirm.

Conversation history is persisted in the `assist_conversations` Mongo collection (plain
user/assistant text turns) — no agent-framework session service, no SQL.

Power-user / test escape hatch: a message of the form
    /run <tool_name> {"arg": "value"}
skips the LLM entirely and goes straight to the tier gate (safe → execute now, risky →
pending action). This keeps the propose→confirm→execute state machine fully testable without
a live (non-deterministic, billable) Gemini call.
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from .tools import TOOL_REGISTRY, Tool

logger = logging.getLogger(__name__)

ASSIST_MODEL = os.environ.get("ASSIST_MODEL", "gemini-2.5-flash")
MAX_TOOL_ROUNDS = 6
HISTORY_LIMIT = 30  # most recent messages fed back to the model


def _now():
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _pending_ttl_seconds() -> int:
    try:
        return int(os.environ.get("ASSIST_PENDING_TTL_SECONDS", "300"))
    except ValueError:
        return 300


SYSTEM_INSTRUCTION = """\
You are the CalibrationOS Assist — the built-in operations copilot for The Calibration Crew, a
mobile ADAS windshield-calibration business in Phoenix, AZ. You are talking to the owner on the
admin dashboard. Be direct, concise, and concrete; use plain language, not corporate filler.

You act through tools. Ground every answer in tool results — never invent job ids, prices,
names, or statuses. When the owner refers to something loosely ("the Camry job", "the Gilbert
shop"), use the read tools (list_jobs, list_shops, list_contractors, list_partner_contacts...)
to resolve it to a specific record first, and if more than one plausibly matches, ask which one
they mean instead of guessing.

Some tools perform real actions (dispatching, cancelling, rescheduling, changing prices,
sending real messages to partners). When you call one of those, the system does NOT execute it —
it shows the owner a confirmation card and waits for their explicit approval. So don't ask
"should I go ahead?" in text before calling an action tool; resolve the details, then make the
tool call, and the confirmation step handles consent. Propose one action at a time.

Dates/times are Phoenix, AZ (America/Phoenix, no DST). The business runs Monday–Saturday with a
West zone (morning) and East zone (afternoon)."""


class AssistError(Exception):
    pass


def _build_gemini_tools():
    """Build FunctionDeclaration-only tools — the SDK can't auto-execute declarations."""
    from google.genai import types
    decls = [
        types.FunctionDeclaration(
            name=t.name, description=t.description, parameters=t.parameters)
        for t in TOOL_REGISTRY.values()
    ]
    return [types.Tool(function_declarations=decls)]


def _history_to_contents(messages: list) -> list:
    """Convert persisted {role, text} turns into genai Content objects."""
    from google.genai import types
    contents = []
    for m in messages[-HISTORY_LIMIT:]:
        role = "user" if m["role"] == "user" else "model"
        text = m.get("text") or ""
        if not text:
            continue
        contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
    return contents


async def _load_conversation(db, owner_id: str, conversation_id: Optional[str]) -> dict:
    if conversation_id:
        convo = await db.assist_conversations.find_one(
            {"id": conversation_id, "owner_id": owner_id}, {"_id": 0})
        if convo:
            return convo
    convo = {
        "id": conversation_id or str(uuid.uuid4()),
        "owner_id": owner_id,
        "messages": [],
        "created_at": _iso(_now()),
        "updated_at": _iso(_now()),
    }
    await db.assist_conversations.insert_one({**convo})
    return convo


async def _append_message(db, conversation_id: str, role: str, text: str,
                          tool_name: Optional[str] = None, extra: Optional[dict] = None):
    msg = {"role": role, "text": text, "at": _iso(_now())}
    if tool_name:
        msg["tool_name"] = tool_name
    if extra:
        msg.update(extra)
    await db.assist_conversations.update_one(
        {"id": conversation_id},
        {"$push": {"messages": msg}, "$set": {"updated_at": _iso(_now())}})
    return msg


async def _create_pending_action(db, owner_id: str, conversation_id: str,
                                 tool: Tool, args: dict) -> dict:
    pending = {
        "id": str(uuid.uuid4()),
        "owner_id": owner_id,
        "conversation_id": conversation_id,
        "tool_name": tool.name,
        "args": args,
        "summary": tool.summary(args),
        "status": "pending",
        "created_at": _iso(_now()),
        "expires_at": _iso(_now() + timedelta(seconds=_pending_ttl_seconds())),
        "result": None,
    }
    await db.assist_pending_actions.insert_one({**pending})
    return pending


async def _log_action(db, owner_id: str, action_type: str, target_id: str,
                      tool_name: Optional[str] = None, status: str = "ok",
                      detail: Optional[str] = None):
    """Same ai_action_log collection Module 9 writes to — one shared HITL audit trail."""
    await db.ai_action_log.insert_one({
        "id": str(uuid.uuid4()), "actor_type": "owner", "actor_id": owner_id,
        "action_type": action_type, "target_type": "assist_action", "target_id": target_id,
        "channel": tool_name, "status": status, "detail": detail,
        "created_at": _iso(_now()),
    })


def _pending_payload(pending: dict) -> dict:
    return {k: pending[k] for k in
            ("id", "tool_name", "args", "summary", "status", "expires_at")}


def _parse_slash_run(message: str):
    """Parse the '/run tool_name {json args}' escape hatch. Returns (tool, args) or None."""
    if not message.strip().startswith("/run"):
        return None
    rest = message.strip()[len("/run"):].strip()
    if not rest:
        raise AssistError("Usage: /run <tool_name> {\"arg\": \"value\"}")
    parts = rest.split(None, 1)
    tool_name = parts[0]
    tool = TOOL_REGISTRY.get(tool_name)
    if not tool:
        raise AssistError(f"Unknown tool '{tool_name}'. Available: {', '.join(sorted(TOOL_REGISTRY))}")
    args = {}
    if len(parts) > 1 and parts[1].strip():
        try:
            args = json.loads(parts[1])
        except json.JSONDecodeError as e:
            raise AssistError(f"Args must be valid JSON: {e}")
        if not isinstance(args, dict):
            raise AssistError("Args must be a JSON object")
    return tool, args


async def run_turn(db, token: str, owner: dict, message: str,
                   conversation_id: Optional[str] = None) -> dict:
    """One assistant turn. Returns one of:
      {"kind": "text",           "conversation_id", "text"}
      {"kind": "pending_action", "conversation_id", "text", "pending_action": {...}}
    """
    owner_id = owner["id"]
    convo = await _load_conversation(db, owner_id, conversation_id)
    cid = convo["id"]
    await _append_message(db, cid, "user", message)

    # ---- deterministic escape hatch: /run <tool> {args} — no LLM involved ----
    slash = _parse_slash_run(message)
    if slash:
        tool, args = slash
        if tool.tier == "safe":
            result = await tool.execute(token, args)
            text = f"Ran {tool.name}: " + json.dumps(result, default=str)[:4000]
            await _append_message(db, cid, "assistant", text, tool_name=tool.name)
            return {"kind": "text", "conversation_id": cid, "text": text}
        pending = await _create_pending_action(db, owner_id, cid, tool, args)
        await _log_action(db, owner_id, "assist_propose", pending["id"], tool.name)
        text = f"Needs your confirmation: {pending['summary']}"
        await _append_message(db, cid, "assistant", text, tool_name=tool.name,
                              extra={"pending_action_id": pending["id"]})
        return {"kind": "pending_action", "conversation_id": cid, "text": text,
                "pending_action": _pending_payload(pending)}

    # ---- normal path: Gemini tool-calling loop ----
    from google import genai
    from google.genai import types

    client = genai.Client()  # reads GOOGLE_API_KEY from env
    contents = _history_to_contents(convo["messages"])
    contents.append(types.Content(role="user", parts=[types.Part(text=message)]))
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=_build_gemini_tools(),
        temperature=0.2,
    )

    for _round in range(MAX_TOOL_ROUNDS):
        response = await client.aio.models.generate_content(
            model=ASSIST_MODEL, contents=contents, config=config)

        calls = response.function_calls or []
        if not calls:
            text = (response.text or "").strip() or "(no response)"
            await _append_message(db, cid, "assistant", text)
            return {"kind": "text", "conversation_id": cid, "text": text}

        # Keep the model's turn (function-call parts) in the running transcript
        if response.candidates and response.candidates[0].content:
            contents.append(response.candidates[0].content)

        function_response_parts = []
        for call in calls:
            tool = TOOL_REGISTRY.get(call.name)
            args = dict(call.args or {})
            if tool is None:
                function_response_parts.append(types.Part.from_function_response(
                    name=call.name, response={"ok": False, "error": "unknown tool"}))
                continue
            if tool.tier == "risky":
                # HITL gate: store the proposal, stop the loop, nothing executes.
                pending = await _create_pending_action(db, owner_id, cid, tool, args)
                await _log_action(db, owner_id, "assist_propose", pending["id"], tool.name)
                lead_in = (response.text or "").strip()
                text = (lead_in + "\n\n" if lead_in else "") + \
                    f"Needs your confirmation: {pending['summary']}"
                await _append_message(db, cid, "assistant", text, tool_name=tool.name,
                                      extra={"pending_action_id": pending["id"]})
                return {"kind": "pending_action", "conversation_id": cid, "text": text,
                        "pending_action": _pending_payload(pending)}
            result = await tool.execute(token, args)
            await _log_action(db, owner_id, "assist_execute", tool.name, tool.name,
                              status="ok" if result.get("ok") else "failed")
            function_response_parts.append(types.Part.from_function_response(
                name=call.name, response=result))

        contents.append(types.Content(role="user", parts=function_response_parts))

    text = ("I hit my per-message tool budget before finishing — try narrowing the request "
            "(e.g. one day or one shop at a time).")
    await _append_message(db, cid, "assistant", text)
    return {"kind": "text", "conversation_id": cid, "text": text}


async def execute_pending_action(db, token: str, owner: dict, pending: dict) -> dict:
    """Execute a confirmed pending action, then have the model phrase the outcome (with a
    deterministic fallback so confirms still work if the LLM call fails/is unavailable)."""
    owner_id = owner["id"]
    tool = TOOL_REGISTRY.get(pending["tool_name"])
    if tool is None:
        raise AssistError(f"Tool '{pending['tool_name']}' no longer exists")

    result = await tool.execute(token, pending["args"])
    status = "ok" if result.get("ok") else "failed"
    await db.assist_pending_actions.update_one(
        {"id": pending["id"]},
        {"$set": {"status": "executed" if result.get("ok") else "failed",
                  "result": result, "executed_at": _iso(_now())}})
    await _log_action(db, owner_id, "assist_execute", pending["id"], tool.name, status=status)

    fallback = (f"Done — {pending['summary']}." if result.get("ok")
                else f"That didn't go through — {pending['summary']} failed: "
                     f"{result.get('error', 'unknown error')} (HTTP {result.get('status', '?')}).")
    text = fallback
    try:
        from google import genai
        from google.genai import types
        client = genai.Client()
        convo = await db.assist_conversations.find_one(
            {"id": pending["conversation_id"]}, {"_id": 0}) or {"messages": []}
        contents = _history_to_contents(convo["messages"])
        contents.append(types.Content(role="user", parts=[types.Part(text=(
            f"[system] The owner APPROVED the proposed action '{pending['summary']}' and it was "
            f"executed. Raw result: {json.dumps(result, default=str)[:3000]}\n"
            "Tell the owner the outcome in one or two short sentences."))]))
        response = await client.aio.models.generate_content(
            model=ASSIST_MODEL, contents=contents,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION,
                                                temperature=0.2))
        if (response.text or "").strip():
            text = response.text.strip()
    except Exception as e:  # LLM phrasing is best-effort; the action itself already ran
        logger.warning(f"[ASSIST] outcome phrasing failed, using fallback: {e}")

    await _append_message(db, pending["conversation_id"], "assistant", text,
                          tool_name=tool.name)
    return {"kind": "text", "conversation_id": pending["conversation_id"],
            "text": text, "result": result}
