from __future__ import annotations

import time
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from models import Record, canonical_url, clean_text, iso_date, stable_id
from source_health import SourceHealth


IGNORED_TEXT = {
    "about", "apply", "blog", "careers", "companies", "contact", "facebook",
    "instagram", "jobs", "learn more", "linkedin", "portfolio", "privacy",
    "terms", "twitter", "x", "youtube",
}


def parse_registry(content: str, registry_url: str) -> list[Record]:
    registry_domain = urlsplit(registry_url).netloc.casefold().removeprefix("www.")
    soup = BeautifulSoup(content, "html.parser")
    companies: dict[str, Record] = {}
    for anchor in soup.select("a[href]"):
        name = clean_text(anchor.get_text(" ", strip=True))
        url = canonical_url(anchor.get("href"))
        if not url.startswith("http") or not 2 <= len(name) <= 80:
            continue
        if name.casefold() in IGNORED_TEXT:
            continue
        domain = urlsplit(url).netloc.casefold().removeprefix("www.")
        if not domain or domain == registry_domain:
            continue
        if any(
            blocked in domain
            for blocked in (
                "facebook.com", "instagram.com", "linkedin.com", "twitter.com",
                "youtube.com", "google.com",
            )
        ):
            continue
        companies.setdefault(
            domain,
            {
                "id": stable_id(domain, prefix="company"),
                "company": name,
                "company_url": url,
                "registry_url": registry_url,
                "source": "fund_registry",
                "status": "needs_company_verification",
                "next_action": (
                    "Confirm Bengaluru presence, 400-or-fewer employees, lane, "
                    "and a current funding/growth/problem signal."
                ),
                "confidence": "low",
                "last_seen": iso_date(),
                "source_urls": [registry_url, url],
            },
        )
    return list(companies.values())


def fetch_registries(config: dict) -> tuple[list[Record], list[Record]]:
    session = requests.Session()
    session.headers["User-Agent"] = config.get("user_agent", "InternshipResearch/0.1")
    timeout = int(config.get("timeout_seconds", 25))
    candidates: dict[str, Record] = {}
    health: list[Record] = []
    for registry_url in config.get("registries", []):
        started = time.perf_counter()
        try:
            response = session.get(registry_url, timeout=timeout)
            if response.status_code in {401, 403}:
                raise RuntimeError(f"access_control HTTP {response.status_code}")
            response.raise_for_status()
            records = parse_registry(response.text, registry_url)
            for record in records:
                candidates.setdefault(record["id"], record)
            health.append(
                SourceHealth(
                    source_id=f"registry:{urlsplit(registry_url).netloc}",
                    status="ok" if records else "zero_results",
                    record_count=len(records),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    human_action="" if records else "Inspect the current public page structure.",
                ).to_dict()
            )
        except Exception as exc:
            health.append(
                SourceHealth(
                    source_id=f"registry:{urlsplit(registry_url).netloc}",
                    status="failed",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:500],
                    human_action="Review public access and adapter contract; do not bypass.",
                ).to_dict()
            )
        time.sleep(float(config.get("min_interval_seconds", 2)))
    return list(candidates.values()), health


