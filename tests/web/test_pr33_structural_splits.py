from __future__ import annotations

from pathlib import Path


def test_today_loaders_hub_reexports_section_modules():
    from src.web.routers import today_loaders
    from src.web.routers.today import _build_header as router_build_header, _load_trade_detail as router_load_trade_detail
    from src.web.routers.loaders import (
        _format,
        candidates,
        header_system,
        portfolio,
        risk_macro,
        ticker_detail,
        trades,
        universe_learning,
    )

    assert today_loaders._TAB_LABELS is header_system._TAB_LABELS
    assert callable(header_system._build_header)
    assert callable(portfolio._build_portfolio_view)
    assert callable(trades._load_trade_detail)
    assert callable(candidates._load_candidate_rows)
    assert callable(risk_macro._load_today_risk_macro)
    assert callable(universe_learning._load_learning_factors)
    assert callable(ticker_detail._load_signal_history_by_ticker)
    assert callable(_format._format_pct)
    assert callable(today_loaders._build_header)
    assert callable(today_loaders._load_trade_detail)
    assert callable(router_build_header)
    assert callable(router_load_trade_detail)


def test_today_template_uses_tab_partials():
    template_path = Path("src/templates/today.html")
    template_text = template_path.read_text()

    expected_partials = (
        "today/_tab_trades.html",
        "today/_tab_overview.html",
        "today/_tab_portfolio.html",
        "today/_tab_risk_macro.html",
        "today/_tab_candidates.html",
        "today/_tab_system.html",
    )

    for partial in expected_partials:
        assert f'include "{partial}"' in template_text
        assert Path("src/templates", partial).exists()
