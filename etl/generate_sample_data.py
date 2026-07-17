"""
Generate realistic synthetic data modeled on the CMS Medicare Part D
"Prescribers - by Provider and Drug" public dataset.

Why synthetic? So the repo runs out of the box with zero downloads.
The schema and value distributions mirror the real CMS file, and
etl/download_real_data.py can swap in the real data at any time.

Territory structure is ALWAYS synthetic (real rep territories are not
public data) - prescribers are grouped by city into ~16 territories,
which mirrors standard pharma alignment practice.

Usage:
    python etl/generate_sample_data.py
Outputs CSVs into data/raw/.
"""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pandas as pd

RNG_SEED = 42
N_PRESCRIBERS = 1200
YEARS = [2022, 2023, 2024]

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

# Two demo states, cities weighted by rough population
GEOGRAPHY = {
    "IN": {
        "Indianapolis": 30, "Fort Wayne": 12, "Evansville": 8, "South Bend": 8,
        "Carmel": 6, "Fishers": 5, "Bloomington": 5, "Lafayette": 4,
        "Muncie": 3, "Terre Haute": 3,
    },
    "CO": {
        "Denver": 28, "Colorado Springs": 14, "Aurora": 10, "Fort Collins": 7,
        "Lakewood": 6, "Boulder": 5, "Pueblo": 4, "Greeley": 3,
    },
}

SPECIALTIES = {
    "Internal Medicine": 0.26,
    "Family Practice": 0.24,
    "Cardiology": 0.10,
    "Endocrinology": 0.08,
    "Psychiatry": 0.08,
    "Neurology": 0.06,
    "Nurse Practitioner": 0.10,
    "Physician Assistant": 0.08,
}

# Drug portfolio: (brand, generic, class, avg cost per claim USD)
DRUGS = [
    ("Jardiance", "Empagliflozin", "Diabetes - SGLT2", 540),
    ("Farxiga", "Dapagliflozin", "Diabetes - SGLT2", 520),
    ("Ozempic", "Semaglutide", "Diabetes - GLP-1", 890),
    ("Trulicity", "Dulaglutide", "Diabetes - GLP-1", 850),
    ("Januvia", "Sitagliptin", "Diabetes - DPP-4", 480),
    ("Lantus Solostar", "Insulin Glargine", "Diabetes - Insulin", 310),
    ("Eliquis", "Apixaban", "Cardio - Anticoagulant", 500),
    ("Xarelto", "Rivaroxaban", "Cardio - Anticoagulant", 490),
    ("Entresto", "Sacubitril/Valsartan", "Cardio - Heart Failure", 560),
    ("Repatha", "Evolocumab", "Cardio - PCSK9", 470),
    ("Crestor", "Rosuvastatin", "Cardio - Statin", 25),
    ("Lipitor", "Atorvastatin", "Cardio - Statin", 15),
    ("Trelegy Ellipta", "Flu/Umec/Vilanterol", "Respiratory - COPD", 590),
    ("Symbicort", "Budesonide/Formoterol", "Respiratory - Asthma", 320),
    ("Vraylar", "Cariprazine", "CNS - Antipsychotic", 1150),
    ("Rexulti", "Brexpiprazole", "CNS - Antipsychotic", 1250),
]

# Which specialties actually prescribe which classes (affinity 0..1)
AFFINITY = {
    "Diabetes": {"Endocrinology": 1.0, "Internal Medicine": 0.7, "Family Practice": 0.6,
                 "Nurse Practitioner": 0.5, "Physician Assistant": 0.45, "Cardiology": 0.25},
    "Cardio": {"Cardiology": 1.0, "Internal Medicine": 0.6, "Family Practice": 0.5,
               "Nurse Practitioner": 0.4, "Physician Assistant": 0.35},
    "Respiratory": {"Internal Medicine": 0.6, "Family Practice": 0.6,
                    "Nurse Practitioner": 0.5, "Physician Assistant": 0.45},
    "CNS": {"Psychiatry": 1.0, "Neurology": 0.5, "Nurse Practitioner": 0.3,
            "Family Practice": 0.15},
}

