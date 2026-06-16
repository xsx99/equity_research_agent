from __future__ import annotations

import json
from datetime import datetime, timezone

from scripts import run_trading_signal_family_smoke


def _fake_global_context(as_of: datetime) -> dict[str, object]:
    assert as_of == datetime(2026, 6, 15, 15, 0, tzinfo=timezone.utc)
    return {
        "as_of": as_of.isoformat(),
        "indicators": {},
        "official_updates": [],
        "trump_updates": [
            {
                "source": "whitehouse.gov",
                "title": "President Trump discusses NVDA export controls",
                "summary": "Comments directly reference NVDA and chip export policy.",
                "published_at": "2026-06-15T14:30:00+00:00",
                "url": "https://example.test/trump-nvda",
            }
        ],
        "geopolitical_news": [],
    }


def test_run_fixture_smoke_returns_snapshot_families_and_candidate_evidence():
    result = run_trading_signal_family_smoke.run_fixture_smoke(
        ticker="NVDA",
        as_of=datetime(2026, 6, 15, 15, 0, tzinfo=timezone.utc),
    )

    assert result["status"] == "passed"
    assert result["mode"] == "fixture"
    assert "insider" in result["snapshot_families"]
    assert "social_macro" in result["snapshot_families"]
    assert result["source_records_by_family"]["insider"] == 2
    assert result["top_candidate"]["strategy_id"] == "insider_accumulation_momentum_v1"
    assert result["top_candidate"]["candidate_score"] > 0.55
    assert "insider.insider_cluster_buy_count_90d" in result["top_candidate"]["core_signal_evidence"]


def test_run_live_social_macro_smoke_persists_rows_without_orders():
    result = run_trading_signal_family_smoke.run_live_social_macro_smoke(
        ticker="NVDA",
        as_of=datetime(2026, 6, 15, 15, 0, tzinfo=timezone.utc),
        global_context_fetcher=_fake_global_context,
    )

    assert result["status"] == "passed"
    assert result["mode"] == "live_social_macro"
    assert result["source_records_by_family"] == {"social_macro": 1}
    assert result["social_macro_items_persisted"] == 1
    assert result["orders_created"] == 0
    assert result["provider_request_statuses"] == ["succeeded"]


def test_main_prints_json_fixture_report(capsys):
    exit_code = run_trading_signal_family_smoke.main(["--ticker", "NVDA", "--fixture", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "passed"
    assert payload["mode"] == "fixture"
