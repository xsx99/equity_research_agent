"""Admin routes."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.agents.research import ResearchAgent
from src.db.connection import get_session
from src.prompts.registry import PromptRegistry
from src.research.workflows.evaluation import EvalPipeline
from src.research.workflows.batch_research import ResearchPipeline
from src.tools import build_research_tool_registry
from src.web.flash import flash

router = APIRouter()
_templates: Jinja2Templates | None = None


def init(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


@router.post("/admin/run-now", response_class=HTMLResponse)
def admin_run_now(request: Request):
    try:
        with get_session() as session:
            agent = ResearchAgent(
                tool_registry=build_research_tool_registry(),
                prompt_registry=PromptRegistry.get_default(),
            )
            pipeline = ResearchPipeline(session=session, agent=agent)
            result = pipeline.run_all()
        msg = f"Research complete: {result.succeeded} succeeded, {result.failed} failed."
        level = "info" if result.failed == 0 else "warning"
    except Exception as exc:
        msg = f"Research pipeline error: {exc}"
        level = "error"
    flash(request, msg, level)
    return RedirectResponse("/research", status_code=303)


@router.post("/admin/eval-now", response_class=HTMLResponse)
def admin_eval_now(request: Request):
    try:
        with get_session() as session:
            pipeline = EvalPipeline(session=session)
            result = pipeline.run_all()
        msg = (
            f"Eval complete: {result.evaluated} evaluated, "
            f"{result.skipped} skipped, {result.failed} failed."
        )
        level = "info" if result.failed == 0 else "warning"
    except Exception as exc:
        msg = f"Eval pipeline error: {exc}"
        level = "error"
    flash(request, msg, level)
    return RedirectResponse("/research", status_code=303)
