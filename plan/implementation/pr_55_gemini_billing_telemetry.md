# PR 55 Gemini Billing Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:test-driven-development` and `superpowers:systematic-debugging`; use `ui-development` before touching the System tab template.

**Goal:** Make future Gemini API spend telemetry comparable to Google Console by recording Gemini SDK token usage, while keeping the System tab explicit that local totals are estimates and not settled billing.

**Architecture:** Keep the existing `llm_usage_events` schema. Route Gemini trading/intraday calls through a direct Google SDK runner that reads `usage_metadata`, while preserving direct OpenRouter and fallback Phi behavior for other model names. Add derived Gemini-only summary fields in the System view so all-provider telemetry is not confused with Gemini billing.

**Tech Stack:** Python 3.13, `google-generativeai`, SQLAlchemy telemetry models, FastAPI/Jinja, pytest.

---

### Task 1: Capture Gemini SDK Usage

**Files:**
- Modify: `tests/agents/test_llm_models.py`
- Modify: `tests/agents/test_trading_agent.py`
- Modify: `src/agents/llm_models.py`
- Modify: `src/agents/trading.py`

- [x] Write RED tests for Gemini `usage_metadata` normalization and default trading-runner Gemini dispatch.
- [x] Implement direct Gemini runner with local cost estimation from prompt/completion tokens.
- [x] Route Gemini model names through the direct runner before Phi fallback.

### Task 2: Clarify System Cost Scope

**Files:**
- Modify: `tests/web/test_today.py`
- Modify: `src/web/routers/loaders/header_system.py`
- Modify: `src/templates/today/_tab_system.html`

- [x] Write RED tests for all-provider and Gemini-only estimate separation.
- [x] Add summary metadata and Gemini-only totals to `_build_system_view`.
- [x] Render the scope and billing-source copy in the Cost & Usage section.

### Task 3: Verification And Tracker

**Files:**
- Modify: `plan/progress_tracker.md`

- [x] Run focused RED/GREEN tests.
- [x] Run affected agent/web test suites, compile, and `git diff --check`.
- [x] Render `/today?tab=system` and inspect the changed Cost & Usage section.
- [x] Update `plan/progress_tracker.md`.
