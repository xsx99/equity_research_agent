# Handoff — Add yfinance fundamentals backfill (fix "missing signals" for fundamental family)

**Investigation done → implementation handoff.** Root cause confirmed in code (file:line below).
Nothing applied. Line numbers are approximate — reconfirm before editing.

> **SUPERSEDED — earnings piece:** this doc originally proposed pulling earnings dates from
> `yfinance.Ticker.calendar`. Earnings is now owned by `pr_47_earnings_calendar_wiring_and_nasdaq_source.md`
> (Nasdaq source + the events_news wiring fix). **Do NOT implement the earnings/`calendar` parts
> below** (the `_load_earnings`/`calendar_fetcher` code, `earnings_in_days`/`earnings_date` backfill).
> yfinance here owns only the fundamental *ratios*: EV/Sales, FCF margin, short interest, P/E, P/S,
> and the growth/margin/quality scores. Drop `earnings_in_days`/`earnings_date`/`known_event_date`
> from the yfinance provider's return and from `_backfill_from_yfinance`.

## Context / problem

The Today dashboard shows long "Missing signal:" lists on nearly every ticker (MRVL, AMAT, CRDO
screenshots). A chunk of those are the **fundamental family**:

- `fundamental.ev_sales_percentile`
- `fundamental.fcf_margin_score`
- `fundamental.short_interest_bucket`
- `fundamental.valuation_percentile`

and the two earnings-calendar event fields `events_news.earnings_in_days` /
`events_news.known_event_date`.

**Confirmed root cause (NOT a missing API key):** the screenshots show `quality_score`,
`revenue_growth_score`, `margin_trend_score` with real values, so Finnhub *is* configured and its
`/stock/metric` call works. The missing fields simply are not returned by the free Finnhub tier.
In `src/providers/market_data/alpaca_provider.py:244-301`, `fetch_context` requests these Finnhub
metric keys that the free tier omits:

| Signal | Finnhub key requested (free tier returns null) | alpaca_provider.py |
|---|---|---|
| `valuation_percentile` | `peTTM`/`psTTM` → `_valuation_percentile` | :244-245, :291 |
| `ev_sales_percentile` | `evSalesTTM`/`evSalesAnnual` | :292-296 |
| `fcf_margin_score` | `freeCashFlowMarginTTM`/`fcfMarginTTM` | :297-301 |
| `short_interest_bucket` | `shortPercentOfFloat`/`shortInterestPercent`/`shortRatio` | :246-251 |
| `earnings_in_days` / `known_event_date` | earnings calendar | :243, :417-454 |

Builder that turns these into missing flags: `src/trading/signals/fundamental.py:29-50` (null →
listed in `REQUIRED_FUNDAMENTAL_FIELDS` missing). Payload is consumed via `payload.get(...)`.

## Solution (decided)

Add a **yfinance-backed fundamentals provider** that backfills only the fields Finnhub left null.
Yahoo Finance needs no API key, its `Ticker.info` returns every missing field in one call, and it's
a Python lib that fits the stack. Keep Finnhub for what it already provides; yfinance fills the gaps
(and also serves as a full fallback when `FINNHUB_API_KEY` is unset, since then every field is null).

Backfill is **default-on** and injected at construction, so the wiring site
(`src/trading/runtime/preopen_dependencies.py:140`, `AlpacaMarketDataProvider()` with no args)
needs **no change**.

### yfinance → our fields mapping (mind the units)

Yahoo reports ratios as **fractions**; our normalizers (tuned for Finnhub) expect **percentages**.

| yfinance `Ticker.info` key | Yahoo unit | Convert | Feeds |
|---|---|---|---|
| `trailingPE` | multiple | pass-through | `pe_ratio` → `_valuation_percentile` |
| `priceToSalesTrailing12Months` | multiple | pass-through | `ps_ratio` → `_valuation_percentile` |
| `enterpriseToRevenue` | multiple | pass-through | `_normalize_ratio_score(floor=0, ceiling=15)` → `ev_sales_percentile` |
| `freeCashflow` ÷ `totalRevenue` | dollars | `× 100` (margin %) | `_normalize_ratio_score(floor=0, ceiling=25)` → `fcf_margin_score` |
| `shortPercentOfFloat` | fraction (0.035 = 3.5%) | `× 100` | `short_interest_pct_float` → `_short_interest_bucket` (thresholds 5/10/20 are percent) |
| `revenueGrowth` | fraction | `× 100` | `_normalize_ratio_score(floor=-10, ceiling=25)` → `revenue_growth_score` |
| `operatingMargins` | fraction | `× 100` | `_normalize_ratio_score(floor=0, ceiling=35)` → `margin_trend_score` + quality |
| `returnOnEquity` | fraction | `× 100` | quality (`floor=0, ceiling=30`) |
| `returnOnAssets` | fraction | `× 100` | quality (`floor=0, ceiling=12`) |
| `marketCap` | dollars | pass-through | `market_cap` → `_market_cap_bucket` |
| `sector` / `shortName`\|`longName` | str | trim | `sector` / `company_name` |
| `Ticker.calendar` → `Earnings Date` | date/list | nearest future | `earnings_in_days` / `earnings_date` / `known_event_date` |

