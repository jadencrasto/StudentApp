from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Sequence

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integrations import CollegeEvent

logger = logging.getLogger(__name__)


def _to_payload(event: CollegeEvent) -> dict:
    return {
        "id": str(event.id),
        "institution_id": str(event.institution_id) if event.institution_id else None,
        "college": event.college,
        "event_name": event.event_name,
        "event_type": event.event_type,
        "date": event.event_date,
        "semester": event.semester,
        "department": event.department,
        "source_url": event.source_url,
        "is_hidden": event.is_hidden,
        "is_manual": event.is_manual,
    }


def _normalize_title(val: str | None) -> str:
    if not val:
        return ""
    return re.sub(r"\s+", " ", val.strip()).lower()


def _normalize_date(val: str | None) -> str:
    if not val:
        return ""
    return val.strip()


async def save_events_with_fallback(db: AsyncSession, events: Sequence[dict], fallback_path: Path) -> list[dict]:
    persisted: list[dict] = []
    if not events:
        return persisted

    try:
        colleges = {item.get("college") for item in events if item.get("college")}
        inst_ids = {item.get("institution_id") for item in events if item.get("institution_id")}

        conditions = []
        if colleges:
            conditions.append(CollegeEvent.college.in_(colleges))
        if inst_ids:
            conditions.append(CollegeEvent.institution_id.in_(inst_ids))

        existing_events_query = select(CollegeEvent)
        if conditions:
            existing_events_query = existing_events_query.where(or_(*conditions))

        res = await db.execute(existing_events_query)
        existing_rows = res.scalars().all()

        known_keys = set()
        for row in existing_rows:
            inst_key = str(row.institution_id) if row.institution_id else ""
            college_key = (row.college or "").strip().lower() if not row.institution_id else ""
            title_key = _normalize_title(row.event_name)
            date_key = _normalize_date(row.event_date)
            known_keys.add((inst_key, college_key, title_key, date_key))

        for item in events:
            inst_key = str(item.get("institution_id")) if item.get("institution_id") else ""
            college_key = (item.get("college") or "").strip().lower() if not item.get("institution_id") else ""
            title_key = _normalize_title(item.get("event_name"))
            date_key = _normalize_date(item.get("date") or item.get("event_date"))

            key = (inst_key, college_key, title_key, date_key)
            if key in known_keys:
                persisted.append(item)
                continue

            known_keys.add(key)
            try:
                async with db.begin_nested():
                    new_ev = CollegeEvent(
                        institution_id=item.get("institution_id"),
                        college=item.get("college", ""),
                        event_name=item.get("event_name", ""),
                        event_type=item.get("event_type", "Event"),
                        event_date=item.get("date") or item.get("event_date"),
                        semester=item.get("semester"),
                        department=item.get("department"),
                        source_url=item.get("source_url", ""),
                        is_manual=bool(item.get("is_manual", False)),
                        is_hidden=bool(item.get("is_hidden", False)),
                    )
                    db.add(new_ev)
                    await db.flush()
                persisted.append(item)
            except IntegrityError:
                logger.debug("Duplicate event skipped quietly via DB unique index: %s", key)
                persisted.append(item)
                continue

        return persisted
    except Exception as exc:
        logger.warning("Error saving college events, using fallback file: %s", exc)
        fallback_path.parent.mkdir(parents=True, exist_ok=True)
        fallback_path.write_text(json.dumps(list(events), indent=2, default=str), encoding="utf-8")
        return list(events)
