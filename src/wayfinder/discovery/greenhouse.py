"""Greenhouse public Job Board API integration."""

import logging
import random
import re
import time
from typing import Any
from html import unescape

import httpx
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"

MAX_ATTEMPTS = 3
TIMEOUT_SECONDS = 15

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class DiscoveryError(Exception):
    """Raised when job discovery fails."""


def html_to_text(html: str) -> str:
    """Convert a Greenhouse HTML description into readable text."""

    soup = BeautifulSoup(html, "html.parser")

    for element in soup(["script", "style"]):
        element.decompose()

    text = soup.get_text(separator="\n", strip=True)

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    return "\n".join(lines)


def fetch_jobs(
    board_token: str,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve published jobs from a Greenhouse board.

    Args:
        board_token: Greenhouse company board identifier.
        client: Optional HTTP client for testing or reuse.

    Returns:
        Raw job dictionaries from the Greenhouse API.

    Raises:
        DiscoveryError: For API, network, or response failures.
    """

    if not isinstance(board_token, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]+", board_token
    ):
        raise ValueError("Invalid Greenhouse board token")

    url = f"{BASE_URL}/{board_token}/jobs"

    owns_client = client is None

    if client is None:
        client = httpx.Client(
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,
        )

    try:
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = client.get(
                    url,
                    params={"content": "true"},
                    timeout=TIMEOUT_SECONDS,
                )

                if response.status_code in RETRYABLE_STATUSES:
                    if attempt < MAX_ATTEMPTS - 1:
                        delay = min(2 ** attempt, 8)

                        if response.status_code == 429:
                            retry_after = response.headers.get(
                                "Retry-After"
                            )
                            if retry_after and retry_after.isdigit():
                                delay = min(int(retry_after), 60)

                        delay += random.uniform(0, 0.25)
                        time.sleep(delay)
                        continue

                response.raise_for_status()

                payload = response.json()

                if not isinstance(payload, dict):
                    raise DiscoveryError(
                        "Greenhouse returned an invalid response"
                    )

                jobs = payload.get("jobs")

                if not isinstance(jobs, list):
                    raise DiscoveryError(
                        "Greenhouse response missing jobs list"
                    )

                if not all(isinstance(job, dict) for job in jobs):
                    raise DiscoveryError(
                        "Greenhouse returned malformed job records"
                    )

                logger.info(
                    "Retrieved %d jobs from Greenhouse board %s",
                    len(jobs),
                    board_token,
                )

                return jobs

            except (
                httpx.TimeoutException,
                httpx.TransportError,
            ) as exc:
                if attempt == MAX_ATTEMPTS - 1:
                    raise DiscoveryError(
                        f"Network failure retrieving {board_token}"
                    ) from exc

                time.sleep(min(2 ** attempt, 8))

            except httpx.HTTPStatusError as exc:
                raise DiscoveryError(
                    f"Greenhouse HTTP error "
                    f"{exc.response.status_code} "
                    f"for board {board_token}"
                ) from exc

            except ValueError as exc:
                raise DiscoveryError(
                    "Greenhouse returned invalid JSON"
                ) from exc

        raise DiscoveryError(
            f"Failed to retrieve jobs from {board_token}"
        )

    finally:
        if owns_client:
            client.close()


def normalize_job(
    job: dict[str, Any],
    company: str,
) -> dict[str, Any]:
    """
    Convert a Greenhouse posting into Wayfinder's schema.

    Unknown information remains unknown.
    """

    job_id = job.get("id")
    title = job.get("title")
    url = job.get("absolute_url")

    if not isinstance(job_id, int) or isinstance(job_id, bool):
        raise ValueError("Job missing valid ID")

    if not isinstance(title, str) or not title.strip():
        raise ValueError("Job missing title")

    if not isinstance(url, str) or not url.startswith(
        ("https://", "http://")
    ):
        raise ValueError("Job missing valid URL")

    if not isinstance(company, str) or not company.strip():
        raise ValueError("Company name required")

    location_data = job.get("location") or {}

    if not isinstance(location_data, dict):
        location_data = {}

    location = location_data.get("name")

    if not isinstance(location, str):
        location = None

    raw_description = job.get("content") or ""

    if not isinstance(raw_description, str):
        raw_description = ""

    description = html_to_text(unescape(raw_description))

    # Do not infer remote policy from location text.
    # Do not infer salary from unstructured descriptions.
    return {
        "source": "greenhouse",
        "external_id": str(job_id),
        "company": company.strip(),
        "title": title.strip(),
        "location": location,
        "remote_type": "unknown",
        "salary_min": None,
        "salary_max": None,
        "currency": None,
        "description": description,
        "url": url,
    }


def discover_jobs(
    board_token: str,
    company: str,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Retrieve and normalize opportunities from a company board."""

    raw_jobs = fetch_jobs(board_token, client=client)

    opportunities = []

    for job in raw_jobs:
        try:
            opportunity = normalize_job(job, company)
            opportunities.append(opportunity)

        except ValueError as exc:
            logger.warning(
                "Skipping malformed Greenhouse job: %s",
                exc,
            )

    logger.info(
        "Normalized %d opportunities for %s",
        len(opportunities),
        company,
    )

    return opportunities