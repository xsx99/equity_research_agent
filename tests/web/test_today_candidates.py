from __future__ import annotations

from src.web.presenters.today_candidates import build_today_candidates_view


def test_build_today_candidates_view_groups_duplicate_candidate_rows_by_ticker():
    payload = build_today_candidates_view(
        rows=(
            {
                "ticker": "AAPL",
                "decision_time": "2026-06-16T13:35:00Z",
                "current_outcome_label": "Ready for review",
                "operator_summary": "Momentum setup with clean catalyst.",
                "trade_identity_label": "Action Now",
                "strategy_label": "Gap continuation",
                "strategy_match": "gap_continuation_v1",
                "candidate_score": 0.91,
                "detail_internal_ids": {"strategy_match": "gap_continuation_v1"},
            },
            {
                "ticker": "AAPL",
                "decision_time": "2026-06-16T13:34:00Z",
                "current_outcome_label": "Ready for review",
                "operator_summary": "Alternative pullback setup.",
                "trade_identity_label": "Action Now",
                "strategy_label": "Pullback reclaim",
                "strategy_match": "pullback_reclaim_v1",
                "candidate_score": 0.77,
                "detail_internal_ids": {"strategy_match": "pullback_reclaim_v1"},
            },
            {
                "ticker": "AAPL",
                "decision_time": "2026-06-16T13:33:00Z",
                "current_outcome_label": "Ready for review",
                "operator_summary": "Secondary continuation lens.",
                "trade_identity_label": "Action Now",
                "strategy_label": "RS breakout",
                "strategy_match": "rs_breakout_v1",
                "candidate_score": 0.73,
                "detail_internal_ids": {"strategy_match": "rs_breakout_v1"},
            },
            {
                "ticker": "AAPL",
                "decision_time": "2026-06-16T13:32:00Z",
                "current_outcome_label": "Ready for review",
                "operator_summary": "Lower-ranked reversal setup.",
                "trade_identity_label": "Watch Only",
                "strategy_label": "Reversal try",
                "strategy_match": "reversal_try_v1",
                "candidate_score": 0.41,
                "detail_internal_ids": {"strategy_match": "reversal_try_v1"},
            },
            {
                "ticker": "MSFT",
                "decision_time": "2026-06-16T13:31:00Z",
                "current_outcome_label": "No clean entry, so no trade",
                "operator_summary": "Setup faded after catalyst check.",
                "trade_identity_label": "Watch Only",
                "strategy_label": "Valuation repair setup",
                "strategy_match": "valuation_repair_quality_software_v1",
                "candidate_score": 0.28,
                "detail_internal_ids": {"strategy_match": "valuation_repair_quality_software_v1"},
            },
        ),
        manual_requests=(),
        themes=(),
        active_universe_filter=None,
        portfolio_intents=(),
        relationships=(),
        peer_baskets=(),
    )

    assert [row["ticker"] for row in payload["decision_readout"]] == ["AAPL", "MSFT"]
    assert payload["decision_readout"][0]["duplicate_count"] == 4
    assert len(payload["decision_readout"][0]["alternatives"]) == 3
    assert payload["decision_readout"][0]["primary_reason"] == "Momentum setup with clean catalyst."
    assert payload["decision_readout"][0]["confidence"] == 0.91
    assert payload["decision_readout"][0]["alternatives"][0]["confidence"] == 0.77


