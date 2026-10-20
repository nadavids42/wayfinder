"""Tests for discovery-to-database integration."""

from unittest.mock import patch

from wayfinder.database import OpportunityStore
from wayfinder.discovery.service import run_greenhouse_discovery


def test_discovery_persists_without_duplicates(tmp_path):
    store = OpportunityStore(tmp_path / "discovery.db")
    store.initialize()

    jobs = [
        {
            "source": "greenhouse",
            "external_id": "12345",
            "company": "Example AI",
            "title": "AI Engineer",
            "location": "Remote - US",
            "remote_type": "unknown",
            "salary_min": None,
            "salary_max": None,
            "currency": None,
            "description": "Build production AI systems.",
            "url": "https://example.com/jobs/12345",
        }
    ]

    with patch(
        "wayfinder.discovery.service.discover_jobs",
        return_value=jobs,
    ):
        first = run_greenhouse_discovery(
            "example",
            "Example AI",
            store,
        )

        second = run_greenhouse_discovery(
            "example",
            "Example AI",
            store,
        )

    assert first.retrieved == 1
    assert first.inserted == 1
    assert first.updated == 0
    assert first.errors == 0

    assert second.retrieved == 1
    assert second.inserted == 0
    assert second.updated == 1
    assert second.errors == 0

    assert store.count() == 1