Reuse the existing module-level helpers `_normalize_ratio_score`, `_average_scores`,
`_valuation_percentile` (alpaca_provider.py:461-482) so yfinance-derived scores use identical
scaling to the Finnhub path.

## Implementation steps

### 1. Dependency — `requirements.txt`

Add (floor pin; yfinance ships breaking changes often, so avoid an exact pin but keep a floor):

```
yfinance>=0.2.50
```

Place it near the other data-provider deps (`alpaca-py`, `finnhub-python`).

### 2. New module — `src/providers/market_data/yfinance_fundamentals.py`

Reference implementation (adjust to house style; `_to_float_or_none` already lives in
`src/providers/market_data/helpers.py`):

```python
"""yfinance-backed fundamentals provider.

Backfills fundamental metrics Finnhub's free tier does not return
(EV/Sales, FCF margin, short interest % of float, P/E, P/S, earnings
calendar). Yahoo Finance requires no API key.

Units: Yahoo reports ratios as fractions (0.035 == 3.5%); we multiply the
ratio fields by 100 so they match the units the Finnhub-based normalizers
expect. enterpriseToRevenue is already a multiple and passes through.
FCF margin is derived from freeCashflow / totalRevenue.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Callable, Optional

from src.providers.market_data.helpers import _to_float_or_none


class YFinanceFundamentalsProvider:
    """Fetch a normalized fundamentals payload for one ticker from Yahoo.

    info_fetcher / calendar_fetcher let tests inject fakes without importing
    yfinance or hitting the network. When omitted the provider lazily imports
    yfinance and degrades to an empty payload on ImportError or request error.
    """

    def __init__(
        self,
        *,
        info_fetcher: Optional[Callable[[str], dict[str, Any]]] = None,
        calendar_fetcher: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self._info_fetcher = info_fetcher
        self._calendar_fetcher = calendar_fetcher

    def fetch(self, ticker: str) -> dict[str, Any]:
        symbol = ticker.upper()
        info = self._load_info(symbol)
        if not isinstance(info, dict):
            info = {}

        short_float = _to_float_or_none(info.get("shortPercentOfFloat"))
        short_interest_pct = short_float * 100.0 if short_float is not None else None

        fcf = _to_float_or_none(info.get("freeCashflow"))
        revenue = _to_float_or_none(info.get("totalRevenue"))
        fcf_margin_pct = (
            fcf / revenue * 100.0
            if fcf is not None and revenue not in (None, 0)
            else None
        )

        earnings_in_days, earnings_date = self._load_earnings(symbol)

        return {
            "sector": self._clean_str(info.get("sector")),
            "company_name": self._clean_str(info.get("shortName") or info.get("longName")),
            "market_cap": _to_float_or_none(info.get("marketCap")),
            "pe_ratio": _to_float_or_none(info.get("trailingPE")),
            "ps_ratio": _to_float_or_none(info.get("priceToSalesTrailing12Months")),
            "ev_sales_multiple": _to_float_or_none(info.get("enterpriseToRevenue")),
            "fcf_margin_pct": fcf_margin_pct,
            "short_interest_pct_float": short_interest_pct,
            "revenue_growth_pct": self._as_pct(info.get("revenueGrowth")),
            "operating_margin_pct": self._as_pct(info.get("operatingMargins")),
            "roe_pct": self._as_pct(info.get("returnOnEquity")),
            "roa_pct": self._as_pct(info.get("returnOnAssets")),
            "earnings_in_days": earnings_in_days,
            "earnings_date": earnings_date,
        }

    def _load_info(self, symbol: str) -> dict[str, Any]:
        if self._info_fetcher is not None:
            try:
                return self._info_fetcher(symbol)
            except Exception:
                return {}
        try:
            import yfinance as yf
        except ImportError:
            return {}
        try:
            info = yf.Ticker(symbol).info
        except Exception:
            return {}
        return info if isinstance(info, dict) else {}

    def _load_earnings(self, symbol: str) -> tuple[Optional[int], Optional[date]]:
        raw: Any = None
        if self._calendar_fetcher is not None:
            try:
                raw = self._calendar_fetcher(symbol)
            except Exception:
                raw = None
        else:
            try:
                import yfinance as yf

                raw = yf.Ticker(symbol).calendar
            except Exception:
                raw = None

        next_date = self._extract_earnings_date(raw)
        if next_date is None:
            return None, None
        today = datetime.now(timezone.utc).date()
        delta = (next_date - today).days
        if delta < 0:
            return None, next_date
        return delta, next_date

    @staticmethod
    def _extract_earnings_date(raw: Any) -> Optional[date]:
        value: Any = None
        if isinstance(raw, dict):
            value = raw.get("Earnings Date") or raw.get("earningsDate")
        else:
            value = raw
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return datetime.fromisoformat(value.strip().split("T")[0]).date()
            except ValueError:
                return None
        return None

    @staticmethod
    def _as_pct(value: Any) -> Optional[float]:
        parsed = _to_float_or_none(value)
        return parsed * 100.0 if parsed is not None else None

    @staticmethod
    def _clean_str(value: Any) -> Optional[str]:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None
```

