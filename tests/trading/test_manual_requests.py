from datetime import datetime, timezone

from src.trading.manual_review.requests import ManualTickerRequestService


def test_manual_request_service_keeps_requests_active_until_dismissed():
    service = ManualTickerRequestService(now=lambda: datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc))

    request = service.create(" aapl ", reason="user wants review", mode="review_only")
    service.record_evaluation(
        request.request_id,
        result_status="ordinary_watch",
        signal_snapshot_id="snapshot-1",
    )

    active = service.load_active()
    assert [item.ticker for item in active] == ["AAPL"]
    assert active[0].last_evaluated_at == datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    assert active[0].latest_result_status == "ordinary_watch"

    service.dismiss(request.request_id)

    assert service.load_active() == ()


def test_manual_request_service_supports_paper_trade_eligible_and_cancel():
    service = ManualTickerRequestService(now=lambda: datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc))

    request = service.create("nvda", reason="earnings follow through", mode="paper_trade_eligible")

    assert request.mode == "paper_trade_eligible"
    service.cancel(request.request_id)
    assert service.load_active() == ()


def test_manual_request_service_replaces_existing_active_request_for_same_ticker():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    service = ManualTickerRequestService(now=lambda: now)

    original = service.create("aapl", reason="first review", mode="review_only")
    replacement = service.create(" AAPL ", reason="updated review", mode="paper_trade_eligible")

    active = service.load_active()

    assert replacement.request_id != original.request_id
    assert [item.request_id for item in active] == [replacement.request_id]
    assert active[0].reason == "updated review"
    assert active[0].mode == "paper_trade_eligible"
    assert service._requests[original.request_id].status == "cancelled"
    assert service._requests[original.request_id].cancelled_at == now
