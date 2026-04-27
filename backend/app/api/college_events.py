from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.college_events.college_loader import CollegeConfig, CollegeLoader
from app.college_events.content_extractor import fetch_main_text_and_links
from app.college_events.main import fetch_events_for_college
from app.college_events.sitemap_parser import collect_relevant_urls, detect_sitemap
from app.college_events.url_filter import filter_urls
from app.config import settings
from app.database import get_db
from app.services.gemini_event_extractor import GeminiEventExtractor

logger = logging.getLogger(__name__)

router = APIRouter(tags=["College Events"])

# ── In-memory cache keyed by college URL ─────────────────────────────────────
_url_cache: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 600  # 10 min

# ── Per-base-url Gemini response cache (FIX 3) ────────────────────────────────
_gemini_cache: dict[str, tuple[float, list[dict]]] = {}
_GEMINI_CACHE_TTL = 3600  # 1 hour

# ── Lazy singleton — instantiated once, reused across requests ────────────────
_gemini_extractor: GeminiEventExtractor | None = None


def _get_gemini_extractor() -> GeminiEventExtractor | None:
    """Return a shared GeminiEventExtractor, or None if no API key is set."""
    global _gemini_extractor
    if _gemini_extractor is not None:
        return _gemini_extractor
    if settings.GEMINI_API_KEY:
        try:
            _gemini_extractor = GeminiEventExtractor()
        except Exception as exc:
            logger.warning("Could not initialise GeminiEventExtractor: %s", exc)
    return _gemini_extractor


# ── Google Custom Search fallback ─────────────────────────────────────────────

def _google_search_fallback(college_name: str, college_url: str) -> list[dict]:
    """
    Call the Google Custom Search API when BS4 scraping returns no events.
    Entirely wrapped in try/except — a 403 or any other error is logged and
    silently swallowed so it never crashes the main endpoint.
    """
    try:
        if not settings.GOOGLE_SEARCH_API_KEY or not settings.GOOGLE_SEARCH_CX:
            logger.warning("Google Search keys missing — skipping fallback")
            return []

        query = f"{college_name} notices exams events 2026"
        resp = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": settings.GOOGLE_SEARCH_API_KEY,
                "cx":  settings.GOOGLE_SEARCH_CX,
                "q":   query,
                "num": 10,
            },
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])

        events: list[dict] = []
        for item in items:
            title = str(item.get("title") or "").strip()[:100]
            link  = str(item.get("link") or "").strip()
            if not title:
                continue
            events.append({
                "title":      title,
                "type":       "Notice",
                "date":       "",
                "source_url": link,
                "pdf_url":    "",
            })
        logger.info("Google Search fallback returned %d results for '%s'", len(events), college_name)
        return events

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            logger.warning(
                "Google Search API returned 403 Forbidden. "
                "This usually means billing is not enabled. "
                "Skipping fallback silently."
            )
            return []  # Don't crash, just return empty
        else:
            logger.error(f"Google Search failed: {e}")
            return []
    except Exception as e:
        logger.warning(f"Google Search fallback failed: {e}")
        return []


# ── Main scraping function (runs in a thread) ─────────────────────────────────

def _scrape_url_sync(base_url: str, college_name: str) -> list[dict]:
    """
    Scrape a college website and extract events via a SINGLE Gemini call.

    Pipeline:
      Phase 1 — Scrape up to 20 HTML pages (0.5 s polite delay between each),
                 collect raw text + discovered PDF links.
      Phase 2 — Scrape up to 5 keyword-matching PDFs.
      Phase 3 — Combine all page texts separated by ---PAGE BREAK--- markers
                 and call Gemini ONCE (instead of once-per-page).
    """
    keywords = ["notice", "exam", "calendar", "timetable", "academic", "holiday", "result"]
    sitemap_url = detect_sitemap(base_url)

    seen_sources: set[str] = set()
    gemini = _get_gemini_extractor()

    # Build URL list from sitemap or fall back to base URL only
    if sitemap_url:
        urls = collect_relevant_urls(base_url, sitemap_url, keywords)
        urls = filter_urls(urls, keywords)
        urls = list(dict.fromkeys([base_url, *urls]))
    else:
        urls = [base_url]

    # ── Phase 1: Scrape HTML pages, collect text + PDF links ─────────────────
    scraped_pages: list[dict] = []       # {"url": ..., "text": ...}
    discovered_pdfs: list[dict] = []     # {"url": ..., "parent_url": ...}

    for url in urls[:20]:
        if url in seen_sources:
            continue
        seen_sources.add(url)
        try:
            text, discovered_links = fetch_main_text_and_links(url, timeout=10)
            if text and len(text.strip()) > 100:
                scraped_pages.append({"url": url, "text": text[:1500]})  # FIX 2: was 3000

            for link in discovered_links:
                lowered = link.lower()
                if link in seen_sources:
                    continue
                if not lowered.endswith(".pdf"):
                    continue
                if not any(k in lowered for k in keywords):
                    continue
                discovered_pdfs.append({"url": link, "parent_url": url})
                seen_sources.add(link)

        except Exception as exc:
            logger.warning("Skipping %s: %s", url, exc)

        time.sleep(0.5)  # polite delay between page requests

    # ── Phase 2: Scrape keyword-matching PDFs (cap at 5) ─────────────────────
    for pdf_info in discovered_pdfs[:5]:
        try:
            from app.college_events.content_extractor import fetch_main_text
            pdf_text = fetch_main_text(pdf_info["url"], timeout=10)
            if pdf_text and len(pdf_text.strip()) > 100:
                scraped_pages.append({"url": pdf_info["url"], "text": pdf_text[:3000]})
        except Exception as exc:
            logger.warning("Skipping PDF %s: %s", pdf_info["url"], exc)

    if not scraped_pages:
        logger.info("No usable page text found for %s", base_url)
        return []

    if not gemini:
        logger.warning("Gemini extractor not available — returning no events")
        return []

    # ── Phase 3: Combine all pages and call Gemini ONCE ──────────────────────
    combined_text = "\n\n---PAGE BREAK---\n\n".join(
        f"SOURCE: {p['url']}\n{p['text']}"
        for p in scraped_pages
    )

    # FIX 3: Check Gemini-level cache before making the API call
    cached = _gemini_cache.get(base_url)
    if cached:
        cache_time, cached_events = cached
        if time.time() - cache_time < _GEMINI_CACHE_TTL:
            logger.info("Returning Gemini cached events for %s", base_url)
            return cached_events

    logger.info(
        "Calling Gemini ONCE with %d pages (%d chars) for %s",
        len(scraped_pages), len(combined_text), base_url,
    )
    all_events = gemini.extract_events_from_text(
        raw_text=combined_text[:8000],  # FIX 2: was 15000
        source_url=base_url,
        pdf_url="",
    )
    logger.info("Gemini returned %d events for %s", len(all_events), base_url)

    # FIX 3: Store result in Gemini cache
    _gemini_cache[base_url] = (time.time(), all_events)
    return all_events


