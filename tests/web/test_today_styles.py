"""CSS contract checks for the server-rendered Today dashboard."""

from __future__ import annotations

import re
from pathlib import Path


_CSS_PATH = Path(__file__).resolve().parents[2] / "src" / "static" / "style.css"


def _rules_for_selector(css: str, selector: str) -> dict[str, str]:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    declarations: dict[str, str] = {}
    for selector_group, body in re.findall(r"([^{}]+)\{([^{}]+)\}", css):
        selectors = {part.strip() for part in selector_group.split(",")}
        if selector not in selectors:
            continue
        for declaration in body.split(";"):
            if ":" not in declaration:
                continue
            name, value = declaration.split(":", 1)
            declarations[name.strip()] = value.strip()
    return declarations


def test_trades_detail_layout_shrinks_wide_tables_inside_canvas() -> None:
    css = _CSS_PATH.read_text()

    for selector in (
        ".trades-canvas",
        ".ticker-workspace",
        ".ticker-detail-panel",
        ".ticker-detail-panel .subcard",
        ".tab-panel",
        ".table-scroll",
    ):
        assert _rules_for_selector(css, selector).get("min-width") == "0"

    table_scroll = _rules_for_selector(css, ".table-scroll")
    assert table_scroll.get("overflow-x") == "auto"
    assert table_scroll.get("max-width") == "100%"

    assert _rules_for_selector(css, ".trade-plan-table td").get("white-space") == "normal"
    assert _rules_for_selector(css, ".trade-plan-table td.num").get("white-space") == "nowrap"
