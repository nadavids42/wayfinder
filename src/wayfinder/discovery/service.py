"""Coordinate job discovery and persistence."""

import logging
from dataclasses import dataclass

from wayfinder.database import OpportunityStore
from wayfinder.discovery.greenhouse import discover_jobs


logger = logging.getLogger(__name__)


@dataclass
class DiscoveryResult:
    source: str
    company: str
    retrieved: int
    inserted: int
    updated: int
    errors: int


def run_greenhouse_discovery(
    board_token: str,
    company: str,
    store: OpportunityStore,
) -> DiscoveryResult:
    """Discover Greenhouse opportunities and persist them."""

    opportunities = discover_jobs(
        board_token=board_token,
        company=company,
    )

    inserted = 0
    updated = 0
    errors = 0

    for opportunity in opportunities:
        try:
            external_id = opportunity["external_id"]
            source = opportunity["source"]

            existing = store.get_by_identity(
                source,
                external_id,
            )

            # Also recognize older URL-only records.
            if existing is None:
                from wayfinder.database import normalize_url

                normalized_url = normalize_url(opportunity["url"])

                with store._connect() as connection:
                    row = connection.execute(
                        "SELECT id FROM opportunities WHERE url = ?",
                        (normalized_url,),
                    ).fetchone()

                    if row is not None:
                        existing = {"id": row["id"]}

            store.save(opportunity)

            if existing is None:
                inserted += 1
            else:
                updated += 1

        except Exception:
            errors += 1

            logger.exception(
                "Failed to persist opportunity %s",
                opportunity.get("external_id"),
            )

    return DiscoveryResult(
        source="greenhouse",
        company=company,
        retrieved=len(opportunities),
        inserted=inserted,
        updated=updated,
        errors=errors,
    )