### 3. Wire backfill into `AlpacaMarketDataProvider` — `src/providers/market_data/alpaca_provider.py`

**3a. Import** (top of file, near other provider imports):

```python
from src.providers.market_data.yfinance_fundamentals import YFinanceFundamentalsProvider
```

**3b. Constructor** (`__init__`, around :29-49) — add a param + assignment. Default-on; pass
`fundamentals_provider=<fake>` in tests, or an instance with a no-op fetch to disable:

```python
        fundamentals_provider: Optional[YFinanceFundamentalsProvider] = None,
        ...
        self._fundamentals_provider = fundamentals_provider or YFinanceFundamentalsProvider()
```

Constructing the provider is cheap (yfinance import is lazy inside `fetch`), so this is safe even
if yfinance is not installed in some environment — `_load_info` returns `{}` and backfill is a no-op.

**3c. Call backfill in `fetch_context`** — right before the cache write at
`alpaca_provider.py:303` (`self._context_cache[symbol] = dict(context_payload)`):

```python
        context_payload = self._backfill_from_yfinance(symbol, context_payload)
        self._context_cache[symbol] = dict(context_payload)
```

**3d. New method** on the class (place near the other `_fetch_*` helpers). Only fills fields that
are currently `None`, so the Finnhub path always wins when it has data:

```python
    def _backfill_from_yfinance(self, symbol: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._fundamentals_provider is None:
            return payload
        gap_fields = (
            "sector", "company_name", "market_cap",
            "valuation_percentile", "ev_sales_percentile", "fcf_margin_score",
            "short_interest_pct_float", "revenue_growth_score", "margin_trend_score",
            "quality_score", "earnings_in_days", "earnings_date",
        )
        if all(payload.get(field) is not None for field in gap_fields):
            return payload
        try:
            yf_data = self._fundamentals_provider.fetch(symbol)
        except Exception:
            return payload
        if not isinstance(yf_data, dict):
            return payload

        for key in ("sector", "company_name", "market_cap", "short_interest_pct_float"):
            if payload.get(key) is None and yf_data.get(key) is not None:
                payload[key] = yf_data[key]

        pe = payload.get("pe_ratio")
        if pe is None:
            pe = yf_data.get("pe_ratio")
            payload["pe_ratio"] = pe
        ps = payload.get("ps_ratio")
        if ps is None:
            ps = yf_data.get("ps_ratio")
            payload["ps_ratio"] = ps
        if payload.get("valuation_percentile") is None:
            payload["valuation_percentile"] = _valuation_percentile(pe_ratio=pe, ps_ratio=ps)

        if payload.get("ev_sales_percentile") is None:
            payload["ev_sales_percentile"] = _normalize_ratio_score(
                yf_data.get("ev_sales_multiple"), floor=0.0, ceiling=15.0
            )
        if payload.get("fcf_margin_score") is None:
            payload["fcf_margin_score"] = _normalize_ratio_score(
                yf_data.get("fcf_margin_pct"), floor=0.0, ceiling=25.0
            )
        if payload.get("revenue_growth_score") is None:
            payload["revenue_growth_score"] = _normalize_ratio_score(
                yf_data.get("revenue_growth_pct"), floor=-10.0, ceiling=25.0
            )
        if payload.get("margin_trend_score") is None:
            payload["margin_trend_score"] = _normalize_ratio_score(
                yf_data.get("operating_margin_pct"), floor=0.0, ceiling=35.0
            )
        if payload.get("quality_score") is None:
            payload["quality_score"] = _average_scores(
                (
                    _normalize_ratio_score(yf_data.get("operating_margin_pct"), floor=0.0, ceiling=35.0),
                    _normalize_ratio_score(yf_data.get("roe_pct"), floor=0.0, ceiling=30.0),
                    _normalize_ratio_score(yf_data.get("roa_pct"), floor=0.0, ceiling=12.0),
                )
            )

        if payload.get("earnings_in_days") is None and yf_data.get("earnings_in_days") is not None:
            payload["earnings_in_days"] = yf_data["earnings_in_days"]
        if payload.get("earnings_date") is None and yf_data.get("earnings_date") is not None:
            payload["earnings_date"] = yf_data["earnings_date"]
            if payload.get("known_event_date") is None:
                payload["known_event_date"] = yf_data["earnings_date"]
        return payload
```

