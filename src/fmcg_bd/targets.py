"""Target setting: from the annual business plan down to each SR, every month.

1. Annual plan per brand   = last year's actual x (1 + plan growth). Brands that grew faster
                             than the company last year get a proportionally higher plan.
2. Monthly phasing         = last year's monthly shape, corrected for working days this year.
3. Territory split         = 40% last year's share in the same month
                           + 40% share in the latest three closed months (momentum)
                           + 20% share of potential (population x purchasing power).
4. Guardrails              = each territory between -5% and +30% of its own last year; the excess
                             is redistributed to the territories still inside the band.
5. SR split                = 70% the position's median monthly share of the territory in the latest
                             three closed months, 30% its share of route outlets, and never below 60%
                             of its route share (so a beat that was empty does not get a tiny target).
                             Positions empty on the 1st are held as "VACANT".
Targets for month M are issued on the 25th of M-1, so the latest closed month is M-2.
"""

from __future__ import annotations

from datetime import date

import duckdb
import numpy as np
import pandas as pd

from .config import PLAN_GROWTH, Settings
from .generate import catalog

W_LY, W_RECENT, W_POTENTIAL = 0.40, 0.40, 0.20
FLOOR, CAP = -0.05, 0.30


def round_to(values: np.ndarray, step: float, total: float | None = None) -> np.ndarray:
    """Round to a step so the parts still add up to the (rounded) total: largest remainder."""
    units = values / step
    total_units = round((values.sum() if total is None else total) / step)
    fl = np.floor(units)
    short = int(total_units - fl.sum())
    order = np.argsort(-(units - fl), kind="stable")
    fl[order[:max(short, 0)]] += 1
    return fl * step


def apply_guardrails(raw: np.ndarray, ly: np.ndarray, floor: float = FLOOR, cap: float = CAP) -> tuple[np.ndarray, np.ndarray]:
    """Keep each part within [ly*(1+floor), ly*(1+cap)] and preserve the total.

    Returns the adjusted parts and a flag per part: -1 floored, +1 capped, 0 free.
    Parts with no history (ly == 0) are always free.
    """
    total = raw.sum()
    has = ly > 0
    lo = np.where(has, ly * (1 + floor), 0.0)
    hi = np.where(has, ly * (1 + cap), np.inf)
    out = raw.astype(float).copy()
    flag = np.zeros(len(raw), int)
    for _ in range(25):
        out = np.clip(out, lo, hi)
        flag = np.where(out <= lo + 1e-9, -1, np.where(out >= hi - 1e-9, 1, 0)) * has
        gap = total - out.sum()
        if abs(gap) < 1e-6:
            break
        free = flag == 0
        if not free.any():
            break
        out[free] += gap * out[free] / out[free].sum()
    return out, flag


def _month(m: str, k: int) -> str:
    return str(pd.Period(m, "M") + k)


