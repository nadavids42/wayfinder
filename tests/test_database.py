"""Tests for SQLite opportunity persistence."""

import sqlite3

import pytest

from wayfinder.database import OpportunityStore


@pytest.fixture
def store(tmp_path):
    database = OpportunityStore(tmp_path / 'nested' / 'wayfinder.db')
    database.initialize()
    return database


@pytest.fixture
def sample_job():
    return {
        'source': 'greenhouse',
        'external_id': '12345',
        'company': 'Example AI',
        'title': 'AI Deployment Lead',
        'location': 'Remote - US',
        'remote_type': 'remote',
        'salary_min': None,
        'salary_max': None,
        'currency': None,
        'description': 'Own complex AI deployments.',
        'url': 'https://example.com/jobs/12345',
    }


def test_initialize_is_idempotent(store):
    store.initialize()
    assert store.count() == 0


def test_insert_and_retrieve(store, sample_job):
    job_id = store.save(sample_job)
    saved = store.get(job_id)
    assert saved is not None
    assert saved['title'] == 'AI Deployment Lead'
    assert saved['salary_min'] is None
    assert saved['status'] == 'discovered'
    assert saved['first_seen'] == saved['last_seen']


def test_deduplication_and_update(store, sample_job):
    original_id = store.save(sample_job)
    before = store.get(original_id)
    sample_job['title'] = 'Principal AI Deployment Lead'
    sample_job['url'] += '#apply'
    new_id = store.save(sample_job)
    after = store.get(new_id)
    assert original_id == new_id
    assert store.count() == 1
    assert after['title'] == 'Principal AI Deployment Lead'
    assert after['first_seen'] == before['first_seen']


def test_missing_id(store):
    assert store.get(999) is None


def test_invalid_salary_rejected(store, sample_job):
    sample_job['salary_min'] = 200000
    sample_job['salary_max'] = 150000
    with pytest.raises(ValueError, match='salary_min'):
        store.save(sample_job)
    assert store.count() == 0


def test_invalid_url_rejected(store, sample_job):
    sample_job['url'] = 'not-a-url'
    with pytest.raises(ValueError, match='HTTP'):
        store.save(sample_job)


def test_persists_across_connections(store, sample_job):
    job_id = store.save(sample_job)
    reopened = OpportunityStore(store.db_path)
    assert reopened.get(job_id)['company'] == 'Example AI'


def test_status_preserved_on_refresh(store, sample_job):
    job_id = store.save(sample_job)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute('UPDATE opportunities SET status = ? WHERE id = ?', ('reviewed', job_id))
    store.save(sample_job)
    assert store.get(job_id)['status'] == 'reviewed'


def test_identity_survives_url_change(tmp_path):
    from wayfinder.database import OpportunityStore

    store = OpportunityStore(tmp_path / "identity.db")
    store.initialize()

    job = {
        "source": "greenhouse",
        "external_id": "12345",
        "company": "Example AI",
        "title": "AI Engineer",
        "description": "Build AI systems.",
        "url": "https://example.com/jobs/12345",
    }

    first_id = store.save(job)
    first_record = store.get(first_id)

    job["url"] = "https://example.com/careers/12345"
    job["title"] = "Senior AI Engineer"

    second_id = store.save(job)
    second_record = store.get(second_id)

    assert first_id == second_id
    assert store.count() == 1
    assert second_record["title"] == "Senior AI Engineer"
    assert second_record["first_seen"] == first_record["first_seen"]


def test_different_sources_can_share_external_id(tmp_path):
    from wayfinder.database import OpportunityStore

    store = OpportunityStore(tmp_path / "sources.db")
    store.initialize()

    base_job = {
        "external_id": "12345",
        "company": "Example AI",
        "title": "AI Engineer",
        "description": "Build AI systems.",
    }

    greenhouse = {
        **base_job,
        "source": "greenhouse",
        "url": "https://example.com/greenhouse/12345",
    }

    lever = {
        **base_job,
        "source": "lever",
        "url": "https://example.com/lever/12345",
    }

    store.save(greenhouse)
    store.save(lever)

    assert store.count() == 2


def test_conflicting_identity_rejected(tmp_path):
    import pytest

    from wayfinder.database import (
        OpportunityIdentityError,
        OpportunityStore,
    )

    store = OpportunityStore(tmp_path / "conflicts.db")
    store.initialize()

    job = {
        "source": "greenhouse",
        "external_id": "12345",
        "company": "Example AI",
        "title": "AI Engineer",
        "description": "Build AI systems.",
        "url": "https://example.com/jobs/12345",
    }

    store.save(job)

    conflicting = {
        **job,
        "external_id": "99999",
    }

    with pytest.raises(OpportunityIdentityError):
        store.save(conflicting)

    assert store.count() == 1
