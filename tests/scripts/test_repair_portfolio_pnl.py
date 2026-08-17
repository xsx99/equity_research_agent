from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts import repair_portfolio_pnl
from src.db.models.trading import PaperExecution, PaperOrder, PaperPosition, PortfolioSnapshot
from src.trading.portfolio.pnl import PortfolioPnlValidationError


class _FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)
        self.locked = False

    def filter_by(self, **criteria):
        return _FakeQuery(
            row
            for row in self.rows
            if all(getattr(row, key) == value for key, value in criteria.items())
        )

    def order_by(self, *_args):
        return self

    def with_for_update(self):
        self.locked = True
        return self

    def all(self):
        return list(self.rows)


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _FakeSession:
    def __init__(self, *, snapshots, orders, executions, positions, data_directory="/var/lib/postgresql/data"):
        self.rows = {
            PortfolioSnapshot: list(snapshots),
            PaperOrder: list(orders),
            PaperExecution: list(executions),
            PaperPosition: list(positions),
        }
        self.data_directory = data_directory
        self.commit_count = 0
        self.rollback_count = 0

    def query(self, model):
        return _FakeQuery(self.rows[model])

    def execute(self, _statement):
        return _ScalarResult(self.data_directory)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        return None


@pytest.fixture()
def repair_case():
    reset_at = datetime(2026, 6, 2, 13, 0, tzinfo=timezone.utc)
    before = _snapshot(reset_at - timedelta(days=1), equity=900_000, stock_value=0, realized=7, unrealized=8)
    reset = _snapshot(reset_at, equity=1_000_000, stock_value=0, metadata={"existing": "keep"})
    marked = _snapshot(reset_at + timedelta(hours=1), equity=1_000_100, stock_value=1_100)
    latest = _snapshot(reset_at + timedelta(hours=2), equity=1_000_200, stock_value=600)
    pre_order, pre_execution = _fill(
        "pre-buy", "AAPL", "enter_long", 1, 50, reset_at - timedelta(hours=2), cash=-50
    )
    pre_exit_order, pre_exit_execution = _fill(
        "pre-exit", "AAPL", "exit", 1, 50, reset_at - timedelta(hours=1), cash=-50
    )
    buy_order, buy_execution = _fill(
        "buy", "AAPL", "enter_long", 10, 100, reset_at + timedelta(minutes=1), cash=-1000
    )
    sell_order, sell_execution = _fill(
        "sell", "AAPL", "reduce", 5, 120, reset_at + timedelta(hours=1, minutes=30), cash=-600
    )
    position = SimpleNamespace(
        ticker="AAPL",
        quantity=Decimal("5"),
        average_cost=Decimal("100"),
        status="open",
        opened_at=reset_at + timedelta(minutes=1),
        updated_at=reset_at + timedelta(hours=2),
        closed_at=None,
    )
    return _FakeSession(
        snapshots=[before, reset, marked, latest],
        orders=[pre_order, pre_exit_order, buy_order, sell_order],
        executions=[pre_execution, pre_exit_execution, buy_execution, sell_execution],
        positions=[position],
    )


def test_dry_run_reports_changes_without_mutating_rows(repair_case):
    latest = repair_case.rows[PortfolioSnapshot][-1]
    sell = repair_case.rows[PaperExecution][-1]

    report = repair_portfolio_pnl.run_repair(
        session=repair_case,
        apply=False,
        starting_equity=1_000_000,
    )

    assert report["status"] == "dry_run"
    assert report["snapshot_repair_count"] == 2
    assert report["cash_effect_repair_count"] == 1
    assert report["earliest_snapshot_to_update"] == "2026-06-02T13:00:00+00:00"
    assert report["latest_snapshot_to_update"] == "2026-06-02T15:00:00+00:00"
    assert report["validation_errors"] == []
    assert report["latest_realized_pnl"] == pytest.approx(100)
    assert report["latest_unrealized_pnl"] == pytest.approx(100)
    assert latest.realized_pnl == Decimal("0")
    assert sell.net_cash_effect == Decimal("-600")
    assert repair_case.commit_count == 0
    assert repair_case.rollback_count == 1


