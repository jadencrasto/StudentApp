from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.college_events.college_loader import CollegeConfig, CollegeLoader
from app.college_events.content_extractor import fetch_main_text_and_links
from app.college_events.event_parser import parse_events_from_page
from app.college_events.main import fetch_events_for_college
from app.college_events.sitemap_parser import collect_relevant_urls, detect_sitemap
from app.college_events.url_filter import filter_urls
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["College Events"])

# ── In-memory cache keyed by college URL ─────────────────────────────────────
_url_cache: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 600  # 10 min


def _scrape_url_sync(base_url: str, college_name: str) -> list[dict]:
    """Scrape any college URL dynamically — runs in a thread."""
    keywords = ["notice", "exam", "calendar", "timetable", "academic", "holiday", "result"]
    sitemap_url = detect_sitemap(base_url)

    all_events: list[dict] = []
    seen_sources: set[str] = set()

    # If there is a sitemap, use it; otherwise fall back to the base URL itself
    if sitemap_url:
        urls = collect_relevant_urls(base_url, sitemap_url, keywords)
        urls = filter_urls(urls, keywords)
        urls = list(dict.fromkeys([base_url, *urls]))
    else:
        urls = [base_url]

    for url in urls[:60]:
        if url in seen_sources:
            continue
        seen_sources.add(url)
        try:
            text, discovered_links = fetch_main_text_and_links(url, timeout=10)
            page_events = parse_events_from_page(text, source_url=url, college_name=college_name)
            all_events.extend(page_events)

            for link in discovered_links:
                lowered = link.lower()
                if link in seen_sources:
                    continue
                if not lowered.endswith(".pdf"):
                    continue
                if not any(k in lowered for k in keywords):
                    continue
                seen_sources.add(link)
                try:
                    from app.college_events.content_extractor import fetch_main_text
                    pdf_text = fetch_main_text(link, timeout=10)
                    # Use the PARENT page URL as source so "View Source" opens the
                    # actual college notice page, not a generic bulk PDF.
                    pdf_events = parse_events_from_page(pdf_text, source_url=url, college_name=college_name)
                    # Attach the direct PDF URL as a separate field so the frontend
                    # can still offer a "Download PDF" button.
                    for ev in pdf_events:
                        ev["pdf_url"] = link
                    all_events.extend(pdf_events)
                except Exception as exc:
                    logger.warning("Skipping PDF %s: %s", link, exc)
        except Exception as exc:
            logger.warning("Skipping %s: %s", url, exc)

    return all_events


def _serialize_calendar_event(item: dict) -> dict | None:
    raw_start = item.get("start_date") or item.get("date")
    if not raw_start:
        return None

    start = str(raw_start)[:10]
    end = str(item.get("end_date") or raw_start)[:10]
    title = item.get("title") or item.get("event_name") or "Academic Event"
    event_type = item.get("type") or item.get("event_type") or "Notice"

    return {
        "title": title,
        "start": start,
        "end": end,
        "type": event_type,
        "event_name": title,
        "date": start,
        "event_type": event_type,
        "college": item.get("college"),
        "source_url": item.get("source_url"),
    }


@router.get("/colleges")
async def list_colleges():
    loader = CollegeLoader()
    return [
        {
            "name": c.name,
            "base_url": c.base_url,
            "sitemap_url": c.sitemap_url,
            "keywords": c.keywords,
        }
        for c in loader.list_colleges()
    ]


@router.get("/events")
async def get_events(
    college: str | None = Query(default=None, min_length=2),
    db: AsyncSession = Depends(get_db),
):
    try:
        selected_college = college
        if not selected_college:
            loader = CollegeLoader()
            all_colleges = loader.list_colleges()
            if not all_colleges:
                return []
            selected_college = all_colleges[0].name

        events = await fetch_events_for_college(selected_college, db)
        serialized = []
        for item in events:
            mapped = _serialize_calendar_event(item)
            if mapped:
                serialized.append(mapped)
        return serialized
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch events: {exc}")


@router.get("/college-events")
async def get_college_events_dynamic(
    college_url: str = Query(..., description="Base URL of the college website"),
    college_name: str = Query(default="My College", description="Display name of the college"),
):
    """
    Dynamically scrape events from any college URL.
    No colleges.json entry needed — fully dynamic.
    """
    # ── Validate URL ──────────────────────────────────────────────────────────
    try:
        parsed = urlparse(college_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Invalid URL scheme")
    except Exception:
        raise HTTPException(
            status_code=422,
            detail="Invalid college URL. Must start with http:// or https://",
        )

    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # ── Check cache ───────────────────────────────────────────────────────────
    cached = _url_cache.get(base_url)
    if cached:
        cached_time, cached_events = cached
        if time.time() - cached_time < _CACHE_TTL:
            logger.info("Returning %d cached events for %s", len(cached_events), base_url)
            return cached_events

    # ── Scrape (blocking) in a thread ─────────────────────────────────────────
    try:
        raw_events = await asyncio.wait_for(
            asyncio.to_thread(_scrape_url_sync, base_url, college_name),
            timeout=300,  # overall timeout per request (scraper has 10s per page)
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"Timed out while scraping {college_url}. Try again later.")
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not fetch events from {college_url}. {exc}",
        )

    # ── Serialize ─────────────────────────────────────────────────────────────
    serialized = []
    for item in raw_events:
        # Normalise field names: event_parser uses event_name / event_type / date
        normalized = {
            "title":      item.get("event_name") or item.get("title") or "Academic Event",
            "type":       item.get("event_type") or item.get("type") or "Notice",
            "date":       item.get("date") or item.get("start_date") or "",
            "start":      item.get("date") or item.get("start_date") or "",
            "college":    item.get("college") or college_name,
            "source_url": item.get("source_url"),   # notice/web page URL
            "pdf_url":    item.get("pdf_url"),       # direct PDF link (if event was from a PDF)
        }
        if normalized["date"]:          # drop dateless events
            serialized.append(normalized)

    # Sort latest first
    serialized.sort(key=lambda e: e["date"], reverse=True)

    _url_cache[base_url] = (time.time(), serialized)
    return serialized

