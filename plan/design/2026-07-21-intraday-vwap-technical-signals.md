# Intraday VWAP Technical Signals

## Goal

Add regular-session VWAP into the canonical technical signal surface used by live intraday refresh and rebalance decisions.

## Approved Scope

- Prioritize intraday trading and rebalance decisions.
- Compute VWAP from regular-session 1-minute bars from 09:30 ET through the intraday refresh `as_of`.
- Do not include premarket bars in the default VWAP calculation.
- Keep preopen behavior quiet: VWAP fields may be absent before regular-session bars exist and must not create preopen missing-signal noise.

## Signal Semantics

The technical signal payload should expose these fields when intraday bars are available:

- `vwap_now`: cumulative session VWAP, computed as `sum(typical_price * volume) / sum(volume)` over regular-session 1-minute bars, where `typical_price = (high + low + close) / 3`.
- `price_vs_vwap_now`: `(last_price - vwap_now) / vwap_now`.
- `vwap_return_since_open`: `(vwap_now - session_open_price) / session_open_price`, using the first regular-session intraday bar open.
- `vwap_return_since_last_close`: `(vwap_now - prior_close) / prior_close`, using the most recent completed daily close already available in the technical daily bars.
- `vwap_ma_20`: simple average of the most recent 20 per-bar cumulative VWAP values.

All return-like values are fractional returns, matching the existing technical signal convention.

## Architecture

The provider layer supplies raw intraday 1-minute OHLCV bars. `SourceIngestionService` attaches those bars to the existing `technical` source record payload during live refresh. `build_technical_signals()` remains the single owner for derived technical values, so preopen snapshots, intraday snapshots, strategy evidence, dashboard loaders, and LLM inputs all consume one canonical schema.

Intraday refresh should copy all computed VWAP fields from the latest technical source row into `refreshed_signals_json["technical"]`. The rebalance request already passes this refreshed technical block into `input_payload_json`, so the intraday rebalance prompt can use VWAP without a prompt schema migration.

## Data Flow

1. `AlpacaMarketDataProvider.fetch_intraday_bars(ticker, as_of)` fetches 1-minute bars from 09:30 ET to `as_of`, sorted ascending.
2. `SourceIngestionService._refresh_technical()` calls the optional provider method and stores `payload["intraday_bars"]`.
3. `build_technical_signals()` derives VWAP fields from `intraday_bars` and existing daily bars.
4. `_build_intraday_refresh_payload()` uses `build_technical_signals()` for the latest technical source row and carries the VWAP fields into the intraday snapshot.
5. `_build_rebalance_request()` passes the refreshed technical values to `IntradayRebalancePipeline` through the existing request payload.

## Error Handling

- If the provider has no `fetch_intraday_bars` method, skip intraday bars and leave VWAP fields `None`.
- If Alpaca returns no regular-session bars, leave VWAP fields `None`.
- If volume is missing or zero across all intraday bars, leave VWAP fields `None`.
- Provider failures should continue to flow through the existing `ProviderResiliencePolicy`; one ticker's failed intraday-bar request must not abort the whole refresh.

## Testing

- Unit-test VWAP calculations in `tests/trading/test_technical_signals.py`.
- Unit-test `SourceIngestionService` with a fake provider that exposes `fetch_intraday_bars`.
- Unit-test intraday refresh payload assembly so VWAP fields are present in `refreshed_signals_json["technical"]`.
- Unit-test Alpaca request parameters for regular-session 1-minute bars.
- Run focused trading tests and compile checks after implementation.

## Out Of Scope

- Premarket VWAP and extended-hours VWAP.
- New database columns or migrations; technical source payload and signal JSON already support these fields.
- Strategy catalog scoring changes that make VWAP fields required.
- Dashboard redesign. Existing generic signal surfaces can display the fields later if needed.
