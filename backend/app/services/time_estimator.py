import json
import re
from typing import Dict, Tuple

import anyio

from app.config import settings
from app.services.ollama_client import ollama_client


class AssignmentTimeEstimator:
    SIMPLE_KEYWORDS = [
        "read", "list", "identify", "name", "state", "define",
        "label", "match", "choose", "select", "recall",
    ]

    MEDIUM_KEYWORDS = [
        "explain", "describe", "discuss", "compare", "contrast",
        "summarize", "interpret", "analyze", "examine", "outline",
    ]

    COMPLEX_KEYWORDS = [
        "design", "develop", "create", "implement", "prove",
        "derive", "research", "evaluate", "critique", "synthesize",
        "formulate", "construct", "debug", "optimize",
    ]

    TASK_TYPE_TIMES = {
        "reading": 30,
        "essay": 120,
        "problem_set": 90,
        "programming": 180,
        "research": 240,
        "project": 480,
        "exam": 120,
        "quiz": 45,
        "lab": 120,
        "presentation": 180,
        "assignment": 90,
        "default": 60,
    }

    def estimate(self, text: str, task_type: str | None = None) -> Dict:
        safe_text = text or ""
        word_count = self._count_words(safe_text)
        reading_time = self._estimate_reading_time(word_count)

        complexity_level, complexity_score = self._analyze_complexity(safe_text)

        resolved_task_type = task_type or self._detect_task_type(safe_text)
        question_count = self._count_questions(safe_text)

        has_math = self._has_mathematical_content(safe_text)
        has_code = self._has_code_content(safe_text)
        technical_multiplier = 1.5 if (has_math or has_code) else 1.0

        base_time = self.TASK_TYPE_TIMES.get(resolved_task_type, self.TASK_TYPE_TIMES["default"])
        if question_count > 0:
            base_time += question_count * 5

        complexity_multipliers = {
            "simple": 1.0,
            "medium": 1.5,
            "complex": 2.5,
        }
        base_time *= complexity_multipliers.get(complexity_level, 1.0)

        work_time = int(base_time * technical_multiplier)
        total_time = work_time + reading_time

        confidence = self._calculate_confidence(
            word_count, question_count, complexity_score, has_math or has_code
        )

        breakdown = self._generate_breakdown(
            reading_time, work_time, question_count, complexity_level
        )

        return {
            "estimated_minutes": total_time,
            "estimated_hours": round(total_time / 60, 1),
            "reading_time_minutes": reading_time,
            "work_time_minutes": work_time,
            "complexity": complexity_level,
            "task_type": resolved_task_type,
            "question_count": question_count,
            "has_mathematical_content": has_math,
            "has_code_content": has_code,
            "confidence_score": confidence,
            "breakdown": breakdown,
            "recommended_sessions": self._recommend_sessions(total_time),
            "analysis_provider": "heuristic",
        }

    def _count_words(self, text: str) -> int:
        words = re.findall(r"\b\w+\b", text.lower())
        return len(words)

    def _estimate_reading_time(self, word_count: int) -> int:
        if word_count < 100:
            return 5
        return max(5, int(word_count / 200))

    def _analyze_complexity(self, text: str) -> Tuple[str, float]:
        text_lower = text.lower()
        simple_count = sum(1 for kw in self.SIMPLE_KEYWORDS if kw in text_lower)
        medium_count = sum(1 for kw in self.MEDIUM_KEYWORDS if kw in text_lower)
        complex_count = sum(1 for kw in self.COMPLEX_KEYWORDS if kw in text_lower)

        total = simple_count + medium_count + complex_count
        if total == 0:
            return "medium", 0.5

        score = (simple_count * 0.3 + medium_count * 0.6 + complex_count * 1.0) / total
        if score < 0.4:
            return "simple", score
        if score < 0.7:
            return "medium", score
        return "complex", score

    def _detect_task_type(self, text: str) -> str:
        text_lower = text.lower()
        patterns = {
            "programming": r"write.*code|implement|program|function|algorithm|debug",
            "essay": r"essay|write.*paper|composition|argue|thesis",
            "research": r"research|investigate|literature review|sources",
            "problem_set": r"solve|problems?\s*\d+|calculate|find the",
            "lab": r"lab|experiment|laboratory|procedure",
            "presentation": r"present|slide|powerpoint|speech",
            "reading": r"read.*chapter|reading assignment",
            "quiz": r"quiz|short answer",
            "exam": r"exam|test|midterm|final",
            "project": r"project|capstone|build",
        }

        for detected_type, pattern in patterns.items():
            if re.search(pattern, text_lower):
                return detected_type
        return "default"

    def _count_questions(self, text: str) -> int:
        pattern1 = re.findall(r"(?:problem|question|q)\s*\d+", text.lower())
        pattern2 = re.findall(r"(\d+)\s*(?:questions?|problems?)", text.lower())
        pattern3 = text.count("?")

        count1 = len(pattern1)
        count2 = int(pattern2[0]) if pattern2 else 0
        count3 = pattern3

        return max(count1, count2, min(count3, 20))

    def _has_mathematical_content(self, text: str) -> bool:
        math_patterns = [
            r"\$.*?\$",
            r"\\[a-z]+\{",
            r"[∫∑∏√±×÷≠≈≤≥∞]",
            r"\b(?:theorem|lemma|proof|equation|formula)\b",
        ]
        for pattern in math_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _has_code_content(self, text: str) -> bool:
        code_patterns = [
            r"```",
            r"def |function |class |import |require\(",
            r"for\s*\(|while\s*\(|if\s*\(",
            r"public |private |void |int |string ",
        ]
        for pattern in code_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _calculate_confidence(
        self,
        word_count: int,
        question_count: int,
        complexity_score: float,
        has_technical: bool,
    ) -> float:
        confidence = 0.5
        if word_count > 500:
            confidence += 0.2
        elif word_count > 200:
            confidence += 0.1

        if question_count > 0:
            confidence += 0.15

        if complexity_score > 0:
            confidence += 0.1

        if has_technical:
            confidence += 0.1

        return min(1.0, confidence)

    def _generate_breakdown(
        self,
        reading_time: int,
        work_time: int,
        question_count: int,
        complexity: str,
    ) -> str:
        parts = []
        if reading_time > 0:
            parts.append(f"📖 Reading: {reading_time} min")
        if question_count > 0:
            parts.append(f"✍️ {question_count} questions (~{question_count * 5} min)")
        parts.append(f"⚙️ Work: {work_time} min ({complexity} complexity)")
        return " | ".join(parts)

    def _recommend_sessions(self, total_minutes: int) -> Dict:
        if total_minutes <= 60:
            return {
                "sessions": 1,
                "minutes_per_session": total_minutes,
                "recommendation": "Complete in one sitting",
            }
        if total_minutes <= 120:
            return {
                "sessions": 2,
                "minutes_per_session": total_minutes // 2,
                "recommendation": "Split into 2 focused sessions",
            }
        sessions = (total_minutes // 60) + 1
        return {
            "sessions": sessions,
            "minutes_per_session": 60,
            "recommendation": f"Break into {sessions} one-hour sessions",
        }


import logging
from app.core.rate_limiter import quota_cooldown_tracker
from app.services.ai_provider import ai_provider

logger = logging.getLogger(__name__)


async def estimate_assignment_time(text: str, task_type: str | None = None) -> Dict:
    safe_text = (text or "").strip()
    if not safe_text:
        estimator = AssignmentTimeEstimator()
        return estimator.estimate("", task_type)

    # If AI daily quota cooldown is active, bypass AI call and immediately use heuristic
    if quota_cooldown_tracker.is_in_cooldown():
        logger.info("AI daily quota cooldown active; skipping AI call and using heuristic estimate.")
        estimator = AssignmentTimeEstimator()
        return estimator.estimate(safe_text, task_type)

    # Try AI estimation via unified AI layer (Gemini / Ollama)
    try:
        ai_result = await ai_provider.estimate_time(safe_text, task_type)
        if ai_result is not None:
            return ai_result
    except Exception as exc:
        logger.warning("AI time estimation failed (%s), falling back to heuristic", type(exc).__name__)

    # Fall back to heuristic estimator
    estimator = AssignmentTimeEstimator()
    return estimator.estimate(safe_text, task_type)


async def _estimate_with_ollama(text: str, task_type: str | None = None) -> Dict | None:
    try:
        prompt = (
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

        parsed = await ollama_client.generate_json(prompt)
        if parsed is None:
            return None

        normalized = _normalize_estimate_payload(parsed)
        if normalized is None:
            return None

        normalized["analysis_provider"] = "ollama"
        return normalized
    except Exception:
        return None


def _normalize_estimate_payload(payload: Dict) -> Dict | None:
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
