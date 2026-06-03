"""FastAPI application factory.

Routes:
  GET  /watchlist               — list all watchlist tickers; form to add
  POST /watchlist/add           — add/reactivate a ticker
  POST /watchlist/{ticker}/delete — deactivate a ticker
  GET  /research                — list research runs with aggregated eval stats
  GET  /research/{run_id}       — run detail (input, output, eval)
  POST /admin/run-now           — trigger research pipeline
  POST /admin/eval-now          — trigger eval pipeline
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.db.connection import init_db
from src.web import filters
from src.web.routers import admin, research, today, watchlist

_DIR = os.path.dirname(__file__)
_STATIC_DIR = os.path.join(os.path.dirname(_DIR), "static")
_TEMPLATES_DIR = os.path.join(os.path.dirname(_DIR), "templates")


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        yield

    app = FastAPI(title="Insider Research App", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    templates = Jinja2Templates(directory=_TEMPLATES_DIR)
    filters.register(templates)

    watchlist.init(templates)
    research.init(templates)
    admin.init(templates)
    today.init(templates)

    app.include_router(watchlist.router)
    app.include_router(research.router)
    app.include_router(admin.router)
    app.include_router(today.router)

    @app.get("/", response_class=HTMLResponse)
    def root():
        return RedirectResponse("/today", status_code=303)

    return app
