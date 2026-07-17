from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app import queries
from app.database import get_db, rows_to_dicts

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("/deciles")
def decile_summary(territory_id: int | None = None, db=Depends(get_db)):
    """Decile distribution: prescriber counts and claim volume per decile.

    The classic pharma insight this surfaces: the top 2-3 deciles usually
    drive well over half of all volume - which is why reps target them.
    """
    rows = rows_to_dicts(db.execute(queries.PRESCRIBER_DECILES))
    if territory_id is not None:
        rows = [r for r in rows if r["territory_id"] == territory_id]
        if not rows:
            raise HTTPException(404, f"no prescribers for territory {territory_id}")

    total_claims = sum(r["claims"] for r in rows) or 1
    buckets = []
    for d in range(10, 0, -1):
        sub = [r for r in rows if r["decile"] == d]
        claims = sum(r["claims"] for r in sub)
        buckets.append({
            "decile": d,
            "prescribers": len(sub),
            "claims": claims,
            "claims_share_pct": round(100 * claims / total_claims, 1),
        })
    top3 = sum(b["claims_share_pct"] for b in buckets[:3])
    return {"scope": territory_id or "national",
            "top3_decile_claims_share_pct": round(top3, 1),
            "deciles": buckets}


class CallPlanRequest(BaseModel):
    territory_id: int
    calls_available: int = Field(gt=0, le=10_000,
                                 description="Rep calls available per cycle")
    calls_per_prescriber: int = Field(2, gt=0, le=20)


@router.post("/call-plan")
def simulate_call_plan(req: CallPlanRequest, db=Depends(get_db)):
    """Greedy call-plan simulator.

    Allocates the available calls to prescribers from decile 10 downward
    and reports what share of territory claim volume the plan reaches -
    a simplified version of real sales-force sizing logic.
    """
    buckets = rows_to_dicts(db.execute(queries.CALL_PLAN_BASE, (req.territory_id,)))
    if not buckets:
        raise HTTPException(404, f"no data for territory {req.territory_id}")

    total_claims = sum(b["claims"] for b in buckets) or 1
    remaining = req.calls_available
    plan, covered = [], 0
    for b in buckets:  # already sorted decile DESC
        if remaining <= 0:
            reach = 0
        else:
            can_cover = remaining // req.calls_per_prescriber
            reach = min(b["prescribers"], can_cover)
            remaining -= reach * req.calls_per_prescriber
        covered_claims = b["claims"] * (reach / b["prescribers"]) if b["prescribers"] else 0
        covered += covered_claims
        plan.append({
            "decile": b["decile"],
            "prescribers": b["prescribers"],
            "prescribers_reached": reach,
            "decile_claims": b["claims"],
        })
    return {
        "territory_id": req.territory_id,
        "calls_available": req.calls_available,
        "calls_per_prescriber": req.calls_per_prescriber,
        "claims_coverage_pct": round(100 * covered / total_claims, 1),
        "allocation": plan,
        "note": "Greedy top-decile-first allocation; assumes uniform volume within a decile.",
    }