def test_build_today_candidates_view_separates_manual_review_queue_and_action_queue():
    payload = build_today_candidates_view(
        rows=(
            {
                "ticker": "NVDA",
                "decision_time": "2026-06-16T13:10:00Z",
                "current_outcome_label": "Ready for review",
                "operator_summary": "Scanner still favors continuation after earnings read-through.",
                "trade_identity_label": "Action Now",
                "strategy_label": "Gap continuation",
                "strategy_match": "gap_continuation_v1",
                "candidate_score": 0.88,
                "detail_internal_ids": {"strategy_match": "gap_continuation_v1"},
            },
        ),
        manual_requests=(
            {
                "manual_ticker_request_id": "request-1",
                "ticker": "TSLA",
                "reason": "post-event review",
                "mode_label": "Review Only",
                "status_label": "Pinned",
                "operator_summary": "Review Only because post-event review. Latest result: Still on watch.",
                "last_evaluated_label": "6m ago",
                "linked_detail_url": "/today?tab=trades&ticker=TSLA&detail_tab=decisions",
                "decision_state_label": "Enter Long",
                "execution_state_label": "Risk blocked",
                "latest_block_reason": "Awaiting fresh event-risk snapshot",
                "dismiss_form_action": "/today/manual-requests/request-1/dismiss",
                "degraded_linkage_copy": None,
            },
            {
                "manual_ticker_request_id": "request-2",
                "ticker": "META",
                "reason": "policy headline follow-up",
                "mode_label": "Paper Trade Eligible",
                "status_label": "Pinned",
                "operator_summary": "Paper Trade Eligible because policy headline follow-up.",
                "last_evaluated_label": None,
                "linked_detail_url": None,
                "decision_state_label": "Pending evaluation",
                "execution_state_label": "Unlinked",
                "latest_block_reason": None,
                "dismiss_form_action": "/today/manual-requests/request-2/dismiss",
                "degraded_linkage_copy": "Backend audit linkage has not reached a signal snapshot yet.",
            },
        ),
        themes=(),
        active_universe_filter=None,
        portfolio_intents=(),
        relationships=(),
        peer_baskets=(),
    )

    assert [row["ticker"] for row in payload["manual_review_queue"]] == ["TSLA", "META"]
    assert payload["manual_review_queue"][0]["linked_detail_url"] == "/today?tab=trades&ticker=TSLA&detail_tab=decisions"
    assert payload["manual_review_queue"][1]["degraded_linkage_copy"] == "Signal details not available yet."
    assert [row["ticker"] for row in payload["action_queue"]] == ["TSLA", "NVDA", "META"]


def test_build_today_candidates_view_reports_agent_and_manual_run_times_separately():
    payload = build_today_candidates_view(
        rows=(
            {
                "ticker": "AAPL",
                "decision_time": "2026-07-07T12:50:00Z",
                "selection_source": "manual_request",
                "current_outcome_label": "Still on watch",
                "operator_summary": "Manual review follow-up.",
                "trade_identity_label": "Watch Only",
                "strategy_label": "Catalyst watch",
                "strategy_match": "manual_watch_v1",
                "candidate_score": 0.35,
                "detail_internal_ids": {"selection_source": "manual_request"},
            },
            {
                "ticker": "MU",
                "decision_time": "2026-07-07T12:45:00Z",
                "selection_source": "scanner",
                "current_outcome_label": "Direct Negative Catalyst",
                "operator_summary": "Scanner candidate.",
                "trade_identity_label": "",
                "strategy_label": "Catalyst Breakout V1",
                "strategy_match": "catalyst_breakout_v1",
                "candidate_score": 0.35,
                "detail_internal_ids": {"selection_source": "scanner"},
            },
        ),
        manual_requests=(
            {
                "manual_ticker_request_id": "request-aapl",
                "ticker": "AAPL",
                "reason": "manual follow-up",
                "mode_label": "Review Only",
                "status_label": "Pinned",
                "operator_summary": "Review Only because manual follow-up.",
                "last_evaluated_label": None,
                "linked_detail_url": None,
                "decision_state_label": "Pending evaluation",
                "execution_state_label": "Unlinked",
                "latest_block_reason": None,
                "dismiss_form_action": "/today/manual-requests/request-aapl/dismiss",
                "degraded_linkage_copy": None,
            },
        ),
        themes=(),
        active_universe_filter=None,
        portfolio_intents=(),
        relationships=(),
        peer_baskets=(),
    )

    assert payload["last_run_at"] == "2026-07-07T12:50:00Z"
    assert payload["agent_last_run_at"] == "2026-07-07T12:45:00Z"
    assert payload["manual_last_run_at"] == "2026-07-07T12:50:00Z"


