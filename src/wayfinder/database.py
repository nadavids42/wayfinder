"""SQLite persistence for discovered job opportunities."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit, urlunsplit


SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    remote_type TEXT NOT NULL DEFAULT 'unknown'
        CHECK (remote_type IN ('remote', 'hybrid', 'onsite', 'unknown')),
    salary_min INTEGER CHECK (salary_min IS NULL OR salary_min >= 0),
    salary_max INTEGER CHECK (salary_max IS NULL OR salary_max >= 0),
    currency TEXT,
    description TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'discovered'
        CHECK (status IN ('discovered', 'reviewed', 'rejected', 'archived')),
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    CHECK (salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max)
);
CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_url(url: str) -> str:
    """Normalize simple posting URLs for repeat-discovery deduplication."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError('url must be a nonempty string')
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in ('http', 'https') or not parts.hostname:
        raise ValueError('url must be an absolute HTTP(S) URL')
    host = parts.netloc.lower()
    path = parts.path.rstrip('/') or '/'
    return urlunsplit((parts.scheme.lower(), host, path, parts.query, ''))


class OpportunityStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('PRAGMA busy_timeout = 10000')
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def save(self, job: dict[str, Any]) -> int:
        """Insert or refresh a posting; return its stable internal ID."""
        required = ('source', 'company', 'title', 'description', 'url')
        for key in required:
            if not isinstance(job.get(key), str) or not job[key].strip():
                raise ValueError(f'{key} must be a nonempty string')
        remote_type = job.get('remote_type', 'unknown')
        if remote_type not in ('remote', 'hybrid', 'onsite', 'unknown'):
            raise ValueError('invalid remote_type')
        for key in ('salary_min', 'salary_max'):
            value = job.get(key)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f'{key} must be a nonnegative integer or None')
        low, high = job.get('salary_min'), job.get('salary_max')
        if low is not None and high is not None and low > high:
            raise ValueError('salary_min cannot exceed salary_max')
        url = normalize_url(job['url'])
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO opportunities (
                    source, external_id, company, title, location, remote_type,
                    salary_min, salary_max, currency, description, url,
                    first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    source=excluded.source,
                    external_id=excluded.external_id,
                    company=excluded.company,
                    title=excluded.title,
                    location=excluded.location,
                    remote_type=excluded.remote_type,
                    salary_min=excluded.salary_min,
                    salary_max=excluded.salary_max,
                    currency=excluded.currency,
                    description=excluded.description,
                    last_seen=excluded.last_seen
                """,
                (
                    job['source'], job.get('external_id'), job['company'],
                    job['title'], job.get('location'), remote_type, low, high,
                    job.get('currency'), job['description'], url, now, now,
                ),
            )
            row = connection.execute(
                'SELECT id FROM opportunities WHERE url = ?', (url,)
            ).fetchone()
            assert row is not None
            return int(row['id'])

    def get(self, opportunity_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                'SELECT * FROM opportunities WHERE id = ?', (opportunity_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute('SELECT COUNT(*) AS n FROM opportunities').fetchone()
            assert row is not None
            return int(row['n'])
