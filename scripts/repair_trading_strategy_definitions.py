#!/usr/bin/env python3
"""Inspect and repair canonical trading strategy seed definitions in Postgres."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.connection import get_session
from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository
from src.trading.runtime.support import seed_initial_strategy_definitions
from src.trading.strategies.definitions import load_all_trading_definitions
from src.trading.strategies.matching import StrategyDefinitionRecord


def find_seed_definition_issues(definitions: Iterable[StrategyDefinitionRecord]) -> dict[str, object]:
    """Report tactical seed rows that are missing `selection_policy` metadata."""
    canonical_rows = {
        (str(row["strategy_id"]), str(row.get("version") or "v1")): row
        for row in load_all_trading_definitions()
    }
    current_rows = {
        (definition.strategy_id, definition.version): definition
        for definition in definitions
    }
    missing_selection_policy_strategy_ids: list[str] = []
    missing_seed_definition_strategy_ids: list[str] = []
    for key, canonical_row in canonical_rows.items():
        if str(canonical_row.get("strategy_layer") or "") != "tactical_pattern":
            continue
        current = current_rows.get(key)
        if current is None:
            missing_seed_definition_strategy_ids.append(str(canonical_row["strategy_id"]))
            continue
        if current.source != "seed":
            continue
        current_selection_policy = dict(current.config_json or {}).get("selection_policy") or {}
        if not _has_non_empty_value(current_selection_policy):
            missing_selection_policy_strategy_ids.append(str(canonical_row["strategy_id"]))
    return {
        "missing_selection_policy_strategy_ids": missing_selection_policy_strategy_ids,
        "missing_selection_policy_count": len(missing_selection_policy_strategy_ids),
        "missing_seed_definition_strategy_ids": missing_seed_definition_strategy_ids,
        "missing_seed_definition_count": len(missing_seed_definition_strategy_ids),
    }


def run_repair(*, session: Any, dry_run: bool) -> dict[str, object]:
    """Repair seed metadata and control the transaction boundary explicitly."""
    repository = SqlAlchemyTradingRepository(session)
    before_definitions = tuple(repository.load_strategy_definitions())
    before_issues = find_seed_definition_issues(before_definitions)
    before_by_key = _definitions_by_key(before_definitions)
    canonical_rows = _canonical_seed_rows()
    seed_initial_strategy_definitions(repository)
    after_definitions = tuple(repository.load_strategy_definitions())
    after_issues = find_seed_definition_issues(after_definitions)
    after_by_key = _definitions_by_key(after_definitions)

    inserted_count = sum(1 for key in canonical_rows if key not in before_by_key and key in after_by_key)
    patched_count = sum(
        1
        for key in canonical_rows
        if key in before_by_key
        and key in after_by_key
        and dict(before_by_key[key].config_json or {}) != dict(after_by_key[key].config_json or {})
    )

    if dry_run:
        session.rollback()
    else:
        session.commit()

    return {
        "dry_run": dry_run,
        "inserted_count": inserted_count,
        "patched_count": patched_count,
        "missing_after_count": int(after_issues["missing_selection_policy_count"]),
        "before": before_issues,
        "after": after_issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Inspect and repair without committing changes.")
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")
    args = parser.parse_args(argv)

    load_dotenv()
    session_manager = get_session()
    session = session_manager.__enter__()
    try:
        report = run_repair(session=session, dry_run=args.dry_run)
    finally:
        session.close()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    else:
        _print_report(report)
    return 0


def _canonical_seed_rows() -> dict[tuple[str, str], dict[str, object]]:
    return {
        (str(row["strategy_id"]), str(row.get("version") or "v1")): row
        for row in load_all_trading_definitions()
    }


def _definitions_by_key(definitions: Iterable[StrategyDefinitionRecord]) -> dict[tuple[str, str], StrategyDefinitionRecord]:
    return {(definition.strategy_id, definition.version): definition for definition in definitions}


def _has_non_empty_value(value: Any) -> bool:
    if value is None:
        return False
    if value == "":
        return False
    if value == []:
        return False
    if value == {}:
        return False
    return True


def _print_report(report: dict[str, object]) -> None:
    print(
        "dry_run={dry_run} inserted={inserted} patched={patched} missing_after={missing_after}".format(
            dry_run=str(report["dry_run"]).lower(),
            inserted=report["inserted_count"],
            patched=report["patched_count"],
            missing_after=report["missing_after_count"],
        )
    )
    before_ids = report["before"]["missing_selection_policy_strategy_ids"]
    after_ids = report["after"]["missing_selection_policy_strategy_ids"]
    print(
        "missing_selection_policy_before={before}".format(
            before=", ".join(before_ids) if before_ids else "none",
        )
    )
    print(
        "missing_selection_policy_after={after}".format(
            after=", ".join(after_ids) if after_ids else "none",
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
