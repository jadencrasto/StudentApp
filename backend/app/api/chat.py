"""
Chat / Chatbot API endpoints.

POST   /chat/conversations              — create a new conversation
GET    /chat/conversations              — list conversations
GET    /chat/conversations/{id}         — get conversation with messages
DELETE /chat/conversations/{id}         — delete conversation
POST   /chat/conversations/{id}/messages — send message & get AI reply
POST   /chat/viva                       — start a viva session on a document
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.schemas import (
    ChatConversationOut,
    ChatConversationDetailOut,
    ChatMessageOut,
    ChatCreateRequest,
    ChatSendRequest,
    VivaStartRequest,
)
from app.services.ai_provider import AIConfigError, AIServiceUnavailableError
from app.services.chat_service import ChatService
from app.services.rate_limiter import check_ai_rate_limit

router = APIRouter(prefix="/chat", tags=["Chat"])
chat_service = ChatService()


# ── Create conversation ──────────────────────────────────────

@router.post("/conversations", response_model=ChatConversationOut, status_code=201)
async def create_conversation(
    body: ChatCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await chat_service.create_conversation(
        db,
        user_id=user.id,
        mode=body.mode,
        document_id=body.document_id,
        title=body.title,
    )
    return conv


# ── List conversations ───────────────────────────────────────

@router.get("/conversations", response_model=list[ChatConversationOut])
async def list_conversations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await chat_service.list_conversations(db, user.id)


# ── Get conversation detail ──────────────────────────────────

@router.get("/conversations/{conversation_id}", response_model=ChatConversationDetailOut)
async def get_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await chat_service.get_conversation(db, conversation_id, user.id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    return conv


# ── Delete conversation ──────────────────────────────────────

@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await chat_service.delete_conversation(db, conversation_id, user.id)
    if not deleted:
        raise HTTPException(404, "Conversation not found")


# ── Send message ─────────────────────────────────────────────

@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ChatMessageOut,
)
async def send_message(
    conversation_id: UUID,
    body: ChatSendRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    check_ai_rate_limit(user.id)
    try:
        ai_msg = await chat_service.send_message(
            db, conversation_id, user.id, body.message,
        )
        return ai_msg
    except AIConfigError as e:
        raise HTTPException(503, str(e))
    except AIServiceUnavailableError:
        raise HTTPException(503, "The AI service is temporarily unavailable. Please try again in a few moments.")
    except ValueError as e:
        raise HTTPException(404, str(e))


# ── Start viva session ───────────────────────────────────────

@router.post("/viva", response_model=ChatConversationDetailOut, status_code=201)
async def start_viva(
    body: VivaStartRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    check_ai_rate_limit(user.id)
    try:
        conv = await chat_service.start_viva(
            db, user.id, body.document_id, body.num_questions,
        )
        return conv
    except AIConfigError as e:
        raise HTTPException(503, str(e))
    except AIServiceUnavailableError:
        raise HTTPException(503, "The AI service is temporarily unavailable. Please try again in a few moments.")
    except ValueError as e:
        raise HTTPException(400, str(e))