Note: `context_payload` already carries `pe_ratio`, `ps_ratio`, `short_interest_pct_float`
(alpaca_provider.py:259-261) and `earnings_date`/`known_event_date` (:257-258), so the keys exist.

## Gotchas / must-verify (I could NOT run this — no app env access; verify at implementation)

1. **Units are the #1 risk.** Confirm on 2-3 real tickers that yfinance `shortPercentOfFloat`,
   `revenueGrowth`, `operatingMargins`, `returnOnEquity`, `returnOnAssets` come back as **fractions**
   (e.g. `0.035`, not `3.5`). The `× 100` conversions assume fractions. If a future yfinance version
   changes this, `short_interest_bucket` and the scores will be off by 100×. Spot-check that a
   known high-short-interest name lands in the right bucket.
2. **`enterpriseToRevenue` is a multiple, NOT ×100.** Same for `trailingPE`/`priceToSalesTrailing12Months`.
3. **`Ticker.calendar` shape drifts across yfinance versions** — newer returns a `dict` with
   `"Earnings Date"` → list of `datetime.date`; older returned a DataFrame. `_extract_earnings_date`
   handles dict/list/str/date defensively; re-verify against the installed version. If it returns a
   DataFrame in your version, add a branch (or use `Ticker.get_earnings_dates()`).
4. **Latency:** `.info` + `.calendar` are 1-2 HTTP calls per ticker and yfinance can be slow/flaky.
   This runs inside the preopen batch, already wrapped by `ProviderResiliencePolicy` at
   `source_ingestion.py` (`policy.execute(ticker, lambda: self.market_provider.fetch_context(ticker))`),
   so retries/timeouts are handled there. Do **not** let a yfinance failure raise out of
   `fetch_context` — the try/except in the new code keeps it a no-op backfill.
5. **`fetch_context` is cached per-symbol** (`_context_cache`) — backfill runs before the cache write,
   so it happens once per symbol per provider instance. Good.

## Tests to add

- `tests/.../test_yfinance_fundamentals.py`: unit-test `YFinanceFundamentalsProvider.fetch` with an
  injected `info_fetcher`/`calendar_fetcher` returning a fixed dict — assert unit conversions
  (fraction→pct, fcf margin math, short-float ×100, earnings-days delta, negative delta → None days
  but date retained, missing keys → None). No network.
- Extend the alpaca provider tests: build `AlpacaMarketDataProvider(finnhub_api_key=None,
  fundamentals_provider=<fake>)` and assert `fetch_context` fills `ev_sales_percentile`,
  `fcf_margin_score`, `short_interest_bucket` (via builder), `valuation_percentile`. Then a case
  where Finnhub already supplied a value and assert yfinance does **not** overwrite it.
- Integration/manual (needs network, do at implement time): run `fetch_context` for MRVL/AMAT/CRDO
  and confirm the four fundamental fields + earnings are now non-null; then confirm the UI
  counterargument list drops those "Missing signal" entries.

## Explicitly OUT of scope (these missing signals are NOT data-source problems)

- `technical.premarket_gap_pct`, `technical.rs_vs_spy_1d`, `technical.rs_vs_qqq_1d` — never computed
  in the collector (`source_ingestion.py:300-311` only writes `{"bars": ...}`). Separate code task.
- `option_chain_availability`, `full_transcript_interpretation`, `macro_sector_readthrough` —
  intentional always-missing capability markers (`src/trading/signals/snapshots.py:72-74`). Will
  always appear; do not touch here.
- `insider.*` — separate SEC EDGAR pipeline (`src/collectors/sec_edgar/collector.py`); missing only
  when a ticker has no recent Form 4 rows. Different task.
- `events_news.direct_negative_catalyst_type` — null by design unless a matching negative catalyst
  exists (`src/trading/signals/event_news.py:107-120`). Expected.

## Definition of done

- `yfinance` in requirements; new provider module + tests; `AlpacaMarketDataProvider` backfills gaps.
- With `FINNHUB_API_KEY` set, the four fundamental fields + earnings are non-null for liquid tickers,
  and Finnhub-supplied values are never overwritten.
- With `FINNHUB_API_KEY` unset, yfinance alone populates the whole fundamental family.
- yfinance/network failure degrades gracefully (fields stay null, no exception escapes fetch_context).
```
