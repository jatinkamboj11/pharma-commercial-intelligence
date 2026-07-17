from fastapi import APIRouter, Depends, HTTPException, Query

from app import queries
from app.database import get_db, rows_to_dicts

router = APIRouter(prefix="/api/prescribers", tags=["prescribers"])

SORTABLE = {"claims", "drug_cost", "decile", "prescriber_name"}


@router.get("")
def list_prescribers(
    territory_id: int | None = None,
    specialty: str | None = None,
    min_decile: int = Query(1, ge=1, le=10),
    sort: str = "claims",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
):
    """Ranked prescriber targeting list.

    Deciles are computed nationally (NTILE(10) over latest-year claims),
    then filtered - so 'decile 10' means top ~10% in the whole footprint,
    which is how call plans are actually prioritized.
    """
    if sort not in SORTABLE:
        raise HTTPException(400, f"sort must be one of {sorted(SORTABLE)}")

    rows = rows_to_dicts(db.execute(queries.PRESCRIBER_DECILES))
    if territory_id is not None:
        rows = [r for r in rows if r["territory_id"] == territory_id]
    if specialty:
        rows = [r for r in rows if r["specialty"].lower() == specialty.lower()]
    rows = [r for r in rows if r["decile"] >= min_decile]
    rows.sort(key=lambda r: r[sort], reverse=sort != "prescriber_name")

    return {"total": len(rows), "prescribers": rows[offset:offset + limit]}


@router.get("/{npi}")
def prescriber_profile(npi: int, db=Depends(get_db)):
    """Single prescriber: identity, territory, decile, drug mix by year."""
    head = db.execute(queries.PRESCRIBER_PROFILE, (npi,)).fetchone()
    if head is None:
        raise HTTPException(404, f"prescriber {npi} not found")
    decile = next((r["decile"] for r in db.execute(queries.PRESCRIBER_DECILES)
                   if r["npi"] == npi), None)
    return {
        "prescriber": dict(head),
        "decile": decile,
        "drug_mix": rows_to_dicts(db.execute(queries.PRESCRIBER_DRUG_MIX, (npi,))),
    }