def build(con: duckdb.DuckDBPyConnection, settings: Settings) -> None:
    tbm = con.sql("select month, territory_id, brand, secondary_value v from marts.territory_brand_month").df()
    terr = con.sql("select territory_id, population, affluence from staging.territory order by 1").df()
    full_cal = catalog.calendar(Settings(start=date(settings.start.year, 1, 1),
                                         as_of=date(settings.as_of.year, 12, 31)))
    wd = full_cal.groupby("month").is_working_day.sum()

    pivot = tbm.pivot_table(index=["brand", "month"], columns="territory_id", values="v",
                            aggfunc="sum", fill_value=0.0).reindex(columns=terr.territory_id, fill_value=0.0)
    potential = (terr.population * terr.affluence).to_numpy()
    potential = potential / potential.sum()
    brands = sorted(tbm.brand.unique())
    yearly = tbm.assign(y=tbm.month.str[:4].astype(int)).groupby(["brand", "y"]).v.sum()

    last_target_month = str(pd.Period(settings.as_of, "M") + 1)
    rows = []
    for year in sorted(PLAN_GROWTH):
        if year - 1 < settings.start.year:
            continue
        ly_total = yearly.xs(year - 1, level="y")
        if year - 2 >= settings.start.year:
            g = yearly.xs(year - 1, level="y") / yearly.xs(year - 2, level="y") - 1
            company_g = ly_total.sum() / yearly.xs(year - 2, level="y").sum() - 1
            plan = (PLAN_GROWTH[year] + 0.5 * (g - company_g)).clip(lower=0.03)
        else:
            plan = pd.Series(PLAN_GROWTH[year], index=ly_total.index)
        for b in brands:
            budget = ly_total[b] * (1 + plan[b])
            ly_months = [f"{year - 1}-{m:02d}" for m in range(1, 13)]
            shape = np.array([pivot.loc[(b, m)].sum() if (b, m) in pivot.index else 0.0 for m in ly_months])
            ratio = np.array([wd[f"{year}-{m:02d}"] / max(wd[f"{year - 1}-{m:02d}"], 1) for m in range(1, 13)])
            phase = shape * ratio / (shape * ratio).sum()
            for k in range(12):
                month = f"{year}-{k + 1:02d}"
                if month > last_target_month:
                    break
                n = budget * phase[k]
                ly = pivot.loc[(b, ly_months[k])].to_numpy() if (b, ly_months[k]) in pivot.index else np.zeros(len(terr))
                recent_months = [_month(month, -j) for j in (4, 3, 2)]
                recent = sum(pivot.loc[(b, m)].to_numpy() for m in recent_months if (b, m) in pivot.index)
                ly_share = ly / ly.sum() if ly.sum() else potential
                rc_share = recent / recent.sum() if np.sum(recent) else ly_share
                score = W_LY * ly_share + W_RECENT * rc_share + W_POTENTIAL * potential
                adj, flag = apply_guardrails(n * score, ly)
                final = round_to(adj, 1000, total=n)
                for i, t in enumerate(terr.territory_id):
                    rows.append((month, t, b, final[i], ly[i], ly_share[i], rc_share[i], potential[i],
                                 int(flag[i]), round(float(plan[b]), 4)))
    tgt = pd.DataFrame(rows, columns=["month", "territory_id", "brand", "target_value", "ly_value",
                                      "ly_share", "recent_share", "potential_share", "guardrail", "plan_growth"])
    tgt["issued_on"] = [str((pd.Period(m, "M") - 1).start_time.date().replace(day=25)) for m in tgt.month]
    con.register("tgt_df", tgt)
    con.execute("create or replace table marts.target_territory_brand as select * from tgt_df")
    con.unregister("tgt_df")
    _sr_targets(con, tgt)


def _sr_targets(con: duckdb.DuckDBPyConnection, tgt: pd.DataFrame) -> None:
    srs = con.sql("select sr_id, position_id, territory_id, join_date, leave_date, route_outlets from staging.sr").df()
    route = srs.sort_values("join_date").groupby("position_id").route_outlets.last()
    srs["join_date"] = pd.to_datetime(srs.join_date)
    srs["leave_date"] = pd.to_datetime(srs.leave_date)
    hist = con.sql("""select m.month, s.position_id, m.brand, sum(m.secondary_value) v
                      from marts.sr_brand_month m join staging.sr s using (sr_id) group by all""").df()
    hist = hist.pivot_table(index=["position_id", "brand"], columns="month", values="v", fill_value=0.0)
    positions = srs.groupby("territory_id").position_id.unique().map(sorted)
    holder: dict[tuple[str, str], str] = {}
    for month in tgt.month.unique():
        first = pd.Period(month, "M").start_time
        on = srs[(srs.join_date <= first) & (srs.leave_date.isna() | (srs.leave_date >= first))]
        holder.update({(month, p): s for p, s in zip(on.position_id, on.sr_id)})
    rows = []
    for (month, t, b), g in tgt.groupby(["month", "territory_id", "brand"], sort=False):
        total = g.target_value.iloc[0]
        pos = positions[t]
        recent = [m for m in (_month(month, -j) for j in (4, 3, 2)) if m in hist.columns]
        keys = [(p, b) for p in pos]
        r = route.reindex(pos).to_numpy(float)
        r = r / r.sum()
        if recent:
            h = hist.reindex(keys)[recent].fillna(0).to_numpy()
            share = h / np.where(h.sum(0) > 0, h.sum(0), 1)
            w = 0.7 * np.median(share, axis=1) + 0.3 * r
        else:
            w = r.copy()
        w = np.maximum(w, 0.6 * r)
        parts = round_to(total * w / w.sum(), 100, total=total)
        for p, v in zip(pos, parts):
            rows.append((month, t, b, p, holder.get((month, p), "VACANT"), v))
    df = pd.DataFrame(rows, columns=["month", "territory_id", "brand", "position_id", "sr_id", "target_value"])
    con.register("sr_df", df)
    con.execute("create or replace table marts.target_sr_brand as select * from sr_df")
    con.unregister("sr_df")
