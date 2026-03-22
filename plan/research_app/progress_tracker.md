# Research App Progress Tracker

## 2026-03-22

- Added `plan/research_app/architecture_recommendation.md` to make the MVP agent boundary explicit: custom orchestration owns batch lifecycle, data collection, persistence, and eval; `Phidata` is kept as a thin single-turn LLM adapter.
- Updated `plan/research_app/design_doc.md` to replace the ambiguous "Phidata tool-calling MVP" wording with the agreed hybrid architecture and to state that MVP data tools run in Python before the model call.
- Updated `plan/research_app/implementation_plan.md` to record the architecture decision and clarify the current `ResearchAgent` behavior before the later Gemini default switch.
- Switched the actual code default in `src/agents/research.py` to `gemini-2.5-flash-lite`, made the Phidata runner select a Gemini-backed model for `gemini*` IDs, added the required `openai` and `google-generativeai` dependencies, added provider-selection coverage in tests, and aligned the implementation/design docs plus `documents/repo_overview.md` with the Gemini default.
