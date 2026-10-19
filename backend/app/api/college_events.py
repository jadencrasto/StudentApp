from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import urlparse

from pathlib import Path
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

import re
import uuid
from uuid import UUID
from pydantic import BaseModel, Field
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select, and_, or_, func
from app.core.dependencies import require_admin, get_current_user, get_admin_institution_id
from app.core.security import decode_access_token
from app.models.user import User
from app.models.institution import Institution
from app.models.integrations import CollegeEvent
from app.college_events.safe_scraper import validate_safe_url, extract_events_safe, Scraper503Error
from app.college_events.database import save_events_with_fallback, _normalize_title, _normalize_date
from app.core.rate_limiter import quota_cooldown_tracker

logger = logging.getLogger(__name__)

router = APIRouter(tags=["College Events"])

# Rate limit tracker for admin scrapes: institution_id -> list of timestamps
_institution_scrape_times: dict[str, list[float]] = {}
SCRAPE_MAX_PER_WINDOW = 3
SCRAPE_WINDOW_SECONDS = 3600  # 1 hour

class ManualEventCreate(BaseModel):
    event_name: str = Field(..., min_length=2, max_length=500)
    event_type: str = Field(default="Event", max_length=120)
    event_date: str | None = Field(default=None, max_length=120)
    semester: str | None = Field(default=None, max_length=120)
    department: str | None = Field(default=None, max_length=255)
    source_url: str | None = Field(default=None)

class EventUpdate(BaseModel):
    event_name: str | None = Field(default=None, max_length=500)
    event_type: str | None = Field(default=None, max_length=120)
    event_date: str | None = Field(default=None, max_length=120)
    semester: str | None = Field(default=None, max_length=120)
    department: str | None = Field(default=None, max_length=255)
    is_hidden: bool | None = None

class AdminScrapeRequest(BaseModel):
    college_url: str
    college_name: str = "College"

async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if not credentials:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
        if not payload or not payload.get("sub"):
            return None
        user_id = UUID(payload["sub"])
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user and user.is_active:
            return user
    except Exception:
        pass
    return None


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
    current_user: User | None = Depends(get_optional_user),
):
    try:
        # Case 1: Student belongs to an institution -> strictly scoped to institution
        if current_user and current_user.institution_id:
            stmt = select(CollegeEvent).where(
                CollegeEvent.institution_id == current_user.institution_id,
                CollegeEvent.is_hidden == False,
                CollegeEvent.event_date.isnot(None),
                CollegeEvent.event_date != "",
            ).order_by(CollegeEvent.event_date.desc())
            rows = (await db.execute(stmt)).scalars().all()
            return [
                {
                    "id": str(r.id),
                    "title": r.event_name,
                    "event_name": r.event_name,
                    "type": r.event_type,
                    "event_type": r.event_type,
                    "date": r.event_date,
                    "start": r.event_date,
                    "end": r.event_date,
                    "semester": r.semester,
                    "department": r.department,
                    "source_url": r.source_url,
                    "college": r.college,
                }
                for r in rows
            ]

        # Case 2: Independent student -> unscoped events (institution_id IS NULL)
        stmt = select(CollegeEvent).where(
            CollegeEvent.institution_id.is_(None),
            CollegeEvent.is_hidden == False,
            CollegeEvent.event_date.isnot(None),
            CollegeEvent.event_date != "",
        )
        if college:
            stmt = stmt.where(CollegeEvent.college.ilike(f"%{college}%"))
        stmt = stmt.order_by(CollegeEvent.event_date.desc())
        rows = (await db.execute(stmt)).scalars().all()
        if rows:
            return [
                {
                    "id": str(r.id),
                    "title": r.event_name,
                    "event_name": r.event_name,
                    "type": r.event_type,
                    "event_type": r.event_type,
                    "date": r.event_date,
                    "start": r.event_date,
                    "end": r.event_date,
                    "semester": r.semester,
                    "department": r.department,
                    "source_url": r.source_url,
                    "college": r.college,
                }
                for r in rows
            ]

        # Fallback to configured colleges if DB has no events for selected college
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


# ── Admin Endpoints ───────────────────────────────────────────────────────────

