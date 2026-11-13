"""Generate the raw source tables, shaped like the exports of the systems a sales team uses.

  ERP          erp_primary_invoices          company -> distributor invoices
  DMS          dms_secondary_sales           distributor -> shop deliveries, ordered vs delivered
               dms_sr_sales                  the same sales by SR and brand (memo summary)
               dms_sr_calls                  outlet visits per SR per day
               dms_month_end_stock           distributor stock counts
  SFA survey   outlet_universe, outlet_coverage
  Retail audit retail_audit                  market size and shares by category and region
  Masters      dim_* and price_list
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from ..config import BRANDS, Settings
from . import catalog, org, sales

CHANNELS = {  # people per outlet, by channel; modern trade only in big cities
    "Grocery": 190, "Pharmacy": 1400, "Cosmetics": 2600, "Wholesale": 9000,
}
PENETRATION = {"Nirmol": 0.50, "Shitol": 0.30, "Kesh": 0.45, "Shapla": 0.55, "Raksha": 0.32,
               "Hashi": 0.42, "Jhakjhak": 0.50, "Kuasha": 0.30, "Gormi": 0.22, "Aram": 0.26}
CATEGORY_SHARE = {"Hair Oil": 0.21, "Shampoo": 0.09, "Beauty Soap": 0.11, "Antibacterial Soap": 0.08,
                  "Toothpaste": 0.13, "Detergent": 0.10, "Winter Care": 0.17,
                  "Prickly Heat Powder": 0.24, "Pain Balm": 0.29}


def run(settings: Settings | None = None, quiet: bool = False) -> dict[str, pd.DataFrame]:
    settings = settings or Settings()
    t0 = time.time()
    rng = np.random.default_rng(settings.seed)
    o = org.build(settings, rng)
    prod = catalog.products()
    prices = catalog.price_list(prod, settings)
    cal = catalog.calendar(settings)
    sim = sales.simulate(settings, rng, o, prod, prices, cal)

    terr, srs = o["dim_territory"], o["dim_sr"]
    dist = o["dim_distributor"].set_index("territory_id").distributor_id
    days = np.array(sim["days"], dtype=object)
    tid = terr.territory_id.to_numpy()
    sku = prod.sku_id.to_numpy()
    brands = np.array(list(BRANDS))

    sec = sim["sec"]
    dms_secondary = pd.DataFrame({
        "delivery_date": days[sec.d], "distributor_id": dist.reindex(tid[sec.t]).to_numpy(),
        "sku_id": sku[sec.s], "ordered_units": sec.ordered_units, "delivered_units": sec.delivered_units,
        "delivered_value": sec.delivered_value,
    })

    pri = sim["pri"].reset_index(drop=True)
    lead = terr.region.map(sales.REGION_LEAD_DAYS).to_numpy()
    inv = pri.groupby(["d", "t"]).ngroup()
    erp_primary = pd.DataFrame({
        "invoice_no": [f"INV-{days[d].strftime('%y%m')}-{n:06d}" for d, n in zip(pri.d, inv)],
        "invoice_date": days[pri.d], "distributor_id": dist.reindex(tid[pri.t]).to_numpy(),
        "sku_id": sku[pri.s], "units": pri.units, "invoice_value": pri.invoice_value,
        "lead_days": lead[pri.t],
    })

    sr = pd.concat([
        pd.DataFrame({"sales_date": days[sim["sr"].d], "sr_id": srs.sr_id.to_numpy()[sim["sr"].r],
                      "territory_id": srs.territory_id.to_numpy()[sim["sr"].r],
                      "brand": brands[sim["sr"].b], "units": sim["sr"].units,
                      "value": sim["sr"].value_poisha / 100}),
        pd.DataFrame({"sales_date": days[sim["unalloc"].d], "sr_id": None,
                      "territory_id": tid[sim["unalloc"].t], "brand": brands[sim["unalloc"].b],
                      "units": sim["unalloc"].units, "value": sim["unalloc"].value_poisha / 100}),
    ], ignore_index=True)

    c = sim["calls"]
    calls = pd.DataFrame({"visit_date": days[c.d], "sr_id": srs.sr_id.to_numpy()[c.r],
                          "scheduled_calls": c.scheduled_calls, "visited": c.visited,
                          "productive_calls": c.productive_calls, "lines_sold": c.lines_sold})

    stk = sim["stock"]
    stock = pd.DataFrame({"count_date": days[stk.d], "distributor_id": dist.reindex(tid[stk.t]).to_numpy(),
                          "sku_id": sku[stk.s], "closing_units": stk.closing_units})

    universe, coverage = _coverage(settings, terr, srs, calls, sr, rng)
    audit = _retail_audit(sr, terr, rng, settings)

    # The calendar master runs to the end of the year so month and plan totals are known in advance.
    full_cal = catalog.calendar(Settings(start=settings.start, as_of=settings.as_of.replace(month=12, day=31)))
    out = {**o, "dim_product": prod, "price_list": prices, "dim_date": full_cal,
           "erp_primary_invoices": erp_primary, "dms_secondary_sales": dms_secondary,
           "dms_sr_sales": sr, "dms_sr_calls": calls, "dms_month_end_stock": stock,
           "outlet_universe": universe, "outlet_coverage": coverage, "retail_audit": audit}
    settings.out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in out.items():
        df.to_parquet(settings.out_dir / f"{name}.parquet", index=False)
    if not quiet:
        n = sum(len(v) for v in out.values())
        print(f"generated {len(out)} tables, {n:,} rows in {time.time() - t0:.0f}s -> {settings.out_dir}")
    return out


def _coverage(settings, terr, srs, calls, sr, rng):
    rows = []
    for t in terr.itertuples():
        for ch, per in CHANNELS.items():
            rows.append((t.territory_id, ch, int(t.population / per * rng.uniform(0.9, 1.1))))
        if t.region in ("Dhaka Metro", "Chattogram") or t.district in ("Sylhet", "Khulna", "Rajshahi"):
            rows.append((t.territory_id, "Modern Trade", int(t.population / 60000 * t.affluence)))
    universe = pd.DataFrame(rows, columns=["territory_id", "channel", "outlets"])

    # Outlets on SR routes (six beats a week) and outlets that bought each brand in the month.
    c = calls.merge(srs[["sr_id", "territory_id", "route_outlets"]], on="sr_id")
    c["month"] = pd.to_datetime(c.visit_date).dt.to_period("M").astype(str)
    m = c.groupby(["territory_id", "month"]).agg(productive=("productive_calls", "sum"),
                                                 srs=("sr_id", "nunique"),
                                                 route=("route_outlets", "mean")).reset_index()
    m["covered_outlets"] = (m.srs * m.route * 6).round().astype(int)
    s = sr.assign(month=pd.to_datetime(sr.sales_date).dt.to_period("M").astype(str))
    bm = s.groupby(["territory_id", "month", "brand"]).value.sum().reset_index()
    tot = bm.groupby(["territory_id", "month"]).value.transform("sum")
    bm["brand_weight"] = bm.value / tot
    cov = bm.merge(m, on=["territory_id", "month"])
    base = cov.brand.map(PENETRATION)
    intensity = cov.productive / cov.covered_outlets
    p = 1 - np.exp(-intensity * base * (0.6 + 4 * cov.brand_weight))
    cov["buying_outlets"] = (cov.covered_outlets * np.clip(p, 0.02, 0.95)).round().astype(int)
    return universe, cov[["territory_id", "month", "brand", "covered_outlets", "buying_outlets"]]


def _retail_audit(sr, terr, rng, settings):
    """Bi-monthly retail audit: market value by category and region, with competitor shares."""
    cat = {b: v["category"] for b, v in BRANDS.items()}
    s = sr.merge(terr[["territory_id", "region"]], on="territory_id")
    p = pd.to_datetime(s.sales_date).dt.to_period("M")
    s["period"] = (p.dt.year.astype(str) + "-P" + ((p.dt.month + 1) // 2).astype(str))
    s["category"] = s.brand.map(cat)
    own = s.groupby(["period", "region", "category"]).value.sum().reset_index()
    # Only publish periods that have fully closed (the audit lags the month).
    last_full = (pd.Period(settings.as_of, "M") - 1)
    closed = {f"{y}-P{k}" for y in range(settings.start.year, settings.as_of.year + 1) for k in range(1, 7)
              if pd.Period(f"{y}-{2 * k:02d}", "M") <= last_full}
    own = own[own.period.isin(closed)]
    rows = []
    trend = {k: rng.normal(0, 0.01) for k in CATEGORY_SHARE}
    periods = sorted(own.period.unique())
    for r in own.itertuples():
        k = periods.index(r.period)
        share = np.clip(CATEGORY_SHARE[r.category] * (1 + trend[r.category] * k) * rng.lognormal(0, 0.04), 0.03, 0.6)
        offtake = r.value * rng.lognormal(0, 0.03)  # audit measures shop sales to consumers
        market = offtake / share
        comp = rng.dirichlet([6, 4, 2.5, 3]) * (1 - share)
        rows.append({"period": r.period, "region": r.region, "category": r.category,
                     "market_value": round(market, -3), "kadam_share": round(share, 4),
                     "competitor_a_share": round(comp[0], 4), "competitor_b_share": round(comp[1], 4),
                     "competitor_c_share": round(comp[2], 4), "others_share": round(comp[3], 4)})
    return pd.DataFrame(rows)
