# SEC Collector Progress Tracker

## 2026-03-22

- Completed exact feed filtering in `src/collectors/sec_edgar/feed.py` so the collector only processes ownership filings with form types `4` and `4/A`.
- Added regression coverage in `tests/collectors/test_sec_feed.py` for exact matches, title fallback, and exclusion of broad `4*` matches such as `424B2` and `425`.
- Added manual SEC trigger instructions to `documents/raspberry_pi_service_checks.md` for production smoke tests on the Raspberry Pi.
