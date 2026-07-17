from fastapi import APIRouter, Depends, HTTPException

from app import queries
from app.database import get_db, rows_to_dicts

router = APIRouter(prefix="/api/territories", tags=["territories"])


@router.get("")
def list_territories(db=Depends(get_db)):
    """All territories with latest-year KPIs, YoY growth and rank."""
    rows = rows_to_dicts(db.execute(queries.TERRITORY_KPIS))
    for r in rows:
        prev = r.pop("claims_prev")
        r["claims_yoy_pct"] = round(100 * (r["claims"] - prev) / prev, 1) if prev else None
    return {"territories": rows}


@router.get("/{territory_id}/performance")
def territory_performance(territory_id: int, top_drugs: int = 8, db=Depends(get_db)):
    """Single-territory drilldown: header, yearly trend, top drugs."""
    head = db.execute(queries.TERRITORY_DETAIL, (territory_id,)).fetchone()
    if head is None:
        raise HTTPException(404, f"territory {territory_id} not found")
    return {
        "territory": dict(head),
        "trend": rows_to_dicts(db.execute(queries.TERRITORY_TREND, (territory_id,))),
        "top_drugs": rows_to_dicts(
            db.execute(queries.TERRITORY_TOP_DRUGS, (territory_id, top_drugs))),
    }
