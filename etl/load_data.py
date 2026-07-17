"""
Load the star-schema CSVs from data/raw/ into the SQLite warehouse
(data/warehouse.db), creating tables and indexes.

Run after generate_sample_data.py (or download_real_data.py):
    python etl/load_data.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "warehouse.db"

DDL = """
DROP TABLE IF EXISTS fact_prescriptions;
DROP TABLE IF EXISTS dim_prescriber;
DROP TABLE IF EXISTS dim_drug;
DROP TABLE IF EXISTS dim_territory;

CREATE TABLE dim_territory (
    territory_id   INTEGER PRIMARY KEY,
    territory_name TEXT NOT NULL,
    state          TEXT NOT NULL,
    region         TEXT NOT NULL,
    rep_name       TEXT NOT NULL
);

CREATE TABLE dim_prescriber (
    npi             INTEGER PRIMARY KEY,
    prescriber_name TEXT NOT NULL,
    specialty       TEXT NOT NULL,
    city            TEXT NOT NULL,
    state           TEXT NOT NULL,
    territory_id    INTEGER NOT NULL REFERENCES dim_territory(territory_id)
);

CREATE TABLE dim_drug (
    drug_id      INTEGER PRIMARY KEY,
    brand_name   TEXT NOT NULL,
    generic_name TEXT NOT NULL,
    drug_class   TEXT NOT NULL
);

CREATE TABLE fact_prescriptions (
    npi                 INTEGER NOT NULL REFERENCES dim_prescriber(npi),
    drug_id             INTEGER NOT NULL REFERENCES dim_drug(drug_id),
    year                INTEGER NOT NULL,
    total_claims        INTEGER NOT NULL,
    total_30day_fills   INTEGER NOT NULL,
    total_drug_cost     REAL    NOT NULL,
    total_beneficiaries INTEGER NOT NULL,
    PRIMARY KEY (npi, drug_id, year)
);

CREATE INDEX idx_fact_drug ON fact_prescriptions(drug_id, year);
CREATE INDEX idx_fact_year ON fact_prescriptions(year);
CREATE INDEX idx_prescriber_territory ON dim_prescriber(territory_id);
"""


def main() -> None:
    if not (RAW / "dim_prescriber.csv").exists():
        raise SystemExit("data/raw is empty - run etl/generate_sample_data.py first")

    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.executescript(DDL)

    order = ["dim_territory", "dim_prescriber", "dim_drug", "fact_prescriptions"]
    cols = {
        "dim_territory": ["territory_id", "territory_name", "state", "region", "rep_name"],
        "dim_prescriber": ["npi", "prescriber_name", "specialty", "city", "state", "territory_id"],
        "dim_drug": ["drug_id", "brand_name", "generic_name", "drug_class"],
        "fact_prescriptions": ["npi", "drug_id", "year", "total_claims",
                               "total_30day_fills", "total_drug_cost", "total_beneficiaries"],
    }
    for table in order:
        df = pd.read_csv(RAW / f"{table}.csv")[cols[table]]
        # guard: facts referencing unknown prescribers (possible with real data caps)
        if table == "fact_prescriptions":
            known = pd.read_sql("SELECT npi FROM dim_prescriber", con)["npi"]
            df = df[df.npi.isin(set(known))]
        df.to_sql(table, con, if_exists="append", index=False)
        print(f"{table:<20} {len(df):>8,} rows")

    con.execute("ANALYZE")
    con.commit()
    con.close()
    print(f"warehouse ready: {DB}")


if __name__ == "__main__":
    main()
