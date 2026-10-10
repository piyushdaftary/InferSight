"""Copilot routes.

POST   /api/v1/copilot/chat              — send a message, get a response
GET    /api/v1/copilot/chat/{session_id} — retrieve chat history
DELETE /api/v1/copilot/chat/{session_id} — clear a session
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from infersight.api.auth import require_api_key

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    history: list[ChatMessage]


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    body: ChatRequest,
    _: None = Depends(require_api_key),
) -> ChatResponse:
    """Send a message to the AI copilot and get a response."""
    from infersight.config import InferSightConfig
    from infersight.storage.base import StorageBackend

    config: InferSightConfig | None = getattr(request.app.state, "config", None)
    storage: StorageBackend | None = getattr(request.app.state, "storage", None)

    if config is None or not config.copilot.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Copilot is not enabled. Set copilot.enabled=true in your config.",
        )
    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage backend not available",
        )

    session_id = body.session_id or str(uuid.uuid4())
    await storage.write_copilot_message(session_id, "user", body.message)

    raw_history = await storage.query_copilot_history(
        session_id, limit=config.copilot.max_context_messages
    )
    messages = [ChatMessage(role=m["role"], content=m["content"]) for m in raw_history]

    import litellm

    api_key = config.copilot.api_key.get_secret_value()
    lm_messages = [{"role": m.role, "content": m.content} for m in messages]

    try:
        kwargs: dict[str, object] = {
            "model": config.copilot.model,
            "messages": lm_messages,
            "max_tokens": config.copilot.max_tokens,
            "temperature": config.copilot.temperature,
        }
        if api_key:
            kwargs["api_key"] = api_key
        if config.copilot.base_url:
            kwargs["base_url"] = config.copilot.base_url

        response = await litellm.acompletion(**kwargs)
        reply: str = response.choices[0].message.content or ""
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM call failed: {exc}",
        ) from exc

    await storage.write_copilot_message(session_id, "assistant", reply)
    messages.append(ChatMessage(role="assistant", content=reply))

    return ChatResponse(session_id=session_id, reply=reply, history=messages)


@router.get("/chat/{session_id}", response_model=list[ChatMessage])
async def get_chat_history(
    session_id: str,
    request: Request,
    _: None = Depends(require_api_key),
) -> list[ChatMessage]:
    """Retrieve all messages for a copilot session."""
    from infersight.storage.base import StorageBackend

    storage: StorageBackend | None = getattr(request.app.state, "storage", None)
    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage backend not available",
        )
    raw = await storage.query_copilot_history(session_id)
    return [ChatMessage(role=m["role"], content=m["content"]) for m in raw]


@router.delete("/chat/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_chat_session(
    session_id: str,
    request: Request,
    _: None = Depends(require_api_key),
) -> None:
    """Clear all messages for a copilot session."""
    from infersight.storage.base import StorageBackend

    storage: StorageBackend | None = getattr(request.app.state, "storage", None)
    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage backend not available",
        )
    await storage.write_copilot_message(session_id, "system", "__cleared__")
