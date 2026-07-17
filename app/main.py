"""Pharma Commercial Intelligence Platform - FastAPI entrypoint.

API docs:   /docs
Dashboard:  /
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.routers import drugs, insights, prescribers, territories

BASE = Path(__file__).resolve().parent

app = FastAPI(
    title="Pharma Commercial Intelligence Platform",
    description=(
        "Territory performance, prescriber deciling and call-plan simulation "
        "on Medicare Part D-style prescription data. Built as a portfolio "
        "project for business-technology consulting roles."
    ),
    version="1.0.0",
)

app.include_router(territories.router)
app.include_router(prescribers.router)
app.include_router(drugs.router)
app.include_router(insights.router)

app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def page_overview(request: Request):
    return templates.TemplateResponse(request, "index.html", {"active": "overview"})


@app.get("/territory/{territory_id}", response_class=HTMLResponse)
def page_territory(request: Request, territory_id: int):
    return templates.TemplateResponse(
        request, "territory.html",
        {"active": "overview", "territory_id": territory_id})


@app.get("/targeting", response_class=HTMLResponse)
def page_targeting(request: Request):
    return templates.TemplateResponse(request, "targeting.html", {"active": "targeting"})
