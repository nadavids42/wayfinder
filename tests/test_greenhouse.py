"""Tests for Greenhouse job discovery."""

import html
import json

import httpx
import pytest

from wayfinder.discovery.greenhouse import (
    DiscoveryError,
    discover_jobs,
    fetch_jobs,
    html_to_text,
    normalize_job,
)


SAMPLE_JOB = {
    "id": 12345,
    "title": "Senior AI Engineer",
    "absolute_url": "https://boards.greenhouse.io/example/jobs/12345",
    "location": {"name": "Remote - United States"},
    "content": (
        "&lt;p&gt;Build production AI systems.&lt;/p&gt;"
        "&lt;p&gt;Work with enterprise customers.&lt;/p&gt;"
    ),
}


def mock_client(payload, status_code=200):
    """Create a mock HTTP client."""

    def handler(request):
        return httpx.Response(
            status_code,
            json=payload,
            request=request,
        )

    return httpx.Client(
        transport=httpx.MockTransport(handler)
    )


def test_html_to_text():
    result = html_to_text(
        "<p>Hello</p><p>World</p>"
    )

    assert result == "Hello\nWorld"


def test_normalize_job():
    opportunity = normalize_job(
        SAMPLE_JOB,
        "Example AI",
    )

    assert opportunity["source"] == "greenhouse"
    assert opportunity["external_id"] == "12345"
    assert opportunity["company"] == "Example AI"
    assert opportunity["title"] == "Senior AI Engineer"
    assert opportunity["location"] == "Remote - United States"

    assert opportunity["remote_type"] == "unknown"
    assert opportunity["salary_min"] is None

    assert "Build production AI systems" in (
        opportunity["description"]
    )


def test_fetch_jobs_success():
    client = mock_client({
        "jobs": [SAMPLE_JOB]
    })

    with client:
        jobs = fetch_jobs("example", client=client)

    assert len(jobs) == 1
    assert jobs[0]["id"] == 12345


def test_fetch_jobs_empty():
    client = mock_client({"jobs": []})

    with client:
        jobs = fetch_jobs("example", client=client)

    assert jobs == []


def test_invalid_board_token():
    with pytest.raises(ValueError):
        fetch_jobs("../invalid")


def test_missing_jobs_list():
    client = mock_client({"unexpected": []})

    with client:
        with pytest.raises(
            DiscoveryError,
            match="missing jobs list",
        ):
            fetch_jobs("example", client=client)


def test_http_404():
    client = mock_client(
        {"error": "Not found"},
        status_code=404,
    )

    with client:
        with pytest.raises(
            DiscoveryError,
            match="HTTP error 404",
        ):
            fetch_jobs("nonexistent", client=client)


def test_discover_jobs():
    client = mock_client({
        "jobs": [SAMPLE_JOB]
    })

    with client:
        opportunities = discover_jobs(
            "example",
            "Example AI",
            client=client,
        )

    assert len(opportunities) == 1

    opportunity = opportunities[0]

    assert opportunity["company"] == "Example AI"
    assert opportunity["source"] == "greenhouse"
    assert opportunity["external_id"] == "12345"


def test_malformed_job_skipped():
    client = mock_client({
        "jobs": [
            SAMPLE_JOB,
            {"id": 999, "title": ""},
        ]
    })

    with client:
        opportunities = discover_jobs(
            "example",
            "Example AI",
            client=client,
        )

    assert len(opportunities) == 1