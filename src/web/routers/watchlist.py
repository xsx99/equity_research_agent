"""Watchlist routes."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.db.connection import get_session
from src.research import repository
from src.web.flash import flash, get_flash

router = APIRouter()
_templates: Jinja2Templates | None = None


def init(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


@router.get("/watchlist", response_class=HTMLResponse)
def watchlist_page(request: Request):
    with get_session() as session:
        items = repository.get_watchlist(session)
        rows = [
            {
                "id": str(w.id),
                "ticker": w.ticker,
                "is_active": w.is_active,
                "created_at": w.created_at,
            }
            for w in items
        ]
    return _templates.TemplateResponse(
        request, "watchlist.html", {"rows": rows, "flash": get_flash(request)}
    )


@router.post("/watchlist/add")
def watchlist_add(request: Request, ticker: str = Form(...)):
    ticker = ticker.strip().upper()
    if not ticker:
        return RedirectResponse("/watchlist", status_code=303)
    try:
        with get_session() as session:
            repository.add_ticker(session, ticker)
    except Exception as exc:
        flash(request, f"Error adding {ticker}: {exc}", "error")
    return RedirectResponse("/watchlist", status_code=303)


@router.post("/watchlist/{ticker}/delete")
def watchlist_delete(ticker: str, request: Request):
    try:
        with get_session() as session:
            found = repository.deactivate_ticker(session, ticker.upper())
        if not found:
            flash(request, f"{ticker} not found", "error")
    except Exception as exc:
        flash(request, f"Error removing {ticker}: {exc}", "error")
    return RedirectResponse("/watchlist", status_code=303)
