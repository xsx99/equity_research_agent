from __future__ import annotations

import json

from scripts import repair_trading_strategy_definitions
from src.trading.strategies.definitions import load_all_trading_definitions
from src.trading.strategies.matching import StrategyDefinitionRecord


def _seed_definitions(*, missing_selection_policy_for: str | None = None) -> list[StrategyDefinitionRecord]:
    definitions: list[StrategyDefinitionRecord] = []
    for row in load_all_trading_definitions():
        config_json = dict(row.get("config_json") or {})
        if row["strategy_id"] == missing_selection_policy_for:
            config_json.pop("selection_policy", None)
        definitions.append(
            StrategyDefinitionRecord.from_mapping(
                {
                    **row,
                    "strategy_definition_id": f"seed-{row['strategy_id']}",
                    "config_json": config_json,
                    "source": "seed",
                }
            )
        )
    return definitions


def _legacy_oversold_row() -> StrategyDefinitionRecord:
    oversold = next(
        row for row in load_all_trading_definitions()
        if row["strategy_id"] == "oversold_bounce_v1"
    )
    return StrategyDefinitionRecord.from_mapping(
        {
            **oversold,
            "strategy_definition_id": "legacy-oversold",
            "config_json": {"required_signals": ["rsi_oversold"]},
            "source": "seed",
        }
    )


def test_find_seed_definition_issues_reports_missing_selection_policy_for_legacy_seed_rows():
    issues = repair_trading_strategy_definitions.find_seed_definition_issues(
        _seed_definitions(missing_selection_policy_for="oversold_bounce_v1")
    )

    assert issues["missing_selection_policy_strategy_ids"] == ["oversold_bounce_v1"]
    assert issues["missing_selection_policy_count"] == 1
    assert issues["missing_seed_definition_count"] == 0


def test_find_seed_definition_issues_reports_no_issue_when_catalog_seed_rows_are_complete():
    issues = repair_trading_strategy_definitions.find_seed_definition_issues(_seed_definitions())

    assert issues["missing_selection_policy_strategy_ids"] == []
    assert issues["missing_selection_policy_count"] == 0
    assert issues["missing_seed_definition_count"] == 0


def test_run_repair_dry_run_rolls_back_changes(monkeypatch):
    session = _FakeSession()
    repository = _FakeRepository(rows=[_legacy_oversold_row()])
    monkeypatch.setattr(
        repair_trading_strategy_definitions,
        "SqlAlchemyTradingRepository",
        lambda _session: repository,
    )

    report = repair_trading_strategy_definitions.run_repair(session=session, dry_run=True)

    assert session.rollback_calls == 1
    assert session.commit_calls == 0
    assert report["dry_run"] is True
    assert report["inserted_count"] > 0
    assert report["missing_after_count"] == 0


def test_run_repair_apply_commits_changes(monkeypatch):
    session = _FakeSession()
    repository = _FakeRepository(rows=[_legacy_oversold_row()])
    monkeypatch.setattr(
        repair_trading_strategy_definitions,
        "SqlAlchemyTradingRepository",
        lambda _session: repository,
    )

    report = repair_trading_strategy_definitions.run_repair(session=session, dry_run=False)

    assert session.commit_calls == 1
    assert session.rollback_calls == 0
    assert report["dry_run"] is False
    assert report["inserted_count"] > 0
    assert report["missing_after_count"] == 0


def test_main_prints_json_report(monkeypatch, capsys):
    session = _FakeSession()
    repository = _FakeRepository(rows=[_legacy_oversold_row()])
    monkeypatch.setattr(
        repair_trading_strategy_definitions,
        "SqlAlchemyTradingRepository",
        lambda _session: repository,
    )
    monkeypatch.setattr(
        repair_trading_strategy_definitions,
        "get_session",
        lambda: _FakeSessionManager(session),
    )

    exit_code = repair_trading_strategy_definitions.main(["--dry-run", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["missing_after_count"] == 0


class _FakeSession:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.rollback_calls = 0
        self.closed = 0

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1

    def close(self) -> None:
        self.closed += 1


class _FakeRepository:
    def __init__(self, *, rows: list[StrategyDefinitionRecord]) -> None:
        self.rows = list(rows)

    def load_strategy_definitions(self) -> list[StrategyDefinitionRecord]:
        return list(self.rows)

    def save_strategy_definition(self, definition: StrategyDefinitionRecord) -> None:
        self.rows = [
            item for item in self.rows
            if item.strategy_definition_id != definition.strategy_definition_id
        ]
        self.rows.append(definition)


class _FakeSessionManager:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    def __enter__(self) -> _FakeSession:
        return self.session
