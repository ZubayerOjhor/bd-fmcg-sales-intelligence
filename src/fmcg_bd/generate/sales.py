"""Day-by-day simulation of the route to market.

For every working day and every territory x SKU:
  1. Consumer demand reaches the shops (population, purchasing power, season, Eid, price, trend).
  2. The distributor sells to shops from its own stock (secondary sales). An empty shelf loses the sale.
  3. Twice a week the distributor orders from the company (primary sales), to a stock-cover target.
     In the last working days of the month the company "loads" extra stock to close its own target.
Secondary sales are then attributed to the SRs who were working the territory that day.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from ..config import BRANDS, EID_UL_FITR, PRICE_ELASTICITY, REGION_LEAD_DAYS, SEASON, SUPPLY_CUTS, Settings
from .catalog import eid_multiplier, month_position_multiplier

# Synthetic regional shocks: (region, from, to, demand multiplier).
SHOCKS = [
    ("North-East", date(2026, 6, 16), date(2026, 7, 6), 0.72),   # flash flood
    ("North", date(2025, 8, 9), date(2025, 8, 24), 0.86),        # prolonged heavy rain
    ("Chattogram", date(2025, 2, 2), date(2025, 2, 13), 0.9),    # transport strike
]
ORDER_WEEKDAYS = {6, 2}  # Sunday and Wednesday


def allocate(total: np.ndarray, weights: np.ndarray, group: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Split integer totals per group across members by weight; parts sum exactly to the total.

    Returns (parts per member, unallocated per group) where a group has no weight.
    """
    W = np.bincount(group, weights, minlength=len(total))
    ok = W[group] > 0
    raw = np.where(ok, total[group] * weights / np.where(W[group] > 0, W[group], 1), 0.0)
    fl = np.floor(raw).astype(np.int64)
    rem = total - np.bincount(group, fl, minlength=len(total))
    frac = raw - fl
    order = np.lexsort((-frac, group))
    g_sorted = group[order]
    first = np.searchsorted(g_sorted, g_sorted, side="left")
    rank = np.arange(len(order)) - first
    bump = np.zeros(len(group), dtype=np.int64)
    bump[order] = (rank < rem[g_sorted]).astype(np.int64)
    parts = np.where(ok, fl + bump, 0)
    unallocated = np.where(W > 0, 0, total)
    return parts, unallocated