FIRST = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael",
         "Linda", "David", "Elizabeth", "William", "Susan", "Richard", "Jessica",
         "Joseph", "Sarah", "Thomas", "Karen", "Priya", "Rahul", "Wei", "Ana",
         "Carlos", "Fatima", "Aisha", "Daniel", "Laura", "Kevin", "Amanda", "Brian"]
LAST = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
        "Davis", "Rodriguez", "Martinez", "Patel", "Chen", "Nguyen", "Kim",
        "Anderson", "Taylor", "Thomas", "Moore", "Jackson", "Martin", "Lee",
        "Thompson", "White", "Harris", "Clark", "Lewis", "Walker", "Hall"]


def build_prescribers(rng: random.Random) -> pd.DataFrame:
    cities, weights, states = [], [], []
    for state, city_w in GEOGRAPHY.items():
        for city, w in city_w.items():
            cities.append(city)
            weights.append(w)
            states.append(state)

    spec_names = list(SPECIALTIES)
    spec_w = list(SPECIALTIES.values())

    rows = []
    used_npis: set[int] = set()
    for _ in range(N_PRESCRIBERS):
        npi = rng.randint(1_000_000_000, 1_999_999_999)
        while npi in used_npis:
            npi = rng.randint(1_000_000_000, 1_999_999_999)
        used_npis.add(npi)

        idx = rng.choices(range(len(cities)), weights=weights, k=1)[0]
        rows.append({
            "npi": npi,
            "prescriber_name": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
            "specialty": rng.choices(spec_names, weights=spec_w, k=1)[0],
            "city": cities[idx],
            "state": states[idx],
        })
    return pd.DataFrame(rows)


def assign_territories(prescribers: pd.DataFrame, rng: random.Random) -> pd.DataFrame:
    """Group cities into territories of roughly balanced prescriber counts.

    Big cities are split into multiple territories (Metro A/B/...);
    small cities are bundled with neighbors. This mirrors how pharma
    alignments balance workload, and is documented as synthetic.
    """
    territories = []
    t_id = 0
    for state in GEOGRAPHY:
        state_p = prescribers[prescribers.state == state]
        counts = state_p.city.value_counts()
        target = max(40, int(len(state_p) / 8))  # ~8 territories per state

        bundle, bundle_n = [], 0
        for city, n in counts.items():
            if n >= target:  # split large metro
                n_parts = round(n / target) or 1
                for part in range(n_parts):
                    t_id += 1
                    territories.append({
                        "territory_id": t_id,
                        "territory_name": f"{city} Metro {chr(65 + part)}" if n_parts > 1 else city,
                        "state": state,
                        "cities": [city],
                        "metro_part": (part, n_parts),
                    })
            else:
                bundle.append(city)
                bundle_n += n
                if bundle_n >= target:
                    t_id += 1
                    territories.append({
                        "territory_id": t_id,
                        "territory_name": f"{bundle[0]} Region",
                        "state": state, "cities": bundle, "metro_part": None,
                    })
                    bundle, bundle_n = [], 0
        if bundle:
            t_id += 1
            territories.append({
                "territory_id": t_id, "territory_name": f"{bundle[0]} Region",
                "state": state, "cities": bundle, "metro_part": None,
            })

    # map each prescriber to a territory
    assignment: dict[int, int] = {}
    for state in GEOGRAPHY:
        for city in GEOGRAPHY[state]:
            parts = [t for t in territories if t["state"] == state and city in t["cities"]]
            idxs = prescribers.index[(prescribers.state == state) & (prescribers.city == city)]
            if len(parts) == 1:
                for i in idxs:
                    assignment[i] = parts[0]["territory_id"]
            else:  # round-robin across metro splits
                parts = sorted(parts, key=lambda t: t["metro_part"][0])
                for k, i in enumerate(idxs):
                    assignment[i] = parts[k % len(parts)]["territory_id"]

    prescribers = prescribers.copy()
    prescribers["territory_id"] = prescribers.index.map(assignment)

    reps = [f"{rng.choice(FIRST)} {rng.choice(LAST)}" for _ in territories]
    dim_territory = pd.DataFrame([
        {"territory_id": t["territory_id"], "territory_name": t["territory_name"],
         "state": t["state"], "region": "Midwest" if t["state"] == "IN" else "West",
         "rep_name": reps[i]}
        for i, t in enumerate(territories)
    ])
    return prescribers, dim_territory


