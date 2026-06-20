# Prompt 03 — Filter out general/non-ticker news before it reaches decisions and the UI

You are editing the equity_research_agent repo. This is a backend data-quality fix
(not a UI layout change). Make ONLY the changes described. Run the matching tests.

## Problem
The TRADES tab "EVENT / NEWS SUMMARY" for a ticker (e.g. AAPL) shows generic
clickbait that has nothing to do with the ticker (e.g. "Making $100K a Year? Here's
the One Fund That Compounds Without the Research..."), and trade evidence reads
"direct negative catalyst: **General News**". General market news must be filtered
out before it influences the decision or appears in the UI.

## Context (verified facts)
- A filter already exists but is too narrow:
  `src/providers/news_data/helpers.py:353-361` `_is_irrelevant_general_news(...)`.
  It only drops an item when ALL of: `signal_type == "general_news"` AND
  `event_type == "general_news"` AND no catalyst terms AND **summary is empty** AND
  the title matches a tiny pattern list. Clickbait that has a non-empty summary slips
  through.
- The filter runs only when the condenser is enabled
  (`TRADING_NEWS_CONDENSER_ENABLED`, default on):
  `src/trading/signals/source_ingestion.py:398-402`.
- `src/trading/signals/event_news.py` can set `direct_negative_catalyst_type` from a
  `general_news`-derived value → produces the "direct negative catalyst: General
  News" message. `_NEGATIVE_CATALYST_PRECEDENCE` (top of that file) lists the real
  catalyst types; `general_news` is not among them.
- The UI does no relevance filtering: `_load_news_by_ticker`
  (`src/web/routers/today.py:1679-1718`) loads all news, and
  `_build_event_news_summary` (`src/web/presenters/today_workspace.py:519-539`) shows
  the FIRST news item regardless of type.

## Changes — three layers (defense in depth)
1. **Ingestion** (`src/providers/news_data/helpers.py`, `_is_irrelevant_general_news`):
   - REMOVE the "summary must be empty" requirement (this is why clickbait-with-text
     leaks through).
   - ADD a relevance check: drop the item when `event_type == "general_news"` AND the
     title+summary do NOT mention the ticker symbol or the company name AND there is
     no catalyst term. (The ticker/company-name relevance check is the key part.)
   - Broaden the generic-title patterns. Add patterns like: `one fund`,
     `make .* a year`, `compounds`, `retire`, `these .* stocks`, `best stocks`,
     `motley`, `should you buy`, `stocks to buy`.
2. **Signal aggregation** (`src/trading/signals/event_news.py`): never populate
   `direct_negative_catalyst_type` from a `general_news` event. Only types present in
   `_NEGATIVE_CATALYST_PRECEDENCE` may set it.
3. **UI guard** (belt-and-suspenders): in `_build_event_news_summary`
   (`src/web/presenters/today_workspace.py:519-539`) and/or `_load_news_by_ticker`,
   skip items whose `event_type == "general_news"` (or `importance == "low"`) when
   choosing the summary item. If nothing ticker-relevant remains, return the string
   `"No material ticker-specific news."` instead of a generic article.

## Acceptance criteria
- The AAPL EVENT / NEWS SUMMARY never shows generic market/clickbait; it shows a
  ticker-relevant item or the explicit "No material ticker-specific news." fallback.
- No UI text ever reads "direct negative catalyst: General News".
- Add a test: a clickbait item with a non-empty summary and no ticker mention is
  filtered out. `pytest tests/providers/ tests/trading/ -q` passes.