def test_build_today_candidates_view_filters_smoke_rows_and_uses_plain_linkage_copy():
    payload = build_today_candidates_view(
        rows=(
            {
                "ticker": "NVDA",
                "decision_time": "2026-06-16T13:10:00Z",
                "current_outcome_label": "Ready for review",
                "operator_summary": "codex live preopen verification",
                "trade_identity_label": "Action Now",
                "strategy_label": "Lpsmoke 181857",
                "strategy_match": "lpsmoke_181857",
                "candidate_score": 0.88,
                "detail_internal_ids": {"strategy_match": "lpsmoke_181857"},
            },
            {
                "ticker": "AAPL",
                "decision_time": "2026-06-16T13:09:00Z",
                "current_outcome_label": "Ready for review",
                "operator_summary": "Momentum setup with clean catalyst.",
                "trade_identity_label": "Action Now",
                "strategy_label": "Gap continuation",
                "strategy_match": "gap_continuation_v1",
                "candidate_score": 0.84,
                "detail_internal_ids": {"strategy_match": "gap_continuation_v1"},
            },
        ),
        manual_requests=(
            {
                "manual_ticker_request_id": "request-1",
                "ticker": "NVDA",
                "reason": "codex live preopen order smoke:NVDA",
                "mode_label": "Review Only",
                "status_label": "Pinned",
                "operator_summary": "Review Only because codex live preopen order smoke:NVDA.",
                "last_evaluated_label": None,
                "linked_detail_url": None,
                "decision_state_label": "Pending evaluation",
                "execution_state_label": "Unlinked",
                "latest_block_reason": None,
                "dismiss_form_action": "/today/manual-requests/request-1/dismiss",
                "degraded_linkage_copy": None,
            },
            {
                "manual_ticker_request_id": "request-2",
                "ticker": "TSLA",
                "reason": "post-event review",
                "mode_label": "Review Only",
                "status_label": "Pinned",
                "operator_summary": "Review Only because post-event review.",
                "last_evaluated_label": None,
                "linked_detail_url": None,
                "decision_state_label": "Pending evaluation",
                "execution_state_label": "Unlinked",
                "latest_block_reason": None,
                "dismiss_form_action": "/today/manual-requests/request-2/dismiss",
                "degraded_linkage_copy": None,
            },
        ),
        themes=(),
        active_universe_filter=None,
        portfolio_intents=(),
        relationships=(),
        peer_baskets=(),
    )

    assert [row["ticker"] for row in payload["decision_readout"]] == ["AAPL"]
    assert [row["ticker"] for row in payload["manual_review_queue"]] == ["TSLA"]
    assert payload["manual_review_queue"][0]["degraded_linkage_copy"] == "Signal details not available yet."
    assert [row["ticker"] for row in payload["action_queue"]] == ["AAPL", "TSLA"]


def test_build_today_candidates_view_populates_signal_bullets_from_core_signal_evidence():
    payload = build_today_candidates_view(
        rows=(
            {
                "ticker": "AAPL",
                "decision_time": "2026-06-16T13:35:00Z",
                "current_outcome_label": "Ready for review",
                "operator_summary": "Momentum setup with clean catalyst.",
                "trade_identity_label": "Action Now",
                "strategy_label": "Gap continuation",
                "strategy_match": "gap_continuation_v1",
                "candidate_score": 0.91,
                "selection_reason": "relative strength and catalyst quality remain aligned",
                "core_signal_evidence": {
                    "technical.return_20d": 0.0826,
                    "technical.relative_volume": 0.78,
                    "fundamental.quality_score": 0.98,
                    "fundamental.revenue_growth_score": 0.65,
                    "fundamental.margin_trend_score": 0.93,
                    "events_news.sentiment_direction": "positive",
                    "events_news.high_signal_news_count_24h": 2,
                },
                "risk_tags": ["gap_risk", "momentum"],
                "invalidators": ["loses VWAP"],
                "detail_internal_ids": {"strategy_match": "gap_continuation_v1"},
            },
        ),
        manual_requests=(),
        themes=(),
        active_universe_filter=None,
        portfolio_intents=(),
        relationships=(),
        peer_baskets=(),
    )

    row = payload["decision_readout"][0]
    assert row["selection_reason"] == "relative strength and catalyst quality remain aligned"
    assert row["confidence"] == 0.91
    assert row["signal_bullets"] == (
        "Technical: 20d return 8.26%, relative volume 0.78.",
        "Fundamental: quality 0.98, revenue growth 0.65, margin trend 0.93.",
        "News: sentiment positive, 2 high-signal items / 24h.",
    )
    assert row["risk_tags"] == ("Risk tags: Gap Risk, momentum.",)
    assert row["invalidators"] == ("Invalidators: loses VWAP.",)