@router.get("/admin/events")
@router.get("/events/admin")
async def get_admin_events(
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    inst_id = get_admin_institution_id(admin_user)
    stmt = select(CollegeEvent).where(
        CollegeEvent.institution_id == inst_id
    ).order_by(CollegeEvent.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()

    dated = []
    needs_date = []
    for r in rows:
        item = {
            "id": str(r.id),
            "institution_id": str(r.institution_id) if r.institution_id else None,
            "event_name": r.event_name,
            "title": r.event_name,
            "event_type": r.event_type,
            "type": r.event_type,
            "event_date": r.event_date,
            "date": r.event_date,
            "semester": r.semester,
            "department": r.department,
            "source_url": r.source_url,
            "is_hidden": r.is_hidden,
            "is_manual": r.is_manual,
            "college": r.college,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        if r.event_date and r.event_date.strip():
            dated.append(item)
        else:
            needs_date.append(item)

    return {
        "events": dated,
        "needs_date": needs_date,
        "stats": {
            "total": len(rows),
            "dated_count": len(dated),
            "needs_date_count": len(needs_date),
            "hidden_count": sum(1 for r in rows if r.is_hidden),
        }
    }


def validate_event_date_format(val: str | None) -> str | None:
    """
    Validates date string for assigned events.
    Accepts ISO formats (YYYY-MM-DD), standard slash formats (DD/MM/YYYY or YYYY/MM/DD),
    or common calendar date formats. Normalizes valid dates to YYYY-MM-DD or raises 422.
    """
    if val is None:
        return None
    cleaned = val.strip()
    if not cleaned:
        return None
    from datetime import datetime
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y", "%B %d, %Y"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    if re.match(r"^\d{4}-\d{2}-\d{2}$", cleaned):
        try:
            datetime.fromisoformat(cleaned)
            return cleaned
        except ValueError:
            pass
    raise HTTPException(
        status_code=422,
        detail="Invalid date format. Please provide a valid date such as YYYY-MM-DD (e.g. 2026-11-15) or DD/MM/YYYY.",
    )


@router.post("/admin/events/manual")
@router.post("/events/manual")
async def create_manual_event(
    payload: ManualEventCreate,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    inst_id = get_admin_institution_id(admin_user)

    norm_title = _normalize_title(payload.event_name)
    validated_date = validate_event_date_format(payload.event_date)
    norm_date = _normalize_date(validated_date)

    existing_stmt = select(CollegeEvent).where(CollegeEvent.institution_id == inst_id)
    existing_rows = (await db.execute(existing_stmt)).scalars().all()
    for ex in existing_rows:
        if _normalize_title(ex.event_name) == norm_title and _normalize_date(ex.event_date) == norm_date:
            raise HTTPException(
                status_code=409,
                detail="An event with the same title and date already exists for this institution.",
            )

    inst_name = "College"
    if inst_id:
        inst_obj = await db.get(Institution, inst_id)
        if inst_obj and inst_obj.name:
            inst_name = inst_obj.name

    new_ev = CollegeEvent(
        institution_id=inst_id,
        college=inst_name,
        event_name=payload.event_name.strip(),
        event_type=payload.event_type.strip(),
        event_date=validated_date,
        semester=payload.semester.strip() if payload.semester else None,
        department=payload.department.strip() if payload.department else None,
        source_url=payload.source_url.strip() if payload.source_url else "manual",
        is_manual=True,
        is_hidden=False,
    )
    db.add(new_ev)
    await db.commit()
    await db.refresh(new_ev)
    return {
        "message": "Manual event created successfully",
        "id": str(new_ev.id),
        "event_name": new_ev.event_name,
        "event_date": new_ev.event_date,
        "is_manual": new_ev.is_manual,
    }


@router.patch("/admin/events/{event_id}")
@router.patch("/events/{event_id}")
async def update_event(
    event_id: UUID,
    payload: EventUpdate,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    inst_id = get_admin_institution_id(admin_user)
    ev = await db.get(CollegeEvent, event_id)
    if not ev or ev.institution_id != inst_id:
        raise HTTPException(status_code=404, detail="Event not found")

    if payload.event_name is not None:
        ev.event_name = payload.event_name.strip()
    if payload.event_type is not None:
        ev.event_type = payload.event_type.strip()
    if payload.event_date is not None:
        ev.event_date = validate_event_date_format(payload.event_date)
    if payload.semester is not None:
        ev.semester = payload.semester.strip() if payload.semester else None
    if payload.department is not None:
        ev.department = payload.department.strip() if payload.department else None
    if payload.is_hidden is not None:
        ev.is_hidden = payload.is_hidden

    await db.commit()
    await db.refresh(ev)
    return {
        "message": "Event updated successfully",
        "id": str(ev.id),
        "is_hidden": ev.is_hidden,
        "event_date": ev.event_date,
    }


@router.post("/admin/events/scrape")
@router.post("/events/scrape")
async def trigger_admin_scrape(
    payload: AdminScrapeRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    inst_id = get_admin_institution_id(admin_user)
    inst_key = str(inst_id)

    # 1. Rate limit check: max 3 calls per hour
    now = time.time()
    recent = [t for t in _institution_scrape_times.get(inst_key, []) if now - t < SCRAPE_WINDOW_SECONDS]
    if len(recent) >= SCRAPE_MAX_PER_WINDOW:
        raise HTTPException(
            status_code=429,
            detail="Scraping rate limit reached (maximum 3 scrapes per hour). You can still add events manually using the 'Add Event' button.",
        )
    # Record attempt now (failed attempts count, but 503 will be refunded below)
    recent.append(now)
    _institution_scrape_times[inst_key] = recent

    # 2. SSRF validation on the initial URL
    is_safe, reason = validate_safe_url(payload.college_url)
    if not is_safe:
        raise HTTPException(
            status_code=400,
            detail=f"Target URL rejected by safety policy: {reason}. You can add events manually using the 'Add Event' button.",
        )

    # 3. Check AI quota cooldown
    if quota_cooldown_tracker.is_in_cooldown():
        raise HTTPException(
            status_code=429,
            detail="AI service daily quota limit reached or in cooldown. Please add events manually using the 'Add Event' form.",
        )

    # 4. Scrape safely (runs in thread so we don't block the async loop)
    inst_name = "College"
    if inst_id:
        inst_obj = await db.get(Institution, inst_id)
        if inst_obj and inst_obj.name:
            inst_name = inst_obj.name

    college_name = payload.college_name or inst_name
    try:
        scraped_events = await asyncio.to_thread(
            extract_events_safe,
            start_url=payload.college_url,
            college_name=college_name,
            max_pages=15
        )
    except Scraper503Error as exc_503:
        # 503 does NOT count towards the rate limit
        if now in _institution_scrape_times.get(inst_key, []):
            _institution_scrape_times[inst_key].remove(now)
        raise HTTPException(
            status_code=503,
            detail=f"The service is temporarily unavailable (503): {exc_503}. This attempt was not counted against your hourly scrape limit. Please try again in a few moments, or add events manually using the 'Add Event' button.",
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=400,
            detail=f"Scraper safety halt: {val_err}. You can add events manually using the 'Add Event' button.",
        )
    except Exception as exc:
        err_msg = str(exc)
        if "503" in err_msg:
            if now in _institution_scrape_times.get(inst_key, []):
                _institution_scrape_times[inst_key].remove(now)
            raise HTTPException(
                status_code=503,
                detail="The service is temporarily unavailable (503). This attempt was not counted against your hourly scrape limit. Please try again in a few moments, or add events manually using the 'Add Event' button.",
            )
        logger.error("Scraper error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Scraping failed: {exc}. You can add events manually using the 'Add Event' button.",
        )

    # 5. Tag events with institution_id and is_manual = False
    for ev in scraped_events:
        ev["institution_id"] = inst_id
        ev["is_manual"] = False
        ev["is_hidden"] = False

    # 6. Save with fallback and duplicate skip (does not overwrite manual rows)
    fallback_file = Path("./uploads/college_events_fallback.json")
    saved = await save_events_with_fallback(db, scraped_events, fallback_file)
    await db.commit()

    return {
        "message": f"Successfully scraped and processed {len(saved)} events",
        "total_scraped": len(scraped_events),
        "persisted_count": len(saved),
    }



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
