"""
OPTIONAL: replace the synthetic sample with real CMS Medicare Part D data.

Pulls from the data.cms.gov API for the "Medicare Part D Prescribers -
by Provider and Drug" dataset, filtered to the states in STATES, and
rewrites the CSVs in data/raw/ in the same star-schema layout the app
expects. Territories remain synthetic (real alignments aren't public).

Run:  python etl/download_real_data.py
Then: python etl/load_data.py
"""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd
import requests

# UUID of "Medicare Part D Prescribers - by Provider and Drug" (latest year).
# Find current UUIDs at https://data.cms.gov/search?keywords=part%20d%20prescribers
DATASET_UUID = "9552739e-3d05-4c1b-8eff-ecabf391e2e5"
API = f"https://data.cms.gov/data-api/v1/dataset/{DATASET_UUID}/data"

STATES = ["IN", "CO"]
PAGE = 5000
MAX_ROWS_PER_STATE = 200_000  # safety cap for a demo build

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


def fetch_state(state: str) -> pd.DataFrame:
    frames, offset = [], 0
    while offset < MAX_ROWS_PER_STATE:
        r = requests.get(API, params={
            "filter[Prscrbr_State_Abrvtn]": state,
            "size": PAGE, "offset": offset,
        }, timeout=120)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        frames.append(pd.DataFrame(batch))
        offset += PAGE
        print(f"  {state}: {offset:,} rows...")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw = pd.concat([fetch_state(s) for s in STATES], ignore_index=True)
    if raw.empty:
        raise SystemExit("No rows returned - check DATASET_UUID on data.cms.gov")

    cols = {
        "Prscrbr_NPI": "npi", "Prscrbr_Last_Org_Name": "last",
        "Prscrbr_First_Name": "first", "Prscrbr_City": "city",
        "Prscrbr_State_Abrvtn": "state", "Prscrbr_Type": "specialty",
        "Brnd_Name": "brand_name", "Gnrc_Name": "generic_name",
        "Tot_Clms": "total_claims", "Tot_30day_Fills": "total_30day_fills",
        "Tot_Drug_Cst": "total_drug_cost", "Tot_Benes": "total_beneficiaries",
    }
    raw = raw[[c for c in cols if c in raw.columns]].rename(columns=cols)
    raw["npi"] = raw["npi"].astype("int64")
    for c in ["total_claims", "total_30day_fills", "total_beneficiaries"]:
        raw[c] = pd.to_numeric(raw[c], errors="coerce").fillna(0).astype(int)
    raw["total_drug_cost"] = pd.to_numeric(raw["total_drug_cost"], errors="coerce").fillna(0.0)
    raw["year"] = 2023  # single-vintage file; adjust if pulling multiple years

    dim_prescriber = (raw.groupby("npi").first().reset_index()
                      [["npi", "first", "last", "specialty", "city", "state"]])
    dim_prescriber["prescriber_name"] = dim_prescriber["first"].str.title() + " " + \
        dim_prescriber["last"].str.title()
    dim_prescriber = dim_prescriber.drop(columns=["first", "last"])

    # synthetic territories: bundle cities per state into ~8 groups
    rng = random.Random(7)
    terr_rows, t_id = [], 0
    for state in STATES:
        cities = dim_prescriber.loc[dim_prescriber.state == state, "city"].value_counts()
        groups: list[list[str]] = [[] for _ in range(8)]
        sizes = [0] * 8
        for city, n in cities.items():
            k = sizes.index(min(sizes))
            groups[k].append(city)
            sizes[k] += n
        for g in groups:
            if not g:
                continue
            t_id += 1
            terr_rows.append({"territory_id": t_id,
                              "territory_name": f"{g[0].title()} Region",
                              "state": state,
                              "region": "Midwest" if state == "IN" else "West",
                              "rep_name": f"Rep {t_id:02d}", "cities": set(g)})
    city_to_t = {(t["state"], c): t["territory_id"] for t in terr_rows for c in t["cities"]}
    dim_prescriber["territory_id"] = dim_prescriber.apply(
        lambda r: city_to_t.get((r.state, r.city)), axis=1)
    dim_territory = pd.DataFrame(terr_rows).drop(columns=["cities"])

    drugs = (raw[["brand_name", "generic_name"]].drop_duplicates()
             .reset_index(drop=True))
    drugs["drug_id"] = drugs.index + 1
    drugs["drug_class"] = "Unclassified"  # optionally map via a class lookup
    fact = raw.merge(drugs, on=["brand_name", "generic_name"])[
        ["npi", "drug_id", "year", "total_claims", "total_30day_fills",
         "total_drug_cost", "total_beneficiaries"]]

    dim_prescriber.to_csv(DATA_DIR / "dim_prescriber.csv", index=False)
    dim_territory.to_csv(DATA_DIR / "dim_territory.csv", index=False)
    drugs[["drug_id", "brand_name", "generic_name", "drug_class"]].to_csv(
        DATA_DIR / "dim_drug.csv", index=False)
    fact.to_csv(DATA_DIR / "fact_prescriptions.csv", index=False)
    print(f"Done: {len(dim_prescriber):,} prescribers, {len(fact):,} fact rows")


if __name__ == "__main__":
    main()