def simulate(settings: Settings, rng: np.random.Generator, org: dict, prod: pd.DataFrame,
             prices: pd.DataFrame, cal: pd.DataFrame) -> dict[str, pd.DataFrame]:
    terr = org["dim_territory"].reset_index(drop=True)
    srs = org["dim_sr"].reset_index(drop=True)
    T, S = len(terr), len(prod)
    brands = list(BRANDS)
    B = len(brands)
    sku_brand = prod.brand.map({b: i for i, b in enumerate(brands)}).to_numpy()
    days = list(cal.date)
    D = len(days)
    d0 = days[0]

    # --- static demand structure ---------------------------------------------------------
    affinity = np.array([[BRANDS[b]["affinity"].get(r, 1.0) for b in brands] for r in terr.region])
    tw = (terr.population.to_numpy()[:, None] * terr.affluence.to_numpy()[:, None]
          * affinity * terr.strength.to_numpy()[:, None])
    tw = tw / tw.sum(0, keepdims=True)                                    # T x B, sums to 1 per brand
    brand_day_value = np.array([settings.base_annual_value * BRANDS[b]["share"] / 300 for b in brands])
    growth = np.array([BRANDS[b]["growth"] for b in brands])
    season_kind = [BRANDS[b]["season"] for b in brands]
    season = np.array([SEASON[k] for k in season_kind])                  # B x 12
    launch = prod.launch_date.map(lambda x: x if isinstance(x, date) else date.min).to_numpy()
    mix = prod.mix_weight.to_numpy(float)
    case = prod.case_size.to_numpy()
    list_tp = prices.sort_values("valid_from").groupby("sku_id").tp.first().reindex(prod.sku_id).to_numpy()
    sku_tsku = {(r.brand, r.pack): i for i, r in enumerate(prod.itertuples())}
    lead = terr.region.map(REGION_LEAD_DAYS).to_numpy()
    # Working days of stock each distributor aims to hold, per SKU: slow SKUs get neglected.
    cover = rng.uniform(2, 6, (T, 1)) * np.where(rng.random((T, S)) < 0.3, rng.uniform(0.0, 0.35, (T, S)), 1.0)
    weekly_only = rng.random(T) < 0.4                                     # smaller distributors order once a week
    region_idx = {r: np.where(terr.region.to_numpy() == r)[0] for r in terr.region.unique()}

    # Price per SKU per day (TP to shops, DP to distributors).
    tp = np.zeros((D, S))
    dp = np.zeros((D, S))
    sku_pos = {s: i for i, s in enumerate(prod.sku_id)}
    day_ord = np.array([d.toordinal() for d in days])
    for p in prices.itertuples():
        lo = p.valid_from.toordinal()
        hi = p.valid_to.toordinal() if isinstance(p.valid_to, date) else 10**9
        m = (day_ord >= lo) & (day_ord <= hi)
        tp[m, sku_pos[p.sku_id]] = p.tp
        dp[m, sku_pos[p.sku_id]] = p.dp
    price_effect = (tp / list_tp[None, :]) ** PRICE_ELASTICITY

    # Slow local drift (AR(1) per territory per month): competition, distributor energy.
    months = sorted({(d.year, d.month) for d in days})
    drift = np.zeros((len(months), T))
    for i in range(1, len(months)):
        drift[i] = 0.75 * drift[i - 1] + rng.normal(0, 0.045, T)
    month_idx = {m: i for i, m in enumerate(months)}

    # Field force: who is working, and how strong the team in each territory is.
    sr_terr = srs.territory_id.map({t: i for i, t in enumerate(terr.territory_id)}).to_numpy()
    sr_join = np.array([d.toordinal() for d in srs.join_date])
    sr_leave = np.array([d.toordinal() if isinstance(d, date) else 10**9 for d in srs.leave_date])
    sr_q = srs.quality.to_numpy()
    sr_route = srs.route_outlets.to_numpy()
    sr_skill = rng.lognormal(0, 0.10, (len(srs), B))
    nominal = np.bincount(sr_terr, sr_route.astype(float), minlength=T) / np.bincount(
        srs.drop_duplicates("position_id").territory_id.map(
            {t: i for i, t in enumerate(terr.territory_id)}), minlength=T).clip(1) * terr.sr_positions.to_numpy()

    # Month-end loading flags: the last three working days of each month.
    cal = cal.reset_index(drop=True)
    wd = cal.is_working_day.to_numpy()
    month_key = np.array([(d.year, d.month) for d in days])
    last3 = np.zeros(D, bool)
    for m in months:
        idx = np.where((month_key[:, 0] == m[0]) & (month_key[:, 1] == m[1]) & wd)[0]
        last3[idx[-3:]] = True
    load_days = rng.gamma(2.0, 1.6, (len(months), T))                    # extra days of stock pushed
    # Cash-strapped months: the distributor can only pay for part of what it needs.
    cash = np.where(rng.random((len(months), T)) < 0.15, rng.uniform(0.2, 0.5, (len(months), T)), 1.0)

    # --- state ------------------------------------------------------------------------------
    stock = np.zeros((T, S))
    arrive = np.zeros((D + 8, T, S))
    fc = None
    sec_rows, pri_rows, sr_rows, call_rows, unalloc_rows, stock_rows = [], [], [], [], [], []
    fitr_ord = [e.toordinal() for e in EID_UL_FITR]

    for i, day in enumerate(days):
        mi = month_idx[(day.year, day.month)]
        launched = launch <= day
        # Expected demand in units today (T x S).
        mult_b = (season[:, day.month - 1]
                  * np.array([eid_multiplier(day, k) for k in season_kind])
                  * (1 + growth) ** ((day - d0).days / 365.25))
        mix_today = np.where(launched, mix, 0.0)
        mix_norm = np.bincount(sku_brand, mix_today, minlength=B)[sku_brand]
        sku_share = np.where(mix_norm > 0, mix_today / np.where(mix_norm > 0, mix_norm, 1), 0)
        lam_value = (brand_day_value[sku_brand] * mult_b[sku_brand] * sku_share)[None, :] * tw[:, sku_brand]
        local = np.exp(drift[mi]) * month_position_multiplier(day)
        for r, lo, hi, f in SHOCKS:
            if lo <= day <= hi and r in region_idx:
                local[region_idx[r]] *= f

        active = (sr_join <= day.toordinal()) & (sr_leave >= day.toordinal())
        ramp = np.where(day.toordinal() - sr_join < 60, 0.8, 1.0)
        eff = np.bincount(sr_terr, active * sr_route * sr_q * ramp, minlength=T)
        team = np.sqrt(np.clip(eff / nominal, 0.2, 1.4))
        local = local * team

        lam_units = lam_value / list_tp[None, :] * price_effect[i][None, :] * local[:, None]
        if fc is None:
            fc = lam_units.copy()
            stock = fc * cover

        stock += arrive[i]
        if i + 1 == D or days[i + 1].month != day.month:  # month-end stock count at the distributor
            t_k, s_k = np.nonzero(launched[None, :] & np.ones((T, 1), bool))
            stock_rows.append(np.column_stack([np.full(len(t_k), i), t_k, s_k,
                                               np.floor(stock[t_k, s_k]).astype(np.int64)]))
        if not wd[i]:
            continue
        demand = rng.poisson(lam_units * rng.lognormal(0, 0.10, (T, S)))
        demand = np.where(launched[None, :], demand, 0)
        sold = np.minimum(demand, np.floor(stock)).astype(np.int64)
        lost = demand - sold
        stock -= sold
        fc = 0.9 * fc + 0.1 * demand

        t_idx, s_idx = np.nonzero(sold + lost)
        sec_rows.append(np.column_stack([np.full(len(t_idx), i), t_idx, s_idx, sold[t_idx, s_idx],
                                         lost[t_idx, s_idx]]))

        # Distributor orders.
        if day.weekday() in ORDER_WEEKDAYS or last3[i]:
            pre_eid = any(0 <= f - day.toordinal() <= 25 for f in fitr_ord)
            review = np.where(weekly_only, 6, 3) + lead                       # days until the next delivery
            target = fc * (cover * (1.3 if pre_eid else 1.0) + review[:, None])
            pipeline = arrive[i + 1:].sum(0)
            order_today = np.full(T, day.weekday() == 6) | ((day.weekday() == 2) & ~weekly_only)
            need = np.maximum(0, target - stock - pipeline) * order_today[:, None]
            need = need * cash[mi][:, None]
            if last3[i]:
                need = need + fc * load_days[mi][:, None] / 3
            need = np.where(launched[None, :], need, 0)
            for b, pack, lo, hi in SUPPLY_CUTS:
                if lo <= day <= hi and (b, pack) in sku_tsku:
                    need[:, sku_tsku[(b, pack)]] = 0
            cases = np.ceil(need / case[None, :] - 0.15).clip(0)
            units = (cases * case[None, :]).astype(np.int64)
            t_o, s_o = np.nonzero(units)
            pri_rows.append(np.column_stack([np.full(len(t_o), i), t_o, s_o, units[t_o, s_o]]))
            for t in np.unique(t_o):
                arrive[i + lead[t], t] += units[t]

        # Attribute the day's secondary value (in poisha) to working SRs, by brand.
        val = np.rint(sold * tp[i][None, :] * 100).astype(np.int64)            # T x S
        vb = np.zeros((T, B), np.int64)
        ub = np.zeros((T, B), np.int64)
        np.add.at(vb, (slice(None), sku_brand), val)
        np.add.at(ub, (slice(None), sku_brand), sold)
        a = np.nonzero(active)[0]
        noise = rng.lognormal(0, 0.12, len(a))
        w = (sr_route[a] * sr_q[a] * ramp[a] * noise)[:, None] * sr_skill[a]       # nA x B
        grp = (sr_terr[a][:, None] * B + np.arange(B)[None, :]).ravel()
        pv, uv = allocate(vb.ravel(), w.ravel(), grp)
        pu, uu = allocate(ub.ravel(), w.ravel(), grp)
        rows_sr = np.repeat(a, B)
        rows_b = np.tile(np.arange(B), len(a))
        keep = (pv > 0) | (pu > 0)
        sr_rows.append(np.column_stack([np.full(keep.sum(), i), rows_sr[keep], rows_b[keep], pu[keep], pv[keep]]))
        if uv.any():
            g = np.nonzero(uv)[0]
            unalloc_rows.append(np.column_stack([np.full(len(g), i), g // B, g % B, uu[g], uv[g]]))

        # Calls made by each working SR.
        q = sr_q[a]
        visited = rng.binomial(sr_route[a], np.clip(0.9 + 0.08 * (q - 1), 0.75, 0.99))
        strike = np.clip(0.52 + 0.30 * (q - 1) + 0.12 * (mult_b.mean() - 1) + rng.normal(0, 0.04, len(a)), 0.25, 0.9)
        productive = rng.binomial(visited, strike)
        lines = np.rint(productive * np.clip(rng.normal(3.1 + 1.1 * (q - 1), 0.25, len(a)), 1.5, 6)).astype(int)
        call_rows.append(np.column_stack([np.full(len(a), i), a, sr_route[a], visited, productive, lines]))

    def frame(rows, cols):
        arr = np.concatenate(rows) if rows else np.zeros((0, len(cols)), np.int64)
        return pd.DataFrame(arr, columns=cols)

    sec = frame(sec_rows, ["d", "t", "s", "delivered_units", "short_units"])
    sec["ordered_units"] = sec.delivered_units + sec.short_units
    sec["delivered_value"] = np.round(sec.delivered_units * tp[sec.d, sec.s], 2)
    pri = frame(pri_rows, ["d", "t", "s", "units"])
    pri["invoice_value"] = np.round(pri.units * dp[pri.d, pri.s], 2)
    sr = frame(sr_rows, ["d", "r", "b", "units", "value_poisha"])
    calls = frame(call_rows, ["d", "r", "scheduled_calls", "visited", "productive_calls", "lines_sold"])
    un = frame(unalloc_rows, ["d", "t", "b", "units", "value_poisha"])
    stk = frame(stock_rows, ["d", "t", "s", "closing_units"])
    return {"sec": sec, "stock": stk, "pri": pri, "sr": sr, "calls": calls, "unalloc": un,
            "tp": tp, "dp": dp, "days": days, "sku_brand": sku_brand}
