from __future__ import annotations

import ipaddress
import logging
import socket
import time
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests

from app.config import settings
from app.core.rate_limiter import quota_cooldown_tracker
from app.college_events.junk_filter import is_junk_event
from app.college_events.event_parser import parse_events_from_page
from app.services.gemini_event_extractor import GeminiEventExtractor

logger = logging.getLogger(__name__)

class Scraper503Error(Exception):
    """Raised when upstream web server or AI service returns 503 Service Unavailable."""
    pass


CLOUD_METADATA_IPS = {
    "169.254.169.254",   # AWS / GCP / Azure metadata
    "fd00:ec2::254",      # AWS IPv6 metadata
    "100.100.100.200",   # Alibaba cloud metadata
}

BLOCKED_HOSTNAMES = {
    "metadata.google.internal",
    "metadata",
    "localhost",
}

def is_safe_ip(ip_str: str) -> tuple[bool, str]:
    """Validates that an IP address is public and safe (blocks private, loopback, link-local, metadata)."""
    if ip_str in CLOUD_METADATA_IPS:
        return False, f"Cloud metadata IP address {ip_str} is strictly blocked"
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False, f"Invalid IP address: {ip_str}"

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return False, f"Private or local IP address {ip_str} is forbidden"

    return True, ""


def validate_safe_url(url: str, allowed_domain: str | None = None) -> tuple[bool, str]:
    """
    Validates scheme, domain consistency, and DNS-resolved IP address.
    Re-run on every redirect hop to prevent SSRF vulnerabilities.
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:
        return False, f"Invalid URL format: {exc}"

    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Unsupported scheme '{parsed.scheme}'. Only http and https are allowed."

    hostname = parsed.hostname
    if not hostname:
        return False, "Missing hostname in URL"

    if hostname.lower() in BLOCKED_HOSTNAMES:
        return False, f"Blocked hostname: {hostname}"

    # Same-domain restriction
    if allowed_domain:
        allowed_parsed = urlparse(allowed_domain)
        target_domain = allowed_parsed.hostname or allowed_domain
        if hostname.lower() != target_domain.lower() and not hostname.lower().endswith("." + target_domain.lower()):
            return False, f"Cross-domain request forbidden: '{hostname}' does not match '{target_domain}'"

    # Check if hostname itself is an IP literal
    try:
        ipaddress.ip_address(hostname)
        is_safe, reason = is_safe_ip(hostname)
        if not is_safe:
            return False, reason
    except ValueError:
        # Resolve hostname via DNS
        try:
            addr_infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror as e:
            return False, f"Could not resolve hostname '{hostname}': {e}"

        if not addr_infos:
            return False, f"No IP addresses resolved for '{hostname}'"

        for addr_info in addr_infos:
            ip_str = addr_info[4][0]
            is_safe, reason = is_safe_ip(ip_str)
            if not is_safe:
                return False, reason

    return True, ""


def safe_fetch_page(
    url: str,
    allowed_domain: str,
    max_redirects: int = 3,
    timeout: int = 10,
    max_bytes: int = 2 * 1024 * 1024
) -> str | None:
    """
    Fetches URL content safely, checking every redirect hop against SSRF rules.
    Enforces maximum bytes (default 2MB) and timeout.
    """
    current_url = url
    session = requests.Session()
    session.headers.update({
        "User-Agent": "SAIS-Academic-Crawler/1.0 (+https://sais.edu)"
    })

    for hop in range(max_redirects + 1):
        is_safe, reason = validate_safe_url(current_url, allowed_domain=allowed_domain)
        if not is_safe:
            logger.warning("SSRF check rejected URL at hop %d: %s (%s)", hop, current_url, reason)
            raise ValueError(f"Blocked by safety policy: {reason}")

        try:
            resp = session.get(
                current_url,
                allow_redirects=False,
                timeout=timeout,
                stream=True
            )
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", current_url, exc)
            return None

        # Check for redirect
        if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
            if hop >= max_redirects:
                raise ValueError("Too many redirects")
            loc = resp.headers.get("Location")
            if not loc:
                return None
            current_url = urljoin(current_url, loc)
            continue

        if resp.status_code == 503:
            raise Scraper503Error(f"Target web server at {current_url} returned 503 Service Unavailable")

        if resp.status_code != 200:
            return None

        # Read content with size limit
        content_chunks = []
        bytes_read = 0
        for chunk in resp.iter_content(chunk_size=65536):
            bytes_read += len(chunk)
            if bytes_read > max_bytes:
                logger.warning("Response exceeded size limit (%d bytes) for %s", max_bytes, current_url)
                break
            content_chunks.append(chunk)

        try:
            return b"".join(content_chunks).decode("utf-8", errors="replace")
        except Exception:
            return None

    return None


def extract_events_safe(
    start_url: str,
    college_name: str,
    max_pages: int = 15,
) -> list[dict]:
    """
    Safely crawls college website up to max_pages, strictly on same domain.
    Extracts text, filters junk, and normalizes events.
    """
    parsed = urlparse(start_url)
    allowed_domain = f"{parsed.scheme}://{parsed.netloc}"

    visited: set[str] = set()
    to_visit: list[str] = [start_url]
    all_events: list[dict] = []
    page_texts: list[dict] = []

    keywords = ["notice", "exam", "calendar", "timetable", "academic", "holiday", "result", "workshop"]

    while to_visit and len(visited) < max_pages:
        current_url = to_visit.pop(0)
        if current_url in visited:
            continue
        visited.add(current_url)

        try:
            html = safe_fetch_page(current_url, allowed_domain=allowed_domain)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator="\n", strip=True)

            if len(text) > 100:
                page_texts.append({"url": current_url, "text": text[:2000]})
                # Extract rule-based events from page
                events = parse_events_from_page(text, source_url=current_url, college_name=college_name)
                all_events.extend(events)

            # Discover internal links
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                abs_url = urljoin(current_url, href)
                # Strip fragments
                abs_url = abs_url.split("#")[0]
                if abs_url in visited or abs_url in to_visit:
                    continue
                # Same domain only
                u_parsed = urlparse(abs_url)
                if u_parsed.netloc.lower() == parsed.netloc.lower():
                    # Prioritize relevant links
                    if any(k in abs_url.lower() for k in keywords):
                        to_visit.insert(0, abs_url)
                    elif len(to_visit) < 50:
                        to_visit.append(abs_url)

        except ValueError as val_err:
            logger.warning("Safety abort on %s: %s", current_url, val_err)
            raise
        except Exception as exc:
            logger.warning("Error scraping %s: %s", current_url, exc)

        time.sleep(0.3)  # Polite crawl rate limit

    # AI Enhancement if Gemini configured and not in cooldown
    if page_texts and settings.GEMINI_API_KEY and not quota_cooldown_tracker.is_in_cooldown():
        try:
            gemini = GeminiEventExtractor()
            combined = "\n\n---PAGE BREAK---\n\n".join(
                f"SOURCE: {p['url']}\n{p['text']}" for p in page_texts[:10]
            )
            # Try extraction with 1 retry on 503 only
            ai_events = None
            for attempt in range(2):
                try:
                    ai_events = gemini.extract_events_from_text(
                        raw_text=combined[:8000],
                        source_url=start_url,
                        pdf_url=""
                    )
                    break
                except Exception as ai_exc:
                    err_str = str(ai_exc)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                        logger.warning("Gemini quota exhausted during event scrape. Setting cooldown.")
                        quota_cooldown_tracker.set_cooldown(300.0)
                        break
                    elif "503" in err_str:
                        if attempt == 0:
                            logger.info("AI service returned 503. Retrying once after 1s...")
                            time.sleep(1.0)
                            continue
                        else:
                            logger.warning("AI service 503 persisted after retry.")
                            raise Scraper503Error("AI service returned 503 Service Unavailable after retry.")
                    else:
                        logger.warning("Gemini event extraction error: %s", ai_exc)
                        break

            if ai_events:
                for item in ai_events:
                    title = item.get("title") or item.get("event_name")
                    if not title:
                        continue
                    is_junk, _ = is_junk_event(title, source_url=item.get("source_url", start_url))
                    if is_junk:
                        continue
                    all_events.append({
                        "college": college_name,
                        "event_name": title[:180],
                        "event_type": item.get("type") or "Notice",
                        "date": item.get("date"),
                        "semester": item.get("semester"),
                        "department": item.get("department"),
                        "source_url": item.get("source_url") or start_url,
                    })
        except Exception as e:
            logger.warning("Gemini integration error: %s", e)

    # In-scrape deduplication
    unique_events = []
    seen = set()
    for ev in all_events:
        name_key = " ".join(ev["event_name"].strip().lower().split())
        date_key = (ev.get("date") or "").strip()
        key = (name_key, date_key)
        if key in seen:
            continue
        seen.add(key)
        unique_events.append(ev)

    return unique_events
