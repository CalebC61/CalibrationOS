"""CalibrationOS – Module 8: Admin Assist Engine – API routes.

Same factory pattern as backend/growth/routes.py: server.py imports this module and injects its
already-constructed objects (db, require_owner), so nothing here imports from server.py and no
circular import is possible. Included under /api/assist only when ASSIST_MODULE_ENABLED.

Owner-only. The raw bearer token is re-read from the Authorization header (require_owner has
already validated it) because the tool layer replays it against the app's own /api/* endpoints —
the assistant acts *as the owner*, with exactly the owner's permissions, never more.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .agent import run_turn, execute_pending_action, AssistError, _log_action
from .tools import TOOL_REGISTRY

logger = logging.getLogger(__name__)


class MessageIn(BaseModel):
    message: str
    conversation_id: Optional[str] = None


def _bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    return auth[7:] if auth.lower().startswith("bearer ") else auth


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_assist_router(db, require_owner) -> APIRouter:
    router = APIRouter(prefix="/assist", tags=["assist"])

    @router.post("/message")
    async def post_message(body: MessageIn, request: Request, tech=Depends(require_owner)):
        if not body.message.strip():
            raise HTTPException(status_code=400, detail="Message is empty")
        try:
            return await run_turn(db, _bearer(request), tech, body.message,
                                  conversation_id=body.conversation_id)
        except AssistError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"[ASSIST] turn failed: {e}")
            raise HTTPException(status_code=502,
                                 detail="The assistant couldn't process that — try again.")

    async def _load_pending(action_id: str, owner_id: str) -> dict:
        pending = await db.assist_pending_actions.find_one(
            {"id": action_id, "owner_id": owner_id}, {"_id": 0})
        if not pending:
            raise HTTPException(status_code=404, detail="Pending action not found")
        return pending

    async def _claim_pending(action_id: str, owner_id: str, new_status: str) -> dict:
        """Atomically move a pending action out of 'pending' so racing confirm/cancel requests
        can't both win — exactly one caller's update matches the status:'pending' filter."""
        pending = await _load_pending(action_id, owner_id)
        res = await db.assist_pending_actions.update_one(
            {"id": action_id, "owner_id": owner_id, "status": "pending"},
            {"$set": {"status": new_status}})
        if res.modified_count != 1:
            fresh = await _load_pending(action_id, owner_id)
            raise HTTPException(status_code=400,
                                 detail=f"Action is already {fresh['status']}")
        return pending

    @router.post("/actions/{action_id}/confirm")
    async def confirm_action(action_id: str, request: Request, tech=Depends(require_owner)):
        pending = await _claim_pending(action_id, tech["id"], "confirming")
        if pending["expires_at"] <= _now_iso():
            await db.assist_pending_actions.update_one(
                {"id": action_id}, {"$set": {"status": "expired"}})
            raise HTTPException(status_code=410,
                                 detail="This action expired — ask the assistant again.")
        await _log_action(db, tech["id"], "assist_confirm", action_id, pending["tool_name"])
        try:
            return await execute_pending_action(db, _bearer(request), tech, pending)
        except AssistError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/actions/{action_id}/cancel")
    async def cancel_action(action_id: str, tech=Depends(require_owner)):
        pending = await _claim_pending(action_id, tech["id"], "cancelled")
        await db.assist_pending_actions.update_one(
            {"id": action_id}, {"$set": {"cancelled_at": _now_iso()}})
        await _log_action(db, tech["id"], "assist_cancel", action_id, pending["tool_name"])
        return {"ok": True, "status": "cancelled"}

    @router.get("/conversations/{conversation_id}")
    async def get_conversation(conversation_id: str, tech=Depends(require_owner)):
        convo = await db.assist_conversations.find_one(
            {"id": conversation_id, "owner_id": tech["id"]}, {"_id": 0})
        if not convo:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return convo

    @router.get("/tools")
    async def list_tools(tech=Depends(require_owner)):
        """What the assistant can do — powers a help/capabilities view in the UI."""
        return [{"name": t.name, "tier": t.tier, "description": t.description}
                for t in TOOL_REGISTRY.values()]

    return router