# ── Serialiser (unchanged) ────────────────────────────────────────────────────

def _serialize_calendar_event(item: dict) -> dict | None:
    raw_start = item.get("start_date") or item.get("date")
    if not raw_start:
        return None

    start = str(raw_start)[:10]
    end   = str(item.get("end_date") or raw_start)[:10]
    title = item.get("title") or item.get("event_name") or "Academic Event"
    event_type = item.get("type") or item.get("event_type") or "Notice"

    return {
        "title":      title,
        "start":      start,
        "end":        end,
        "type":       event_type,
        "event_name": title,
        "date":       start,
        "event_type": event_type,
        "college":    item.get("college"),
        "source_url": item.get("source_url"),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/colleges")
async def list_colleges():
    loader = CollegeLoader()
    return [
        {
            "name":        c.name,
            "base_url":    c.base_url,
            "sitemap_url": c.sitemap_url,
            "keywords":    c.keywords,
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
    college_url: str  = Query(..., description="Base URL of the college website"),
    college_name: str = Query(default="My College", description="Display name of the college"),
):
    """
    Dynamically scrape events from any college URL.
    No colleges.json entry needed — fully dynamic.

    Pipeline:
      1. requests + BS4 crawl (up to 20 pages + PDFs)
      2. Gemini AI parses each page's raw text → structured events
      3. If still empty → Google Custom Search API fallback
      4. Results cached in-memory for 10 minutes
    """
    # ── Validate required / optional API keys ─────────────────────────────────
    if not settings.GOOGLE_SEARCH_API_KEY:
        logger.warning("GOOGLE_SEARCH_API_KEY not set — Google Search fallback disabled")
    if not settings.GOOGLE_SEARCH_CX:
        logger.warning("GOOGLE_SEARCH_CX not set — Google Search fallback disabled")
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set — Gemini event extraction will fail")
        raise HTTPException(
            status_code=500,
            detail="Gemini API key not configured. Please set GEMINI_API_KEY in .env",
        )

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

    # ── Scrape + Gemini parse (blocking) in a thread ──────────────────────────
    try:
        raw_events: list[dict] = await asyncio.wait_for(
            asyncio.to_thread(_scrape_url_sync, base_url, college_name),
            timeout=300,  # overall timeout; Gemini calls + scraper both happen here
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Timed out while scraping {college_url}. Try again later.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not fetch events from {college_url}. {exc}",
        )

    # ── Google Search fallback if scraping yielded nothing ────────────────────
    if not raw_events:
        logger.info(
            "No events found from scraping %s. Trying Google Search fallback.", base_url
        )
        raw_events = _google_search_fallback(college_name, base_url)

    # ── Normalise + deduplicate final list ────────────────────────────────────
    serialized: list[dict] = []
    seen_final: set[tuple] = set()

    for item in raw_events:
        title      = str(item.get("title") or "").strip() or "Academic Event"
        event_type = str(item.get("type")  or "Notice").strip()
        date       = str(item.get("date")  or "").strip()
        source_url = item.get("source_url") or ""
        pdf_url    = item.get("pdf_url")    or ""

        key = (title.lower(), date)
        if key in seen_final:
            continue
        seen_final.add(key)

        serialized.append({
            "title":      title,
            "type":       event_type,
            "date":       date,
            "start":      date,
            "college":    item.get("college") or college_name,
            "source_url": source_url or None,
            "pdf_url":    pdf_url    or None,
        })

    # Sort latest first (dateless entries fall to the bottom)
    serialized.sort(key=lambda e: e["date"] or "", reverse=True)

    _url_cache[base_url] = (time.time(), serialized)
    return serialized
