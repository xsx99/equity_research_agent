from datetime import date, datetime, timezone

from src.trading.data_sources.provider_resilience import InMemoryProviderRequestRecorder
from src.trading.ranking.calendar import RankingSession
from src.trading.ranking.loader import RankingInputLoader


class _Calendar:
    def latest_completed_session(self, decision_time: datetime) -> RankingSession:
        return RankingSession(date(2026, 7, 20), datetime(2026, 7, 20, 20, tzinfo=timezone.utc))


class _BatchProvider:
    provider_name = "fake_market"

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def fetch_daily_bars_for_symbols(self, symbols, lookback_days):
        self.calls.append(tuple(symbols))
        assert lookback_days == 65
        return {
            ticker: [
                {"date": "2026-07-18", "close": 10.0, "volume": 100},
                {"date": "2026-07-20", "close": 11.0, "volume": 110},
                {"date": "2026-07-21", "close": 12.0, "volume": 120},
            ]
            for ticker in symbols
            if ticker != "BAD"
        }


def test_loader_uses_bounded_batch_requests_and_filters_to_last_completed_session():
    provider = _BatchProvider()
    recorder = InMemoryProviderRequestRecorder()
    loader = RankingInputLoader(
        provider=provider,
        calendar=_Calendar(),
        recorder=recorder,
        chunk_size=2,
    )

    result = loader.load(("aaa", "AAA", "bbb"), decision_time=datetime(2026, 7, 21, 13, 30, tzinfo=timezone.utc))

    assert provider.calls == [("AAA", "BBB"), ("SPY",)]
    assert result.requested_tickers == ("AAA", "BBB")
    assert tuple(result.bars_by_ticker) == ("AAA", "BBB")
    assert [bar.session_date.isoformat() for bar in result.bars_by_ticker["AAA"]] == ["2026-07-18", "2026-07-20"]
    assert result.benchmark_bars[-1].session_date.isoformat() == "2026-07-20"
    assert all(bar.available_for_decision_at == result.cutoff_session.scheduled_close for bar in result.benchmark_bars)
    assert len(recorder.runs) == 2
    assert all(run.status == "succeeded" for run in recorder.runs)


def test_loader_retains_partial_chunk_errors_without_falling_back_to_per_ticker_calls():
    class _PartialProvider(_BatchProvider):
        def fetch_daily_bars_for_symbols(self, symbols, lookback_days):
            if "BBB" in symbols:
                raise RuntimeError("batch unavailable")
            return super().fetch_daily_bars_for_symbols(symbols, lookback_days)

    provider = _PartialProvider()
    loader = RankingInputLoader(provider=provider, calendar=_Calendar(), chunk_size=2)

    result = loader.load(("AAA", "BBB"), decision_time=datetime(2026, 7, 21, 13, 30, tzinfo=timezone.utc))

    assert result.chunk_errors == {"AAA,BBB": "RuntimeError: batch unavailable"}
    assert tuple(result.bars_by_ticker) == ()
    assert result.benchmark_bars
