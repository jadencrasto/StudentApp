"""
Chat service — powers the student chatbot.

Two modes
  • general  – answer any academic question the student asks
  • viva     – generate & ask viva-voce questions on uploaded documents / assignments,
               then evaluate the student's answers
"""
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chat import ChatConversation, ChatMessage
from app.models.document_alert import Document
from app.models.assignment import Assignment
from app.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  System prompts
# ---------------------------------------------------------------------------

GENERAL_SYSTEM = (
    "You are SAIS — a friendly, knowledgeable AI study assistant for college students. "
    "Answer questions clearly and concisely. Use examples when helpful. "
    "If the student asks about something outside academics, politely redirect to study topics. "
    "Format your answers using Markdown when it improves readability (bullet points, headings, code blocks, etc.)."
)

VIVA_SYSTEM = (
    "You are a strict but fair university examiner conducting a viva-voce (oral exam). "
    "You have access to the student's document/assignment content below. "
    "Ask thought-provoking questions that test understanding, not memorization. "
    "After the student answers, provide brief feedback: whether they are correct, "
    "partially correct, or wrong, and give the ideal answer. Then ask the next question. "
    "Be encouraging but rigorous."
)

VIVA_GENERATE_PROMPT = (
    "Based on the following document content, generate {n} viva-voce questions that test "
    "deep understanding. Return ONLY a numbered list of questions, nothing else.\n\n"
    "DOCUMENT CONTENT:\n{content}\n\n"
    "QUESTIONS:"
)


class ChatService:
    def __init__(self):
        self.ollama = OllamaClient()

    # ------------------------------------------------------------------
    #  Conversation CRUD
    # ------------------------------------------------------------------

    async def create_conversation(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        mode: str = "general",
        document_id: uuid.UUID | None = None,
        title: str | None = None,
    ) -> ChatConversation:
        if not title:
            title = "Viva Session" if mode == "viva" else "New Chat"
        conv = ChatConversation(
            user_id=user_id,
            mode=mode,
            document_id=document_id,
            title=title,
        )
        db.add(conv)
        await db.commit()
        await db.refresh(conv)
        return conv

    async def list_conversations(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> List[ChatConversation]:
        result = await db.execute(
            select(ChatConversation)
            .where(ChatConversation.user_id == user_id)
            .order_by(ChatConversation.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_conversation(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ChatConversation | None:
        result = await db.execute(
            select(ChatConversation)
            .options(
                selectinload(ChatConversation.messages),
                selectinload(ChatConversation.document),
            )
            .where(
                ChatConversation.id == conversation_id,
                ChatConversation.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def delete_conversation(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        conv = await self.get_conversation(db, conversation_id, user_id)
        if not conv:
            return False
        await db.delete(conv)
        await db.commit()
        return True

    # ------------------------------------------------------------------
    #  Send message & get AI reply
    # ------------------------------------------------------------------

    async def send_message(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        user_message: str,
    ) -> ChatMessage:
        conv = await self.get_conversation(db, conversation_id, user_id)
        if not conv:
            raise ValueError("Conversation not found")

        # 1. Persist user message
        user_msg = ChatMessage(
            conversation_id=conv.id,
            role="user",
            content=user_message,
        )
        db.add(user_msg)
        await db.flush()

        # 2. Build prompt with history
        prompt = await self._build_prompt(conv, user_message)

        # 3. Call Ollama
        ai_text = await self.ollama.generate(prompt)
        if not ai_text:
            ai_text = "Sorry, I wasn't able to generate a response. Please try again."

        # 4. Persist assistant message
        ai_msg = ChatMessage(
            conversation_id=conv.id,
            role="assistant",
            content=ai_text.strip(),
        )
        db.add(ai_msg)

        # 5. Auto-title the conversation from first message
        if len(conv.messages) <= 1:  # only the system/first user msg
            conv.title = user_message[:80] + ("…" if len(user_message) > 80 else "")

        conv.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(ai_msg)
        return ai_msg

    # ------------------------------------------------------------------
    #  Viva: start a viva session with generated questions
    # ------------------------------------------------------------------

    async def start_viva(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        num_questions: int = 5,
    ) -> ChatConversation:
        """Create a viva conversation and generate initial questions."""
        # Fetch document content (verify ownership)
        result = await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.user_id == user_id,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError("Document not found or you don't have access")

        content = doc.raw_text or ""
        if not content:
            raise ValueError("Document has no extracted text to base viva on")

        # Truncate to ~6000 chars to stay within context window
        content = content[:6000]

        # Create conversation
        doc_name = doc.original_filename or "Document"
        conv = await self.create_conversation(
            db, user_id, mode="viva", document_id=document_id,
            title=f"Viva — {doc_name}",
        )

        # Generate viva questions via Ollama
        gen_prompt = VIVA_GENERATE_PROMPT.format(n=num_questions, content=content)
        questions_text = await self.ollama.generate(gen_prompt)

        if not questions_text:
            questions_text = "I couldn't generate questions right now. Please try again."

        # Save as the first assistant message
        intro = (
            f"**Viva Session — {doc_name}**\n\n"
            "I've prepared questions based on your document. "
            "Answer each one and I'll give you feedback.\n\n"
            f"{questions_text.strip()}\n\n"
            "**Let's start!** Answer Question 1."
        )
        ai_msg = ChatMessage(conversation_id=conv.id, role="assistant", content=intro)
        db.add(ai_msg)
        await db.commit()

        # Reload with messages
        conv = await self.get_conversation(db, conv.id, user_id)
        return conv

    # ------------------------------------------------------------------
    #  Internal helpers
    # ------------------------------------------------------------------

    async def _build_prompt(self, conv: ChatConversation, new_message: str) -> str:
        """Build a full prompt including system instructions + conversation history."""
        parts: list[str] = []

        # System prompt
        if conv.mode == "viva":
            parts.append(f"[System]\n{VIVA_SYSTEM}")
            # Include document context if available
            if conv.document:
                doc_text = (conv.document.raw_text or "")[:6000]
                if doc_text:
                    parts.append(f"\n[Document Content]\n{doc_text}")
        else:
            parts.append(f"[System]\n{GENERAL_SYSTEM}")

        # Conversation history (last 20 messages for context window management)
        history = (conv.messages or [])[-20:]
        for msg in history:
            role_label = "Student" if msg.role == "user" else "SAIS"
            parts.append(f"\n[{role_label}]\n{msg.content}")

        # Current user message
        parts.append(f"\n[Student]\n{new_message}")
        parts.append("\n[SAIS]\n")

        return "\n".join(parts)
