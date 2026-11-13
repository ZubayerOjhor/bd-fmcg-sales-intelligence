"""Products, price list and the trading calendar."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from ..config import (BRANDS, DISTRIBUTOR_MARGIN, EID_UL_ADHA, EID_UL_FITR, PRICE_CHANGES,
                      RETAILER_MARGIN, Settings)


def products() -> pd.DataFrame:
    rows = []
    for b_i, (brand, b) in enumerate(BRANDS.items()):
        for s_i, sku in enumerate(b["skus"]):
            pack, mrp, case, mix = sku[:4]
            launch = sku[4] if len(sku) > 4 else None
            rows.append({
                "sku_id": f"{brand[:3].upper()}-{s_i + 1:02d}", "brand": brand, "category": b["category"],
                "pack": pack, "sku_name": f"{brand} {pack}", "mrp_list": float(mrp), "case_size": case,
                "mix_weight": mix, "launch_date": launch,
            })
    return pd.DataFrame(rows)


def _tp(mrp: float) -> float:
    return round(mrp * (1 - RETAILER_MARGIN), 2)


def _dp(mrp: float) -> float:
    return round(_tp(mrp) * (1 - DISTRIBUTOR_MARGIN), 2)


def price_list(p: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    """Slowly changing price list: one row per SKU per price period."""
    rows = []
    for s in p.itertuples():
        changes = sorted((d, f) for b, d, f in PRICE_CHANGES if b == s.brand)
        start, mrp = settings.start, s.mrp_list
        for d, f in changes:
            rows.append((s.sku_id, start, d - timedelta(days=1), mrp))
            start, mrp = d, round(mrp * f)
        rows.append((s.sku_id, start, None, mrp))
    out = pd.DataFrame(rows, columns=["sku_id", "valid_from", "valid_to", "mrp"])
    out["tp"] = out.mrp.map(_tp)
    out["dp"] = out.mrp.map(_dp)
    return out


def calendar(settings: Settings) -> pd.DataFrame:
    days = pd.date_range(settings.start, settings.as_of, freq="D")
    c = pd.DataFrame({"date": days.date})
    c["weekday"] = days.day_name().str[:3]
    c["is_friday"] = days.weekday == 4
    c["eid"] = ""
    c["is_holiday"] = False
    for name, eids, before, after in (("Eid ul-Fitr", EID_UL_FITR, 1, 3), ("Eid ul-Adha", EID_UL_ADHA, 1, 2)):
        for e in eids:
            mask = (c.date >= e - timedelta(days=before)) & (c.date <= e + timedelta(days=after))
            c.loc[mask, "is_holiday"] = True
            c.loc[mask, "eid"] = name
    c.loc[c.date.map(lambda d: (d.month, d.day) in {(2, 21), (3, 26), (4, 14), (12, 16)}), "is_holiday"] = True
    c["is_working_day"] = ~c.is_friday & ~c.is_holiday
    c["month"] = days.to_period("M").astype(str)
    return c


def eid_multiplier(day: date, kind: str) -> float:
    """Demand multiplier around the two Eids, by brand behaviour."""
    m = 1.0
    for e in EID_UL_FITR:
        k = (e - day).days
        if 2 <= k <= 16:  # the pre-Eid shopping rush builds towards the holiday
            m *= {"detergent": 1.12, "winter": 1.10, "summer": 1.2}.get(kind, 1.0 + 0.55 * (17 - k) / 15)
        elif -10 <= k <= -4:
            m *= 0.78
    for e in EID_UL_ADHA:
        k = (e - day).days
        if 2 <= k <= 10:
            m *= {"detergent": 1.25}.get(kind, 1.15)
        elif -9 <= k <= -3:
            m *= {"detergent": 1.22}.get(kind, 0.88)
    return m


def month_position_multiplier(day: date) -> float:
    """SRs push harder in the last days of the month, then trade is slow for a few days."""
    nxt = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
    left = (nxt - day).days
    if left <= 5:
        return 1.10
    if day.day <= 4:
        return 0.93
    return 1.0


def working_days(cal: pd.DataFrame) -> np.ndarray:
    return cal.is_working_day.to_numpy()
