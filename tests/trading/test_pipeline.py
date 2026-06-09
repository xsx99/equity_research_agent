from datetime import date, datetime, timezone

from src.trading.manual_review.requests import ManualTickerRequestService
from src.trading.repositories.in_memory import InMemoryTradingRepository
from src.trading.workflows.signal_snapshot import SignalPipeline
from src.trading.workflows.strategy_scoring import StrategyPipeline
from src.trading.workflows.universe_scan import UniverseScanPipeline
from src.trading.signals.sources import InMemorySignalSourceRepository, SourceRecord
from src.trading.signals.source_ingestion import SourceIngestionService
from src.trading.data_sources.universe import UniverseAsset, UniverseFilterConfig
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import CandidateScoreRecord, StrategyRunRecord
from src.trading.strategies.selector import (
    PrimarySelectionResult,
    SelectedTradeRecord,
    WatchCandidateRecord,
)


class _FakeUniverseProvider:
    def fetch_universe_assets(self):
        return [
            UniverseAsset("AAPL", "Apple", "common_stock", "NASDAQ", "Technology", "Hardware", 180.0, 90_000_000),
            UniverseAsset("MSFT", "Microsoft", "common_stock", "NASDAQ", "Technology", "Software", 320.0, 90_000_000),
        ]


class _FakeMarketProvider:
    def fetch_daily_bars(self, ticker, lookback_days):
        return [
            {"date": date(2026, 5, 29), "open": 100.0, "high": 102.0, "low": 99.0, "close": 100.0, "volume": 1_000_000},
            {"date": date(2026, 5, 30), "open": 100.0, "high": 104.0, "low": 99.0, "close": 103.0, "volume": 2_000_000},
        ]

    def fetch_context(self, ticker):
        return {"market_cap": 3_000_000_000_000}


class _FakeNewsProvider:
    def fetch_recent(self, ticker, limit):
        return []


class _RepositoryWithoutCandidateScores:
    def __init__(self) -> None:
        self.strategy_runs: list[StrategyRunRecord] = []
        self.saved_candidates: list[CandidateScoreRecord] = []
        self.saved_classifications: list[TradeClassificationRecord] = []
        self.saved_watch_candidates: list[WatchCandidateRecord] = []

    def load_active_strategy_definitions(self):
        return []

    def save_strategy_run(self, run):
        self.strategy_runs.append(run)

    def save_candidate_scores(self, candidates):
        self.saved_candidates.extend(candidates)

    def save_trade_classifications(self, classifications):
        self.saved_classifications.extend(classifications)

    def save_watch_candidates(self, watch_candidates):
        self.saved_watch_candidates.extend(watch_candidates)


class _FakeMatcher:
    def __init__(self, candidate: CandidateScoreRecord) -> None:
        self.candidate = candidate

    def match(self, snapshots, definitions, *, strategy_run_id):
        del snapshots, definitions, strategy_run_id
        return [self.candidate]


class _FakeSelector:
    def __init__(self, result: PrimarySelectionResult) -> None:
        self.result = result

    def select(self, candidates, definitions):
        del candidates, definitions
        return self.result


class _FakeClassifier:
    def __init__(self, classification: TradeClassificationRecord) -> None:
        self.classification = classification

    def classify_many(self, selected):
        return [self.classification] if selected else []


