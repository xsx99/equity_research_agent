from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock
from unittest.mock import patch

from src.research.repositories import research_repository as repository
from src.research.workflows.batch_research import ResearchPipeline


class TestMarketTradeDateNormalization:
    def test_same_day_eval_candidates_use_market_trade_date_not_utc_date(self):
        run = MagicMock()
        output = MagicMock()
        run.as_of = datetime(2026, 3, 25, 3, 13, 16, tzinfo=timezone.utc)  # 2026-03-24 23:13 ET
        output.time_horizon = "1d"

        session = MagicMock()
        session.query.return_value.join.return_value.filter.return_value.all.return_value = [
            (run, output)
        ]

        results = repository.get_same_day_eval_candidates(
            session,
            trade_date=date(2026, 3, 24),
        )

        assert results == [(run, output)]

    def test_reusable_global_context_uses_market_trade_date_not_utc_date(self):
        pipeline = ResearchPipeline(
            session=MagicMock(),
            agent=MagicMock(),
            tool_registry=MagicMock(),
        )

        as_of = datetime(2026, 3, 25, 3, 13, 16, tzinfo=timezone.utc)  # 2026-03-24 23:13 ET

        with patch(
            "src.research.workflows.batch_research.repository.get_latest_global_context_for_trade_date",
            return_value={"ok": True},
        ) as mock_get_latest:
            result = pipeline._get_reusable_global_context(as_of)

            assert result == {"ok": True}
            mock_get_latest.assert_called_once_with(
                pipeline.session,
                trade_date=date(2026, 3, 24),
            )