def test_apply_commits_snapshot_metadata_and_positive_sell_cash_effect(repair_case):
    before, reset, marked, latest = repair_case.rows[PortfolioSnapshot]
    sell = repair_case.rows[PaperExecution][-1]

    report = repair_portfolio_pnl.run_repair(
        session=repair_case,
        apply=True,
        starting_equity=1_000_000,
    )

    assert report["status"] == "applied"
    assert repair_case.commit_count == 1
    assert before.realized_pnl == Decimal("7")
    assert before.unrealized_pnl == Decimal("8")
    assert reset.metadata_json["existing"] == "keep"
    assert marked.realized_pnl == Decimal("0")
    assert marked.unrealized_pnl == Decimal("0")
    assert latest.realized_pnl == Decimal("100.0")
    assert latest.unrealized_pnl == Decimal("100.0")
    assert latest.metadata_json["pnl_calculation_method"] == "weighted_average_stock_fills_v1"
    assert sell.net_cash_effect == Decimal("600.0")


def test_second_apply_is_idempotent(repair_case):
    repair_portfolio_pnl.run_repair(session=repair_case, apply=True, starting_equity=1_000_000)

    report = repair_portfolio_pnl.run_repair(session=repair_case, apply=True, starting_equity=1_000_000)

    assert report["snapshot_repair_count"] == 0
    assert report["cash_effect_repair_count"] == 0


def test_latest_clean_reset_isolated_from_earlier_lifecycle(repair_case):
    report = repair_portfolio_pnl.run_repair(session=repair_case, apply=False, starting_equity=1_000_000)

    assert report["boundary"] == "2026-06-02T13:00:00+00:00"
    assert report["excluded_pre_boundary_snapshot_count"] == 1
    assert report["excluded_pre_boundary_fill_count"] == 2


def test_ambiguous_same_timestamp_reset_rolls_back(repair_case):
    reset = repair_case.rows[PortfolioSnapshot][1]
    repair_case.rows[PortfolioSnapshot].append(
        _snapshot(reset.snapshot_time, equity=1_000_000, stock_value=0)
    )

    with pytest.raises(PortfolioPnlValidationError, match="ambiguous_clean_reset"):
        repair_portfolio_pnl.run_repair(session=repair_case, apply=True, starting_equity=1_000_000)

    assert repair_case.commit_count == 0
    assert repair_case.rollback_count == 1


def test_latest_position_cost_difference_within_tolerance_is_diagnostic(repair_case):
    repair_case.rows[PaperPosition][0].average_cost = Decimal("100.005")

    report = repair_portfolio_pnl.run_repair(session=repair_case, apply=False, starting_equity=1_000_000)

    assert report["position_mismatches"] == []
    assert report["cost_basis_diagnostics"][0]["ticker"] == "AAPL"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("quantity", Decimal("4"), "quantity_mismatch"),
        ("average_cost", Decimal("101"), "average_cost_mismatch"),
    ],
)
def test_latest_position_mismatch_blocks_all_writes(repair_case, field, value, message):
    setattr(repair_case.rows[PaperPosition][0], field, value)

    with pytest.raises(PortfolioPnlValidationError, match=message):
        repair_portfolio_pnl.run_repair(session=repair_case, apply=True, starting_equity=1_000_000)

    assert repair_case.rows[PaperExecution][-1].net_cash_effect == Decimal("-600")
    assert repair_case.rows[PortfolioSnapshot][-1].realized_pnl == Decimal("0")
    assert repair_case.commit_count == 0
    assert repair_case.rollback_count == 1


