from fastapi import APIRouter, Depends, HTTPException

from app import queries
from app.database import get_db, rows_to_dicts

router = APIRouter(prefix="/api/drugs", tags=["drugs"])


@router.get("")
def list_drugs(db=Depends(get_db)):
    """Portfolio view: latest-year claims and cost per drug."""
    return {"drugs": rows_to_dicts(db.execute(queries.DRUG_LIST))}


@router.get("/{drug_id}/market")
def drug_market(drug_id: int, db=Depends(get_db)):
    """Territory-level volume and in-class share for one drug."""
    exists = db.execute("SELECT brand_name FROM dim_drug WHERE drug_id = ?",
                        (drug_id,)).fetchone()
    if exists is None:
        raise HTTPException(404, f"drug {drug_id} not found")
    return {
        "drug": exists["brand_name"],
        "trend": rows_to_dicts(db.execute(queries.DRUG_TREND, (drug_id,))),
        "by_territory": rows_to_dicts(
            db.execute(queries.DRUG_MARKET, (drug_id, drug_id))),
    }
