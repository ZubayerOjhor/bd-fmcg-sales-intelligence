"""Settings, the product catalogue and the market calendar for the fictional company.

Everything about the company is invented. The geography (64 districts, 2022 census population)
and the festival calendar are real; they shape where and when demand happens.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "data" / "reference"

COMPANY = "Kadam Consumer Ltd."  # fictional
CURRENCY = "BDT"


@dataclass(frozen=True)
class Settings:
    start: date = date(2024, 1, 1)
    as_of: date = date(2026, 11, 12)  # last day with data; the dashboard is "as of" this date
    seed: int = 2026
    out_dir: Path = ROOT / "data" / "raw"
    warehouse: Path = ROOT / "data" / "warehouse.duckdb"
    dashboard_data: Path = ROOT / "dashboard" / "data"
    # Company secondary sales in 2024, before growth; about BDT 1,000 crore a year.
    base_annual_value: float = 10.0e9
    regions: tuple[str, ...] = field(default_factory=tuple)  # empty means all

    @classmethod
    def from_env(cls) -> "Settings":
        s = cls()
        if v := os.getenv("FMCG_AS_OF"):
            s = Settings(**{**s.__dict__, "as_of": date.fromisoformat(v)})
        return s


# --- Sales regions -------------------------------------------------------------------------
# Six regions built from the eight divisions, sized so each carries a similar sales load.
DHAKA_METRO = {"Dhaka", "Gazipur", "Narayanganj", "Narsingdi", "Munshiganj"}


def region_for(division: str, district: str) -> str:
    if district in DHAKA_METRO:
        return "Dhaka Metro"
    return {
        "Dhaka": "Dhaka Central",
        "Chattogram": "Chattogram",
        "Rajshahi": "North",
        "Rangpur": "North",
        "Khulna": "South-West",
        "Barishal": "South-West",
        "Mymensingh": "North-East",
        "Sylhet": "North-East",
    }[division]


# Purchasing power index (synthetic, metro highest). Drives value per head.
REGION_AFFLUENCE = {
    "Dhaka Metro": 1.65, "Chattogram": 1.15, "Dhaka Central": 0.92,
    "North": 0.80, "South-West": 0.90, "North-East": 0.95,
}
# Days from order to delivery at the distributor.
REGION_LEAD_DAYS = {"Dhaka Metro": 1, "Dhaka Central": 1, "Chattogram": 2,
                    "North": 2, "South-West": 2, "North-East": 2}


# --- Product catalogue ---------------------------------------------------------------------
# brand: category, value share of 2024 sales, annual real growth, seasonality profile,
#        region affinity, and SKUs as (pack, MRP in BDT, units per case, mix weight[, launch date]).
BRANDS: dict[str, dict] = {
    "Nirmol": dict(category="Hair Oil", share=0.16, growth=0.06, season="flat_eid",
                   affinity={"North": 1.15, "Dhaka Metro": 0.85},
                   skus=[("40ml", 38, 144, 0.22), ("100ml", 92, 72, 0.33), ("200ml", 175, 48, 0.30),
                         ("350ml", 295, 24, 0.15)]),
    "Shitol": dict(category="Hair Oil", share=0.09, growth=0.10, season="cooling",
                   affinity={"South-West": 1.15, "Chattogram": 1.1},
                   skus=[("50ml", 60, 144, 0.30), ("100ml", 110, 72, 0.42), ("200ml", 205, 48, 0.28)]),
    "Kesh": dict(category="Shampoo", share=0.11, growth=0.20, season="flat_eid",
                 affinity={"Dhaka Metro": 1.45, "Chattogram": 1.15, "North": 0.8},
                 skus=[("6ml sachet", 5, 960, 0.38), ("80ml", 135, 72, 0.22), ("180ml", 295, 36, 0.28),
                       ("340ml", 520, 24, 0.12)]),
    "Shapla": dict(category="Beauty Soap", share=0.14, growth=0.08, season="flat_eid",
                   affinity={"Dhaka Metro": 1.1},
                   skus=[("75g", 45, 144, 0.30), ("100g", 62, 96, 0.40), ("150g", 88, 72, 0.18),
                         ("3x100g pack", 175, 24, 0.12)]),
    "Raksha": dict(category="Antibacterial Soap", share=0.08, growth=0.04, season="flat_eid",
                   affinity={"North-East": 1.1},
                   skus=[("75g", 48, 144, 0.40), ("100g", 65, 96, 0.45), ("150g", 92, 72, 0.15)]),
    "Hashi": dict(category="Toothpaste", share=0.10, growth=0.12, season="flat_eid",
                  affinity={"Dhaka Metro": 1.2, "North": 0.9},
                  skus=[("45g", 55, 144, 0.30), ("100g", 110, 72, 0.42), ("200g", 205, 48, 0.28)]),
    "Jhakjhak": dict(category="Detergent", share=0.15, growth=0.02, season="detergent",
                     affinity={},
                     skus=[("200g", 38, 120, 0.25), ("500g", 92, 48, 0.40), ("1kg", 175, 24, 0.28),
                           ("2kg", 335, 12, 0.07)]),
    "Kuasha": dict(category="Winter Care", share=0.07, growth=0.14, season="winter",
                   affinity={"North": 1.4, "North-East": 1.15, "South-West": 0.8, "Chattogram": 0.85},
                   skus=[("Petroleum jelly 50ml", 85, 144, 0.34), ("Petroleum jelly 100ml", 150, 72, 0.24),
                         ("Body lotion 100ml", 210, 48, 0.24), ("Body lotion 200ml", 380, 24, 0.18),
                         ("Aloe lotion 200ml", 420, 24, 0.20, date(2025, 10, 15))]),
    "Gormi": dict(category="Prickly Heat Powder", share=0.05, growth=0.09, season="summer",
                  affinity={"South-West": 1.2, "Chattogram": 1.1, "North": 0.85},
                  skus=[("50g", 65, 144, 0.30), ("100g", 120, 72, 0.45), ("200g", 215, 48, 0.25)]),
    "Aram": dict(category="Pain Balm", share=0.05, growth=0.07, season="flat",
                 affinity={"North": 1.1, "North-East": 1.1},
                 skus=[("9ml", 40, 288, 0.55), ("25ml", 95, 144, 0.45)]),
}

RETAILER_MARGIN = 0.12      # MRP to trade price (TP, what the retailer pays)
DISTRIBUTOR_MARGIN = 0.045  # TP to distributor price (DP, what the distributor pays us)

# Price changes (MRP, from this date on).
PRICE_CHANGES = [
    ("Jhakjhak", date(2025, 7, 1), 1.08),   # raw material costs; volume falls with elasticity
    ("Hashi", date(2026, 1, 1), 1.05),
    ("Kesh", date(2026, 3, 1), 1.06),
]
PRICE_ELASTICITY = -0.6

# Monthly seasonality (Jan..Dec); each profile averages about 1.
SEASON = {
    "flat":      [1.00, 0.98, 1.00, 1.02, 1.00, 0.98, 0.97, 0.98, 1.00, 1.02, 1.02, 1.03],
    "flat_eid":  [1.00, 0.97, 1.02, 1.03, 1.00, 0.98, 0.96, 0.97, 0.99, 1.02, 1.02, 1.04],
    "cooling":   [0.70, 0.80, 1.00, 1.25, 1.35, 1.30, 1.20, 1.15, 1.05, 0.90, 0.75, 0.70],
    "summer":    [0.40, 0.60, 1.00, 1.50, 1.70, 1.60, 1.40, 1.30, 1.10, 0.80, 0.50, 0.40],
    "winter":    [2.20, 1.40, 0.60, 0.35, 0.30, 0.30, 0.30, 0.35, 0.50, 1.00, 1.90, 2.40],
    "detergent": [1.00, 0.98, 1.00, 1.00, 1.02, 1.04, 1.05, 1.03, 1.00, 0.98, 0.95, 0.97],
}

# Real festival dates (Bangladesh). Eid dates are as observed in Bangladesh, 2026 as expected.
EID_UL_FITR = [date(2024, 4, 11), date(2025, 3, 31), date(2026, 3, 21)]
EID_UL_ADHA = [date(2024, 6, 17), date(2025, 6, 7), date(2026, 5, 27)]

# Synthetic supply events: a plant problem stops shipments of one SKU.
SUPPLY_CUTS = [
    ("Kesh", "180ml", date(2026, 9, 6), date(2026, 9, 27)),
    ("Nirmol", "200ml", date(2025, 11, 9), date(2025, 11, 23)),
]

# Business plan growth on last year's actual sales (a stretch above the real trend).
PLAN_GROWTH = {2025: 0.11, 2026: 0.13}