def test_dry_run_returns_structured_position_mismatch(repair_case):
    repair_case.rows[PaperPosition][0].quantity = Decimal("4")

    report = repair_portfolio_pnl.run_repair(
        session=repair_case,
        apply=False,
        starting_equity=1_000_000,
    )

    assert report["status"] == "blocked"
    assert report["validation_errors"] == ["quantity_mismatch:AAPL:4.0!=5.0"]
    assert report["position_mismatches"] == [
        {
            "kind": "quantity",
            "ticker": "AAPL",
            "mirrored": 4.0,
            "replayed": 5.0,
        }
    ]
    assert repair_case.rollback_count == 1


def test_dry_run_reports_all_position_mismatches_and_complete_scope(repair_case):
    repair_case.rows[PaperPosition][0].quantity = Decimal("4")
    repair_case.rows[PaperPosition].append(
        SimpleNamespace(
            ticker="MSFT",
            quantity=Decimal("2"),
            average_cost=Decimal("50"),
            status="open",
            opened_at=repair_case.rows[PortfolioSnapshot][1].snapshot_time,
            updated_at=repair_case.rows[PortfolioSnapshot][-1].snapshot_time,
            closed_at=None,
        )
    )

    report = repair_portfolio_pnl.run_repair(
        session=repair_case,
        apply=False,
        starting_equity=1_000_000,
    )

    assert report["status"] == "blocked"
    assert report["boundary"] == "2026-06-02T13:00:00+00:00"
    assert report["active_snapshot_count"] == 3
    assert report["tolerances"]["quantity"] > 0
    assert report["snapshot_repair_count"] == 2
    assert report["earliest_snapshot_to_update"] == "2026-06-02T13:00:00+00:00"
    assert report["latest_snapshot_to_update"] == "2026-06-02T15:00:00+00:00"
    assert report["unverified_historical_snapshot_count"] == 1
    assert report["earliest_unverified_historical_snapshot"] == "2026-06-02T14:00:00+00:00"
    assert report["latest_unverified_historical_snapshot"] == "2026-06-02T14:00:00+00:00"
    assert report["position_mismatches"] == [
        {"kind": "quantity", "ticker": "AAPL", "mirrored": 4.0, "replayed": 5.0},
        {"kind": "quantity", "ticker": "MSFT", "mirrored": 2.0, "replayed": 0.0},
    ]


def test_nonflat_historical_inventory_is_skipped_instead_of_fabricating_unrealized(repair_case):
    historical = repair_case.rows[PortfolioSnapshot][2]

    report = repair_portfolio_pnl.run_repair(
        session=repair_case,
        apply=False,
        starting_equity=1_000_000,
    )

    assert report["unverified_historical_snapshot_count"] == 1
    assert report["earliest_unverified_historical_snapshot"] == historical.snapshot_time.isoformat()
    assert report["latest_unverified_historical_snapshot"] == historical.snapshot_time.isoformat()
    assert historical.unrealized_pnl == Decimal("0")


def test_historical_inventory_without_fill_blocks_even_when_latest_account_is_flat():
    reset_at = datetime(2026, 6, 2, 13, 0, tzinfo=timezone.utc)
    reset = _snapshot(reset_at, equity=1_000_000, stock_value=0)
    unexplained_inventory = _snapshot(
        reset_at + timedelta(hours=1),
        equity=1_000_010,
        stock_value=100,
    )
    later_flat = _snapshot(
        reset_at + timedelta(hours=2),
        equity=999_900,
        stock_value=0,
    )
    session = _FakeSession(
        snapshots=[reset, unexplained_inventory, later_flat],
        orders=[],
        executions=[],
        positions=[],
    )

    report = repair_portfolio_pnl.run_repair(
        session=session,
        apply=False,
        starting_equity=1_000_000,
    )

    assert report["status"] == "blocked"
    assert report["validation_errors"] == [
        "historical_inventory_mismatch:2026-06-02T14:00:00+00:00:snapshot=True:replay=False"
    ]
    assert unexplained_inventory.unrealized_pnl == Decimal("0")