def test_build_today_candidates_view_attaches_recent_news_by_ticker():
    news = [
        {
            "title": "Raised guidance",
            "summary": "Management lifted the full-year outlook.",
            "time": "2026-06-16T12:45:00Z",
            "source": "Dow Jones",
            "sentiment": "positive",
            "event_type": "guidance",
        }
    ]

    payload = build_today_candidates_view(
        rows=(
            {
                "ticker": "aapl",
                "decision_time": "2026-06-16T13:35:00Z",
                "current_outcome_label": "Ready for review",
                "operator_summary": "Momentum setup with clean catalyst.",
                "trade_identity_label": "Action Now",
                "strategy_label": "Gap continuation",
                "strategy_match": "gap_continuation_v1",
                "candidate_score": 0.91,
                "detail_internal_ids": {"strategy_match": "gap_continuation_v1"},
            },
        ),
        manual_requests=(),
        themes=(),
        active_universe_filter=None,
        portfolio_intents=(),
        relationships=(),
        peer_baskets=(),
        news_by_ticker={"AAPL": news},
    )

    assert payload["decision_readout"][0]["news"] == tuple(news)
    assert payload["agent_candidates"][0]["news"] == tuple(news)
    assert payload["rows"][0]["news"] == tuple(news)


def test_build_today_candidates_view_adds_evaluation_timeline_in_decision_order():
    payload = build_today_candidates_view(
        rows=(
            {
                "ticker": "AAPL",
                "decision_time": "2026-06-16T13:35:00Z",
                "current_outcome_label": "Ready for review",
                "operator_summary": "Momentum setup with clean catalyst.",
                "trade_identity_label": "Action Now",
                "strategy_label": "Gap continuation",
                "strategy_match": "gap_continuation_v1",
                "candidate_score": 0.91,
                "detail_internal_ids": {"strategy_match": "gap_continuation_v1"},
            },
            {
                "ticker": "AAPL",
                "decision_time": "2026-06-16T13:10:00Z",
                "current_outcome_label": "Ready for review",
                "operator_summary": "Alternative pullback setup.",
                "trade_identity_label": "Action Now",
                "strategy_label": "Pullback reclaim",
                "strategy_match": "pullback_reclaim_v1",
                "candidate_score": 0.77,
                "detail_internal_ids": {"strategy_match": "pullback_reclaim_v1"},
            },
        ),
        manual_requests=(),
        themes=(),
        active_universe_filter=None,
        portfolio_intents=(),
        relationships=(),
        peer_baskets=(),
    )

    row = payload["decision_readout"][0]
    assert [item["strategy_label"] for item in row["evaluations"]] == ["Gap continuation", "Pullback reclaim"]
    assert row["evaluations"][0]["decision_time"] == "2026-06-16T13:35:00Z"
    assert row["evaluations"][0]["summary"] == "Momentum setup with clean catalyst."


def test_build_today_candidates_view_dedupes_identical_evaluation_rows():
    payload = build_today_candidates_view(
        rows=(
            {
                "ticker": "AAPL",
                "decision_time": "2026-06-16T13:35:00Z",
                "current_outcome_label": "Ready for review",
                "operator_summary": "Momentum setup with clean catalyst.",
                "trade_identity_label": "Action Now",
                "strategy_label": "Gap continuation",
                "strategy_match": "gap_continuation_v1",
                "candidate_score": 0.91,
                "detail_internal_ids": {"strategy_match": "gap_continuation_v1"},
            },
            {
                "ticker": "AAPL",
                "decision_time": "2026-06-16T13:35:00Z",
                "current_outcome_label": "Ready for review",
                "operator_summary": "Momentum setup with clean catalyst.",
                "trade_identity_label": "Action Now",
                "strategy_label": "Gap continuation",
                "strategy_match": "gap_continuation_v1",
                "candidate_score": 0.91,
                "detail_internal_ids": {"strategy_match": "gap_continuation_v1"},
            },
            {
                "ticker": "AAPL",
                "decision_time": "2026-06-16T13:10:00Z",
                "current_outcome_label": "Still on watch",
                "operator_summary": "Alternative pullback setup.",
                "trade_identity_label": "Watch Only",
                "strategy_label": "Pullback reclaim",
                "strategy_match": "pullback_reclaim_v1",
                "candidate_score": 0.77,
                "detail_internal_ids": {"strategy_match": "pullback_reclaim_v1"},
            },
        ),
        manual_requests=(),
        themes=(),
        active_universe_filter=None,
        portfolio_intents=(),
        relationships=(),
        peer_baskets=(),
    )

    row = payload["decision_readout"][0]
    assert [item["strategy_label"] for item in row["evaluations"]] == ["Gap continuation", "Pullback reclaim"]
    assert row["evaluation_count"] == 2
