"""Wayfinder command-line interface."""

import argparse
import logging
from pathlib import Path

from wayfinder.database import OpportunityStore
from wayfinder.discovery.greenhouse import DiscoveryError
from wayfinder.discovery.service import run_greenhouse_discovery
from wayfinder.database import OpportunityIdentityError, OpportunityStore


DEFAULT_DATABASE = Path("data/wayfinder.db")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="wayfinder",
        description="AI-powered career intelligence",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    discover_parser = subparsers.add_parser(
        "discover",
        help="Discover and persist job opportunities",
    )

    discover_parser.add_argument(
        "--source",
        choices=["greenhouse"],
        required=True,
    )

    discover_parser.add_argument(
        "--board",
        required=True,
        help="Greenhouse board token",
    )

    discover_parser.add_argument(
        "--company",
        required=True,
        help="Company name",
    )

    discover_parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "discover":
        try:
            store = OpportunityStore(args.database)
            store.initialize()

            result = run_greenhouse_discovery(
                board_token=args.board,
                company=args.company,
                store=store,
            )

        except (
            DiscoveryError,
            OpportunityIdentityError,
            ValueError,
            OSError,
        ) as exc:
            print(f"Discovery failed: {exc}")
            return 1

        print("\nWayfinder Discovery")
        print("-" * 40)
        print(f"Source:      {result.source}")
        print(f"Company:     {result.company}")
        print(f"Retrieved:   {result.retrieved}")
        print(f"Inserted:    {result.inserted}")
        print(f"Updated:     {result.updated}")
        print(f"Errors:      {result.errors}")
        print(f"Database:    {args.database}")

        return 1 if result.errors else 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())