def test_signal_pipeline_merges_active_manual_requests_into_snapshot_job():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    universe = UniverseScanPipeline(
        provider=_FakeUniverseProvider(),
        config=UniverseFilterConfig(manual_exclude=("MSFT",)),
        now=lambda: now,
    ).run()
    manual_service = ManualTickerRequestService(now=lambda: now)
    request = manual_service.create("MSFT", "please review", "review_only")
    sources = InMemorySignalSourceRepository()
    for ticker in ("AAPL", "MSFT"):
        sources.add(
            SourceRecord(
                ticker,
                "technical",
                "fixture",
                "market_bars",
                f"{ticker}-bars",
                now,
                now,
                now,
                now,
                {
                    "bars": [
                        {"date": date(2026, 5, 29), "open": 100.0, "high": 102.0, "low": 99.0, "close": 100.0, "volume": 1_000_000},
                        {"date": date(2026, 5, 30), "open": 100.0, "high": 104.0, "low": 99.0, "close": 103.0, "volume": 2_000_000},
                    ]
                },
            )
        )

    snapshots = SignalPipeline(
        source_repository=sources,
        manual_request_service=manual_service,
    ).build_pre_open_snapshots(
        universe_result=universe,
        decision_time=now,
    )

    assert [snapshot.ticker for snapshot in snapshots] == ["AAPL", "MSFT"]
    manual_snapshot = snapshots[1]
    assert manual_snapshot.selection_source == "manual_request"
    assert manual_snapshot.manual_request_id == request.request_id
    assert manual_service.load_active()[0].latest_result_status == "ordinary_watch"


def test_signal_pipeline_can_refresh_source_records_before_building_snapshots():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    universe = UniverseScanPipeline(
        provider=_FakeUniverseProvider(),
        config=UniverseFilterConfig(manual_exclude=("MSFT",)),
        now=lambda: now,
    ).run()
    source_repository = InMemorySignalSourceRepository()
    artifact_repository = InMemoryTradingRepository()
    ingestion_service = SourceIngestionService(
        market_provider=_FakeMarketProvider(),
        news_provider=_FakeNewsProvider(),
        source_repository=source_repository,
        artifact_repository=artifact_repository,
        provider_name="fixture",
        now=lambda: now,
        sleeper=lambda seconds: None,
    )

    snapshots = SignalPipeline(
        source_repository=source_repository,
        manual_request_service=ManualTickerRequestService(now=lambda: now),
        source_ingestion_service=ingestion_service,
    ).build_pre_open_snapshots(
        universe_result=universe,
        decision_time=now,
    )

    assert [snapshot.ticker for snapshot in snapshots] == ["AAPL"]
    assert snapshots[0].source_freshness_json["technical"] == "fresh"
    assert snapshots[0].signal_json["technical"]["return_1d"] == 0.03
    assert artifact_repository.source_ingestion_runs[0].run_type == "pre_open"


def test_strategy_pipeline_records_manual_request_results_without_in_memory_repository_state():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    manual_service = ManualTickerRequestService(now=lambda: now)
    request = manual_service.create("AAPL", "please review", "paper_trade_eligible")
    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-1",
        strategy_run_id="strategy-run-1",
        signal_snapshot_id="snapshot-1",
        ticker="AAPL",
        strategy_id="relative_strength_rotation_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        candidate_score=0.8,
        direction="bullish",
        action="enter_long",
        typical_horizon="swing",
        core_signal_evidence={},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=[],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="manual_request",
        manual_request_id=request.request_id,
        selection_reason="fixture",
        rejection_reason=None,
        benchmark_context={},
        decision_time=now,
        available_for_decision_at=now,
        source_record_refs_json=[],
        candidate_status="actionable",
    )
    selected = SelectedTradeRecord(
        candidate=candidate,
        selected_expression_bucket_id="long_stock",
        selected_expression_bucket_version="v1",
        selected_expression_bucket_config={"default_trade_identity": "tactical_stock_trade"},
        fallback_expression_bucket_ids=("defined_risk_directional_option",),
        expression_selection_context={
            "selected_expression_bucket_id": "long_stock",
            "fallback_expression_bucket_ids": ["defined_risk_directional_option"],
        },
        selection_context={},
    )
    classification = TradeClassificationRecord(
        trade_classification_id="classification-1",
        candidate_score_id=candidate.candidate_score_id,
        strategy_run_id=candidate.strategy_run_id,
        ticker=candidate.ticker,
        selected_strategy_id=candidate.strategy_id,
        selected_strategy_version=candidate.strategy_version,
        expression_bucket_id="long_stock",
        expression_bucket_version="v1",
        trade_identity="tactical_stock_trade",
        watch_type=None,
        direction=candidate.direction,
        intended_horizon=candidate.typical_horizon,
        exit_policy="strategy_invalidators_or_target_horizon",
        result_status="actionable_trade",
        classification_reason="fixture",
        selected_strategy_context_json={},
        decision_time=now,
    )
    repository = _RepositoryWithoutCandidateScores()
    selection = PrimarySelectionResult(
        selected_trades=(selected,),
        watch_candidates=(),
    )

    result = StrategyPipeline(
        repository=repository,
        manual_request_service=manual_service,
        matcher=_FakeMatcher(candidate),
        selector=_FakeSelector(selection),
        classifier=_FakeClassifier(classification),
    ).run(
        snapshots=(),
        decision_time=now,
    )

    assert len(result.candidates) == 1
    assert len(result.selected_trades) == 1
    assert result.selected_trades[0].fallback_expression_bucket_ids == ("defined_risk_directional_option",)
    assert result.watch_candidates == ()
    assert manual_service.load_active()[0].latest_result_status == "actionable_trade"


