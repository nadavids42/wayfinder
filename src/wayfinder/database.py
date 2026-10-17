"""SQLite persistence for discovered job opportunities."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit, urlunsplit

class OpportunityIdentityError(Exception):
    """Raised when opportunity identities conflict."""

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

CREATE UNIQUE INDEX IF NOT EXISTS idx_opportunities_source_external_id ON opportunities(source, external_id) WHERE external_id IS NOT NULL;
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
        """Initialize the database and apply identity migration."""

        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self._connect() as connection:
            connection.executescript(SCHEMA)

            duplicates = connection.execute(
                """
                SELECT
                    source,
                    external_id,
                    COUNT(*) AS duplicate_count
                FROM opportunities
                WHERE external_id IS NOT NULL
                GROUP BY source, external_id
                HAVING COUNT(*) > 1
                """
            ).fetchall()

            if duplicates:
                details = [
                    (
                        f"{row['source']}:{row['external_id']} "
                        f"({row['duplicate_count']} records)"
                    )
                    for row in duplicates
                ]

                raise OpportunityIdentityError(
                    "Duplicate opportunity identities require "
                    "manual reconciliation: "
                    + ", ".join(details)
                )

            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_opportunities_source_external_id
                ON opportunities(source, external_id)
                WHERE external_id IS NOT NULL
                """
            )

    def save(self, job: dict[str, Any]) -> int:
        """Insert or refresh a posting, preserving its internal ID."""

        required = ("source", "company", "title", "description", "url")

        for key in required:
            if not isinstance(job.get(key), str) or not job[key].strip():
                raise ValueError(f"{key} must be a nonempty string")

        external_id = job.get("external_id")

        if external_id is not None:
            if not isinstance(external_id, str) or not external_id.strip():
                raise ValueError("external_id must be a nonempty string or None")
            external_id = external_id.strip()

        remote_type = job.get("remote_type", "unknown")

        if remote_type not in ("remote", "hybrid", "onsite", "unknown"):
            raise ValueError("invalid remote_type")

        for key in ("salary_min", "salary_max"):
            value = job.get(key)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{key} must be a nonnegative integer or None")

        low = job.get("salary_min")
        high = job.get("salary_max")

        if low is not None and high is not None and low > high:
            raise ValueError("salary_min cannot exceed salary_max")

        url = normalize_url(job["url"])
        source = job["source"].strip()
        now = utc_now()

        with self._connect() as connection:
            # Resolve identity and URL independently.
            identity_row = None

            if external_id is not None:
                identity_row = connection.execute(
                    """
                    SELECT id
                    FROM opportunities
                    WHERE source = ? AND external_id = ?
                    """,
                    (source, external_id),
                ).fetchone()

            url_row = connection.execute(
                """
                SELECT id, source, external_id
                FROM opportunities
                WHERE url = ?
                """,
                (url,),
            ).fetchone()

            # Never merge two distinct records automatically.
            if (
                identity_row is not None
                and url_row is not None
                and identity_row["id"] != url_row["id"]
            ):
                raise OpportunityIdentityError(
                    "Source identity and URL identify different opportunities"
                )

            if url_row is not None:
                if url_row["source"] != source:
                    raise OpportunityIdentityError(
                        "URL already belongs to another source"
                    )

                existing_external_id = url_row["external_id"]

                if (
                    existing_external_id is not None
                    and external_id is not None
                    and existing_external_id != external_id
                ):
                    raise OpportunityIdentityError(
                        "URL already belongs to another external ID"
                    )

            existing = identity_row or url_row

            if existing is not None:
                opportunity_id = int(existing["id"])

                connection.execute(
                    """
                    UPDATE opportunities
                    SET
                        external_id = COALESCE(?, external_id),
                        company = ?,
                        title = ?,
                        location = ?,
                        remote_type = ?,
                        salary_min = ?,
                        salary_max = ?,
                        currency = ?,
                        description = ?,
                        url = ?,
                        last_seen = ?
                    WHERE id = ?
                    """,
                    (
                        external_id,
                        job["company"],
                        job["title"],
                        job.get("location"),
                        remote_type,
                        low,
                        high,
                        job.get("currency"),
                        job["description"],
                        url,
                        now,
                        opportunity_id,
                    ),
                )

                return opportunity_id

            cursor = connection.execute(
                """
                INSERT INTO opportunities (
                    source,
                    external_id,
                    company,
                    title,
                    location,
                    remote_type,
                    salary_min,
                    salary_max,
                    currency,
                    description,
                    url,
                    first_seen,
                    last_seen
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    external_id,
                    job["company"],
                    job["title"],
                    job.get("location"),
                    remote_type,
                    low,
                    high,
                    job.get("currency"),
                    job["description"],
                    url,
                    now,
                    now,
                ),
            )

            assert cursor.lastrowid is not None
            return int(cursor.lastrowid)

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

    def get_by_identity(
        self,
        source: str,
        external_id: str,
    ) -> dict[str, Any] | None:
        """Retrieve an opportunity by its source identity."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM opportunities
                WHERE source = ?
                AND external_id = ?
                """,
                (source, external_id),
            ).fetchone()

            return dict(row) if row is not None else None

    def get_by_url(self, url: str) -> dict[str, Any] | None:
        """Retrieve an opportunity by normalized URL."""

        normalized = normalize_url(url)

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM opportunities WHERE url = ?",
                (normalized,),
            ).fetchone()

            return dict(row) if row is not None else None