def build_facts(prescribers: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Prescription volumes: lognormal (a few whales, long tail) x
    specialty-class affinity x per-year drug trend."""
    drug_rows = [
        {"drug_id": i + 1, "brand_name": b, "generic_name": g,
         "drug_class": c, "avg_cost": cost}
        for i, (b, g, c, cost) in enumerate(DRUGS)
    ]
    # market momentum: GLP-1s growing fast, statin flat, etc.
    trend = {"Diabetes - GLP-1": 1.35, "Diabetes - SGLT2": 1.18, "Cardio - Anticoagulant": 1.08,
             "Cardio - Heart Failure": 1.10, "Cardio - PCSK9": 1.15, "CNS - Antipsychotic": 1.06}

    facts = []
    base_volume = rng.lognormal(mean=2.1, sigma=0.9, size=len(prescribers))
    for p_pos, (_, p) in enumerate(prescribers.iterrows()):
        for d in drug_rows:
            family = d["drug_class"].split(" - ")[0]
            aff = AFFINITY.get(family, {}).get(p["specialty"], 0.05)
            if aff <= 0.05 and rng.random() > 0.08:
                continue  # most off-specialty pairs never prescribe
            for y_i, year in enumerate(YEARS):
                yearly = trend.get(d["drug_class"], 1.0) ** y_i
                lam = base_volume[p_pos] * aff * yearly * rng.uniform(0.6, 1.4)
                claims = int(rng.poisson(lam))
                if claims < 11:
                    continue  # CMS suppresses cells with <11 claims
                cost_noise = rng.uniform(0.85, 1.15)
                facts.append({
                    "npi": p["npi"], "drug_id": d["drug_id"], "year": year,
                    "total_claims": claims,
                    "total_30day_fills": int(claims * rng.uniform(1.05, 1.6)),
                    "total_drug_cost": round(claims * d["avg_cost"] * cost_noise, 2),
                    "total_beneficiaries": max(1, int(claims * rng.uniform(0.45, 0.8))),
                })
    dim_drug = pd.DataFrame(drug_rows).drop(columns=["avg_cost"])
    return dim_drug, pd.DataFrame(facts)


def main() -> None:
    rng_py = random.Random(RNG_SEED)
    rng_np = np.random.default_rng(RNG_SEED)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    prescribers = build_prescribers(rng_py)
    prescribers, dim_territory = assign_territories(prescribers, rng_py)
    dim_drug, facts = build_facts(prescribers, rng_np)

    prescribers.to_csv(DATA_DIR / "dim_prescriber.csv", index=False)
    dim_territory.to_csv(DATA_DIR / "dim_territory.csv", index=False)
    dim_drug.to_csv(DATA_DIR / "dim_drug.csv", index=False)
    facts.to_csv(DATA_DIR / "fact_prescriptions.csv", index=False)

    print(f"prescribers: {len(prescribers):>7,}")
    print(f"territories: {len(dim_territory):>7,}")
    print(f"drugs:       {len(dim_drug):>7,}")
    print(f"fact rows:   {len(facts):>7,}")
    print(f"written to {DATA_DIR}")


if __name__ == "__main__":
    main()
