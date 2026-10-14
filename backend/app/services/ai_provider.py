from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, TypeVar

import anyio
from google import genai
from google.genai import types

from app.config import settings
from app.core.rate_limiter import quota_cooldown_tracker
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


def _extract_google_error_info(exc: Exception) -> tuple[int | None, str | None, str]:
    """
    Extract (http_status_code, google_status, google_message) from an exception.
    Ensures API keys and user message content are NEVER leaked into logs.
    """
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    status = getattr(exc, "status", None)
    message = getattr(exc, "message", None) or str(exc)

    resp_json = getattr(exc, "response_json", None)
    if isinstance(resp_json, dict) and "error" in resp_json:
        err_obj = resp_json["error"]
        if code is None and "code" in err_obj:
            code = err_obj["code"]
        if status is None and "status" in err_obj:
            status = err_obj["status"]
        if not getattr(exc, "message", None) and "message" in err_obj:
            message = err_obj["message"]

    if code is None:
        m = re.search(r"\b(400|401|403|404|429|500|502|503|504)\b", str(exc))
        if m:
            code = int(m.group(1))

    if status is None:
        known_statuses = [
            "INVALID_ARGUMENT",
            "PERMISSION_DENIED",
            "NOT_FOUND",
            "RESOURCE_EXHAUSTED",
            "UNAVAILABLE",
            "INTERNAL",
            "FAILED_PRECONDITION",
        ]
        for ks in known_statuses:
            if ks in str(exc):
                status = ks
                break

    # Strip any potential API key strings (e.g. AIza... or AQ....)
    clean_msg = re.sub(r"(AIza[0-9A-Za-z-_]{20,}|AQ\.[0-9A-Za-z-_]{20,})", "[REDACTED_KEY]", str(message))
    for k in (
        getattr(settings, "GEMINI_API_KEY_CHAT", None),
        getattr(settings, "GEMINI_API_KEY_TIMETABLE", None),
        getattr(settings, "GEMINI_API_KEY", None),
    ):
        if k and str(k).strip():
            clean_msg = clean_msg.replace(str(k).strip(), "[REDACTED_KEY]")
    return code, status, clean_msg


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

    def _is_retryable_error(self, code: int | None, status: str | None, exc: Exception) -> bool:
        """Retry ONLY on 503 UNAVAILABLE (busy). Explicitly never retry on 429 daily quota or 4xx."""
        if code in (400, 401, 403, 404, 429):
            return False
        if status in ("RESOURCE_EXHAUSTED", "INVALID_ARGUMENT", "PERMISSION_DENIED", "NOT_FOUND"):
            return False
        exc_str = str(exc).lower()
        if "429" in exc_str or "quota" in exc_str or "resource_exhausted" in exc_str:
            return False
        if code == 503 or status == "UNAVAILABLE":
            return True
        if "503" in exc_str or "unavailable" in exc_str:
            return True
        return False

    async def _execute_with_retry_and_timeout(self, sync_func: Callable[[], T]) -> T:
        """
        Execute sync AI function in thread with ~30s timeout.
        Retries once ONLY on 503 (wait ~3 seconds). Never retries on 429 daily quota.
        Logs status code, Google status, and Google error message without leaking keys/messages.
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
                code, status, msg = _extract_google_error_info(exc)
                logger.warning(
                    "Gemini API error (attempt %d/%d): HTTP %s | status: %s | message: %s",
                    attempt,
                    attempts,
                    code,
                    status,
                    msg,
                )

                if self._is_retryable_error(code, status, exc) and attempt < attempts:
                    logger.warning("Gemini 503 UNAVAILABLE (attempt %d/%d). Retrying in ~3s...", attempt, attempts)
                    await asyncio.sleep(3.0)
                    continue

                # Non-retryable or retries exhausted: Map to appropriate friendly error
                if code == 400 or status == "INVALID_ARGUMENT":
                    raise AIServiceUnavailableError(f"Invalid request to AI service: {msg}")
                elif code in (401, 403) or status == "PERMISSION_DENIED":
                    raise AIConfigError("Gemini API key is invalid or lacks permissions. Please check GEMINI_API_KEY_CHAT.")
                elif code == 404 or status == "NOT_FOUND":
                    raise AIConfigError(f"Gemini model is not available. Please verify GEMINI_MODEL in .env.")
                elif code == 429 or status == "RESOURCE_EXHAUSTED" or "429" in str(exc).lower() or "quota" in str(exc).lower() or "resource_exhausted" in str(exc).lower():
                    quota_cooldown_tracker.set_cooldown(300.0)
                    raise AIServiceUnavailableError("AI daily quota reached. Please try again tomorrow.")
                elif code == 503 or status == "UNAVAILABLE" or "503" in str(exc).lower() or "unavailable" in str(exc).lower():
                    raise AIServiceUnavailableError("Google's AI is busy right now. Try again in a few minutes, or start from scratch.")
                else:
                    raise AIServiceUnavailableError("The AI service is temporarily unavailable.") from exc

    async def _execute_async_with_retry_and_timeout(self, async_func: Callable[[], Any]) -> Any:
        """
        Execute async AI function with ~30s timeout and a single retry on 503 (wait ~3 seconds). Never retries on 429 daily quota.
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
                code, status, msg = _extract_google_error_info(exc)
                logger.warning(
                    "Async AI API error (attempt %d/%d): HTTP %s | status: %s | message: %s",
                    attempt,
                    attempts,
                    code,
                    status,
                    msg,
                )
                if self._is_retryable_error(code, status, exc) and attempt < attempts:
                    logger.warning("Transient async AI error (HTTP %s). Retrying in ~3s...", code)
                    await asyncio.sleep(3.0)
                    continue
                if code in (401, 403) or status == "PERMISSION_DENIED":
                    raise AIConfigError("AI credentials invalid or unauthorized.")
                if code == 429 or status == "RESOURCE_EXHAUSTED" or "429" in str(exc).lower() or "quota" in str(exc).lower() or "resource_exhausted" in str(exc).lower():
                    quota_cooldown_tracker.set_cooldown(300.0)
                    raise AIServiceUnavailableError("AI daily quota reached. Please try again tomorrow.")
                elif code == 503 or status == "UNAVAILABLE" or "503" in str(exc).lower() or "unavailable" in str(exc).lower():
                    raise AIServiceUnavailableError("Google's AI is busy right now. Try again in a few minutes, or start from scratch.")
                raise AIServiceUnavailableError("The AI service is temporarily unavailable.") from exc

    # -------------------------------------------------------------------------
    # Multiturn Chat Generation
    # -------------------------------------------------------------------------

    def build_gemini_contents(self, messages: List[Dict[str, str]]) -> List[types.Content]:
        """
        Build well-formed types.Content objects complying with Gemini multi-turn specs:
        - Roles mapped strictly to 'user' and 'model'
        - Empty messages stripped and omitted
        - Adjacent turns of identical roles merged
        - Turn 1 guaranteed to be 'user'
        - Final turn guaranteed to be 'user'
        """
        contents: List[types.Content] = []
        for m in messages:
            text = (m.get("content") or "").strip()
            if not text:
                continue
            raw_role = (m.get("role") or "").lower()
            role = "user" if raw_role in ("user", "student") else "model"

            # Merge adjacent identical roles to preserve turn alternation
            if contents and contents[-1].role == role:
                prev_text = contents[-1].parts[0].text
                contents[-1] = types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=f"{prev_text}\n\n{text}")],
                )
            else:
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=text)],
                    )
                )

        if not contents:
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text="Hello")]))

        # Gemini requires first turn to be 'user'
        if contents[0].role == "model":
            contents.insert(0, types.Content(role="user", parts=[types.Part.from_text(text="Start session")]))

        # Gemini requires the final turn to be 'user' (awaiting model response)
        if contents[-1].role != "user":
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text="Please continue.")]))

        return contents

    async def generate_chat(
        self,
        messages: List[Dict[str, str]],
        system_instruction: str | None = None,
    ) -> str:
        """Generate assistant reply from structured multi-turn conversation messages."""
        if self.provider == "ollama":
            return await self._generate_chat_ollama(messages, system_instruction)
        return await self._generate_chat_gemini(messages, system_instruction)

    async def _generate_chat_gemini(
        self,
        messages: List[Dict[str, str]],
        system_instruction: str | None = None,
    ) -> str:
        gemini_contents = self.build_gemini_contents(messages)

        def _call() -> str:
            client = self._get_gemini_client()
            model = self.model_name
            config = types.GenerateContentConfig()
            if system_instruction and system_instruction.strip():
                config.system_instruction = system_instruction.strip()

            response = client.models.generate_content(
                model=model,
                contents=gemini_contents,
                config=config,
            )
            if not response or not response.text or not response.text.strip():
                raise AIServiceUnavailableError("Empty response received from AI model.")
            return response.text.strip()

        return await self._execute_with_retry_and_timeout(_call)

    async def _generate_chat_ollama(
        self,
        messages: List[Dict[str, str]],
        system_instruction: str | None = None,
    ) -> str:
        parts: List[str] = []
        if system_instruction:
            parts.append(f"[System]\n{system_instruction}")
        for m in messages:
            role_label = "Student" if m.get("role") == "user" else "SAIS"
            text = (m.get("content") or "").strip()
            if text:
                parts.append(f"\n[{role_label}]\n{text}")
        parts.append("\n[SAIS]\n")
        full_prompt = "\n".join(parts)

        async def _call() -> str:
            text = await self.ollama_client.generate(full_prompt)
            if not text or not text.strip():
                raise AIServiceUnavailableError("Empty response received from Ollama.")
            return text.strip()

        return await self._execute_async_with_retry_and_timeout(_call)

    # -------------------------------------------------------------------------
    # Single Prompt Text Generation
    # -------------------------------------------------------------------------

    async def generate_text(self, prompt: str, system_instruction: str | None = None) -> str:
        """Generate text from a single prompt string."""
        safe_prompt = (prompt or "").strip()
        if not safe_prompt:
            raise AIServiceUnavailableError("Prompt cannot be empty.")
        if self.provider == "ollama":
            return await self._generate_text_ollama(safe_prompt, system_instruction)
        return await self._generate_text_gemini(safe_prompt, system_instruction)

    async def _generate_text_gemini(self, prompt: str, system_instruction: str | None = None) -> str:
        def _call() -> str:
            client = self._get_gemini_client()
            model = self.model_name
            config = types.GenerateContentConfig()
            if system_instruction and system_instruction.strip():
                config.system_instruction = system_instruction.strip()

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
