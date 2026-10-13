from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Callable, Dict, Optional, TypeVar

import anyio
from google import genai
from google.genai import types

from app.config import settings
from app.services.ollama_client import ollama_client

logger = logging.getLogger(__name__)

T = TypeVar("T")


class AIProviderError(Exception):
    """Base exception for AI provider issues."""
    pass


class AIConfigError(AIProviderError):
    """Configuration error, such as a missing API key or missing model configuration."""
    pass


class AIServiceUnavailableError(AIProviderError):
    """Service error indicating timeout, rate-limiting, or temporary server unreachability."""
    pass


class AIProvider:
    """
    Unified AI service supporting Google Gemini (default) and Ollama.
    Switches via AI_PROVIDER in .env.
    """

    def __init__(self) -> None:
        self.ollama_client = ollama_client

    @property
    def provider(self) -> str:
        return (getattr(settings, "AI_PROVIDER", "gemini") or "gemini").strip().lower()

    @property
    def model_name(self) -> str:
        model = getattr(settings, "GEMINI_MODEL", None)
        if not model or not str(model).strip():
            raise AIConfigError("GEMINI_MODEL is not configured. Please set GEMINI_MODEL in .env.")
        return str(model).strip()

    def get_chat_api_key(self) -> str:
        """Resolve Gemini API key for chat and estimation with fallback. Never logs or leaks key."""
        key = getattr(settings, "GEMINI_API_KEY_CHAT", None) or getattr(settings, "GEMINI_API_KEY", None)
        if not key or not str(key).strip():
            raise AIConfigError(
                "Gemini API key is not configured. Please set GEMINI_API_KEY_CHAT or GEMINI_API_KEY in your environment."
            )
        return str(key).strip()

    def _get_gemini_client(self) -> genai.Client:
        key = self.get_chat_api_key()
        return genai.Client(api_key=key)

    def _is_retryable_error(self, exc: Exception) -> bool:
        """Check if error is a 429 (rate/quota limit) or 503 (service unavailable) error."""
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        if code in (429, 503, 500, 502, 504):
            return True
        exc_str = str(exc).lower()
        retry_keywords = ["429", "503", "resource_exhausted", "unavailable", "high demand", "overloaded", "quota"]
        return any(k in exc_str for k in retry_keywords)

    async def _execute_with_retry_and_timeout(self, sync_func: Callable[[], T]) -> T:
        """
        Execute sync AI function in thread with ~30s timeout and a single retry on 429/503.
        Never logs API keys or message contents.
        """
        attempts = 2
        for attempt in range(1, attempts + 1):
            try:
                return await asyncio.wait_for(
                    anyio.to_thread.run_sync(sync_func),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                logger.warning("AI provider request timed out after 30s (attempt %d/%d)", attempt, attempts)
                if attempt < attempts:
                    await asyncio.sleep(1.0)
                    continue
                raise AIServiceUnavailableError("The AI service timed out. Please try again later.")
            except AIConfigError:
                raise
            except Exception as exc:
                if self._is_retryable_error(exc) and attempt < attempts:
                    logger.warning("Transient AI error (%s) on attempt %d. Retrying once...", type(exc).__name__, attempt)
                    await asyncio.sleep(1.5)
                    continue
                logger.warning("AI provider call failed: %s", type(exc).__name__)
                raise AIServiceUnavailableError("The AI service is temporarily unavailable or over quota.") from exc

    async def _execute_async_with_retry_and_timeout(self, async_func: Callable[[], Any]) -> Any:
        """
        Execute async AI function with ~30s timeout and a single retry on 429/503.
        """
        attempts = 2
        for attempt in range(1, attempts + 1):
            try:
                return await asyncio.wait_for(
                    async_func(),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                logger.warning("AI provider async request timed out after 30s (attempt %d/%d)", attempt, attempts)
                if attempt < attempts:
                    await asyncio.sleep(1.0)
                    continue
                raise AIServiceUnavailableError("The AI service timed out. Please try again later.")
            except AIConfigError:
                raise
            except Exception as exc:
                if self._is_retryable_error(exc) and attempt < attempts:
                    logger.warning("Transient async AI error (%s) on attempt %d. Retrying once...", type(exc).__name__, attempt)
                    await asyncio.sleep(1.5)
                    continue
                logger.warning("Async AI provider call failed: %s", type(exc).__name__)
                raise AIServiceUnavailableError("The AI service is temporarily unavailable or over quota.") from exc

    # -------------------------------------------------------------------------
    # Text Generation (Chat & Viva)
    # -------------------------------------------------------------------------

    async def generate_text(self, prompt: str, system_instruction: str | None = None) -> str:
        """Generate text using configured AI provider (Gemini or Ollama)."""
        if self.provider == "ollama":
            return await self._generate_text_ollama(prompt, system_instruction)
        return await self._generate_text_gemini(prompt, system_instruction)

    async def _generate_text_gemini(self, prompt: str, system_instruction: str | None = None) -> str:
        def _call() -> str:
            client = self._get_gemini_client()
            model = self.model_name
            config = types.GenerateContentConfig()
            if system_instruction:
                config.system_instruction = system_instruction

            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
            if not response or not response.text or not response.text.strip():
                raise AIServiceUnavailableError("Empty response received from AI model.")
            return response.text.strip()

        return await self._execute_with_retry_and_timeout(_call)

    async def _generate_text_ollama(self, prompt: str, system_instruction: str | None = None) -> str:
        full_prompt = prompt
        if system_instruction:
            full_prompt = f"[System]\n{system_instruction}\n\n{prompt}"

        async def _call() -> str:
            text = await self.ollama_client.generate(full_prompt)
            if not text or not text.strip():
                raise AIServiceUnavailableError("Empty response received from Ollama.")
            return text.strip()

        return await self._execute_async_with_retry_and_timeout(_call)

    # -------------------------------------------------------------------------
    # Time Estimation JSON Generation
    # -------------------------------------------------------------------------

    async def estimate_time(self, text: str, task_type: str | None = None) -> Optional[Dict]:
        """
        Estimate assignment completion time using AI (Gemini or Ollama).
        Returns normalized dictionary with analysis_provider set, or None on failure.
        """
        if self.provider == "ollama":
            return await self._estimate_time_ollama(text, task_type)
        return await self._estimate_time_gemini(text, task_type)

    async def _estimate_time_gemini(self, text: str, task_type: str | None = None) -> Optional[Dict]:
        prompt = self._build_estimation_prompt(text, task_type)

        def _call() -> Dict:
            client = self._get_gemini_client()
            model = self.model_name
            config = types.GenerateContentConfig(response_mime_type="application/json")
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
            if not response or not response.text or not response.text.strip():
                raise AIServiceUnavailableError("Empty JSON response received from Gemini.")
            raw_text = response.text.strip()
            raw_clean = re.sub(r"^```(?:json)?\s*", "", raw_text)
            raw_clean = re.sub(r"\s*```$", "", raw_clean)
            return json.loads(raw_clean)

        try:
            parsed = await self._execute_with_retry_and_timeout(_call)
            normalized = self._normalize_estimate_payload(parsed)
            if normalized:
                normalized["analysis_provider"] = "gemini"
            return normalized
        except Exception as exc:
            logger.warning("Gemini time estimation failed (%s)", type(exc).__name__)
            return None

    async def _estimate_time_ollama(self, text: str, task_type: str | None = None) -> Optional[Dict]:
        prompt = self._build_estimation_prompt(text, task_type)

        async def _call() -> Optional[Dict]:
            return await self.ollama_client.generate_json(prompt)

        try:
            parsed = await self._execute_async_with_retry_and_timeout(_call)
            if parsed is None:
                return None
            normalized = self._normalize_estimate_payload(parsed)
            if normalized:
                normalized["analysis_provider"] = "ollama"
            return normalized
        except Exception as exc:
            logger.warning("Ollama time estimation failed (%s)", type(exc).__name__)
            return None

    def _build_estimation_prompt(self, text: str, task_type: str | None = None) -> str:
        return (
            "Analyze this assignment text and estimate completion time. "
            "Return ONLY valid JSON with this exact schema keys: "
            "estimated_minutes (int), estimated_hours (float), reading_time_minutes (int), "
            "work_time_minutes (int), complexity (simple|medium|complex), task_type (string), "
            "question_count (int), has_mathematical_content (bool), has_code_content (bool), "
            "confidence_score (float 0-1), breakdown (string), recommended_sessions (object with "
            "sessions int, minutes_per_session int, recommendation string). "
            "Use realistic student estimates. "
            f"If provided task_type is not empty, treat it as strong hint: {task_type or 'none'}.\n\n"
            f"Assignment text:\n{text[:12000]}"
        )

    def _normalize_estimate_payload(self, payload: Dict) -> Optional[Dict]:
        try:
            estimated_minutes = int(max(1, payload.get("estimated_minutes", 1)))
            reading_time_minutes = int(max(0, payload.get("reading_time_minutes", 0)))
            work_time_minutes = int(max(1, payload.get("work_time_minutes", max(1, estimated_minutes - reading_time_minutes))))
            complexity = str(payload.get("complexity", "medium")).lower()
            if complexity not in {"simple", "medium", "complex"}:
                complexity = "medium"

            confidence_score = float(payload.get("confidence_score", 0.6))
            confidence_score = max(0.0, min(1.0, confidence_score))

            recommended = payload.get("recommended_sessions") or {}
            sessions = int(max(1, recommended.get("sessions", 1)))
            minutes_per_session = int(max(1, recommended.get("minutes_per_session", max(1, estimated_minutes // sessions))))
            recommendation = str(recommended.get("recommendation", "Split work into focused sessions"))

            return {
                "estimated_minutes": estimated_minutes,
                "estimated_hours": round(float(payload.get("estimated_hours", estimated_minutes / 60)), 1),
                "reading_time_minutes": reading_time_minutes,
                "work_time_minutes": work_time_minutes,
                "complexity": complexity,
                "task_type": str(payload.get("task_type", "assignment")),
                "question_count": int(max(0, payload.get("question_count", 0))),
                "has_mathematical_content": bool(payload.get("has_mathematical_content", False)),
                "has_code_content": bool(payload.get("has_code_content", False)),
                "confidence_score": confidence_score,
                "breakdown": str(payload.get("breakdown", "AI analysis completed")),
                "recommended_sessions": {
                    "sessions": sessions,
                    "minutes_per_session": minutes_per_session,
                    "recommendation": recommendation,
                },
            }
        except Exception:
            return None


ai_provider = AIProvider()


def get_ai_provider() -> AIProvider:
    return ai_provider