def test_strategy_pipeline_persists_watch_candidates_separately():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    manual_service = ManualTickerRequestService(now=lambda: now)
    request = manual_service.create("AAPL", "please review", "review_only")
    candidate = CandidateScoreRecord(
        candidate_score_id="candidate-watch-1",
        strategy_run_id="strategy-run-1",
        signal_snapshot_id="snapshot-1",
        ticker="AAPL",
        strategy_id="strong_theme_no_clear_near_term_entry_v1",
        strategy_version="v1",
        strategy_definition_id="definition-1",
        candidate_score=0.66,
        direction="neutral",
        action="no_trade",
        typical_horizon="swing",
        core_signal_evidence={"events_news.catalyst_quality_score": 0.95},
        missing_required_signals=[],
        unsupported_missing_signal_families=[],
        invalidators=[],
        risk_tags=[],
        macro_compatibility="allowed",
        selection_source="manual_request",
        manual_request_id=request.request_id,
        selection_reason="fixture",
        rejection_reason="no_clean_entry",
        benchmark_context={},
        decision_time=now,
        available_for_decision_at=now,
        source_record_refs_json=[],
        candidate_status="watch",
    )
    watch = WatchCandidateRecord(
        watch_candidate_id="watch-1",
        candidate=candidate,
        watch_strategy_id=candidate.strategy_id,
        watch_strategy_version=candidate.strategy_version,
        watch_type="catalyst_watch",
        result_status="catalyst_watch",
        watch_reason="entry is not clean yet",
        selection_context={"candidate_score_id": candidate.candidate_score_id},
    )
    repository = _RepositoryWithoutCandidateScores()
    selection = PrimarySelectionResult(
        selected_trades=(),
        watch_candidates=(watch,),
    )

    result = StrategyPipeline(
        repository=repository,
        manual_request_service=manual_service,
        matcher=_FakeMatcher(candidate),
        selector=_FakeSelector(selection),
        classifier=_FakeClassifier(
            TradeClassificationRecord(
                trade_classification_id="unused",
                candidate_score_id="unused",
                strategy_run_id="unused",
                ticker="AAPL",
                selected_strategy_id="unused",
                selected_strategy_version="v1",
                expression_bucket_id="unused",
                expression_bucket_version="v1",
                trade_identity="tactical_stock_trade",
                watch_type=None,
                direction="bullish",
                intended_horizon="swing",
                exit_policy="unused",
                result_status="actionable_trade",
                classification_reason="unused",
                selected_strategy_context_json={},
                decision_time=now,
            )
        ),
    ).run(
        snapshots=(),
        decision_time=now,
    )

    assert result.selected_trades == ()
    assert result.watch_candidates == (watch,)
    assert repository.saved_classifications == []
    assert repository.saved_watch_candidates == [watch]
    assert manual_service.load_active()[0].latest_result_status == "catalyst_watch"