def test_apply_rejects_historical_inventory_without_fill():
    reset_at = datetime(2026, 6, 2, 13, 0, tzinfo=timezone.utc)
    session = _FakeSession(
        snapshots=[
            _snapshot(reset_at, equity=1_000_000, stock_value=0),
            _snapshot(reset_at + timedelta(hours=1), equity=1_000_010, stock_value=100),
            _snapshot(reset_at + timedelta(hours=2), equity=999_900, stock_value=0),
        ],
        orders=[],
        executions=[],
        positions=[],
    )

    with pytest.raises(PortfolioPnlValidationError, match="historical_inventory_mismatch"):
        repair_portfolio_pnl.run_repair(
            session=session,
            apply=True,
            starting_equity=1_000_000,
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1


def test_replay_validation_failure_rolls_back_everything(repair_case):
    order, execution = _fill(
        "oversell",
        "AAPL",
        "exit",
        99,
        120,
        repair_case.rows[PortfolioSnapshot][-1].snapshot_time,
        cash=-11_880,
    )
    repair_case.rows[PaperOrder].append(order)
    repair_case.rows[PaperExecution].append(execution)

    with pytest.raises(PortfolioPnlValidationError, match="oversell"):
        repair_portfolio_pnl.run_repair(session=repair_case, apply=True, starting_equity=1_000_000)

    assert repair_case.rows[PaperExecution][-2].net_cash_effect == Decimal("-600")
    assert repair_case.commit_count == 0
    assert repair_case.rollback_count == 1


@pytest.mark.parametrize("path", ["/tmp/postgres", "/run/postgresql", "/dev/shm/pgdata"])
def test_unsafe_postgres_storage_blocks_apply(repair_case, path):
    repair_case.data_directory = path

    with pytest.raises(RuntimeError, match="unsafe_postgres_data_directory"):
        repair_portfolio_pnl.run_repair(session=repair_case, apply=True, starting_equity=1_000_000)

    assert repair_case.commit_count == 0
    assert repair_case.rollback_count == 1


def test_safe_postgres_storage_permits_apply(repair_case):
    repair_case.data_directory = "/var/lib/postgresql/data"

    report = repair_portfolio_pnl.run_repair(session=repair_case, apply=True, starting_equity=1_000_000)

    assert report["data_directory"] == "/var/lib/postgresql/data"
    assert report["status"] == "applied"


@pytest.mark.parametrize(("argv", "expected_apply"), [(["--json"], False), (["--apply", "--json"], True)])
def test_main_is_dry_run_by_default_and_apply_is_explicit(capsys, argv, expected_apply):
    session = _FakeSession(snapshots=[], orders=[], executions=[], positions=[])
    with (
        patch.object(repair_portfolio_pnl, "SessionLocal", return_value=session),
        patch.object(
            repair_portfolio_pnl,
            "run_repair",
            return_value={"status": "applied" if expected_apply else "dry_run"},
        ) as run_repair,
    ):
        exit_code = repair_portfolio_pnl.main(argv)

    assert exit_code == 0
    assert run_repair.call_args.kwargs["apply"] is expected_apply
    assert '"status"' in capsys.readouterr().out


def _snapshot(at, *, equity, stock_value, realized=0, unrealized=0, metadata=None):
    return SimpleNamespace(
        snapshot_time=at,
        account_equity=Decimal(str(equity)),
        stock_market_value=Decimal(str(stock_value)),
        option_market_value=Decimal("0"),
        realized_pnl=Decimal(str(realized)),
        unrealized_pnl=Decimal(str(unrealized)),
        metadata_json=dict(metadata or {}),
    )


def _fill(name, ticker, action, quantity, price, executed_at, *, cash):
    order_id = f"{name}-order"
    order = SimpleNamespace(
        paper_order_id=order_id,
        ticker=ticker,
        action=action,
        status="filled",
    )
    execution = SimpleNamespace(
        paper_execution_id=f"{name}-execution",
        paper_order_id=order_id,
        ticker=ticker,
        quantity=Decimal(str(quantity)),
        fill_price=Decimal(str(price)),
        executed_at=executed_at,
        net_cash_effect=Decimal(str(cash)),
    )
    return order, execution
