"""Export the marts the dashboard reads, as one JSON file, plus written insights."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone

import duckdb
import pandas as pd

from .config import COMPANY, REFERENCE, Settings


def _df(con, sql: str) -> pd.DataFrame:
    return con.sql(sql).df()


def _records(df: pd.DataFrame, digits: int = 4) -> list[dict]:
    return json.loads(df.round(digits).to_json(orient="records"))


def build(con: duckdb.DuckDBPyConnection, settings: Settings) -> dict:
    as_of = settings.as_of.isoformat()
    month = as_of[:7]
    last_closed = str(pd.Period(settings.as_of, "M") - 1)
    next_month = str(pd.Period(settings.as_of, "M") + 1)
    year = as_of[:4]

    mtd = _df(con, """
        select m.*, t.territory, t.district, t.region, t.area, t.territory_officer, t.lat, t.lon
        from marts.mtd_territory_brand m join staging.territory t using (territory_id)""")
    wd_elapsed, wd_in_month = int(mtd.wd_elapsed.max()), int(mtd.wd_in_month.max())

    def summarise(g: pd.DataFrame) -> pd.Series:
        tgt, act, ly = g.target_value.sum(), g.mtd_value.sum(), g.ly_mtd_value.sum()
        proj = g.projected_value.sum()
        return pd.Series({"target": tgt, "mtd": act, "projected": proj, "ly_mtd": ly,
                          "achievement": act / tgt if tgt else None,
                          "projected_achievement": proj / tgt if tgt else None,
                          "yoy": act / ly - 1 if ly else None, "short": g.mtd_short.sum(),
                          "required_per_day": (tgt - act) / max(wd_in_month - wd_elapsed, 1),
                          "current_per_day": act / wd_elapsed})

    overall = summarise(mtd)
    ytd = _df(con, f"""
        select sum(target_value) as target, sum(actual_value) as actual, sum(ly_value) as ly
        from marts.achievement_territory_brand where month between '{year}-01' and '{last_closed}'""").iloc[0]
    fill = _df(con, f"""select sum(delivered_units) / sum(ordered_units) as f from staging.secondary
                        where date >= '{month}-01' and date <= '{as_of}'""").f.iloc[0]
    cover = _df(con, f"""select sum(stock_value_dp) / sum(daily_sales_dp) as c from marts.stock_cover
                         where month = '{last_closed}'""").c.iloc[0]
    people = _df(con, f"""select count(distinct sr_id) as srs from staging.sr
                          where join_date <= '{as_of}' and (leave_date is null or leave_date >= '{as_of}')""").srs.iloc[0]

    trend = _df(con, """
        with a as (select month, sum(target_value) as target, sum(actual_value) as actual, sum(primary_value) as primary_value,
                          sum(short_value) as short_value
                   from marts.achievement_territory_brand group by 1),
             s as (select month, sum(secondary_value) as v from marts.territory_brand_month group by 1)
        select s.month, a.target, s.v as actual, a.primary_value, a.short_value, ly.v as ly_actual
        from s left join a using (month) left join s ly on ly.month = strftime(strptime(s.month || '-01', '%Y-%m-%d') - interval 1 year, '%Y-%m')
        order by 1""")
    trend.loc[trend.month == month, "actual_mtd_only"] = True

    regions = mtd.groupby("region").apply(summarise, include_groups=False).reset_index()
    areas = mtd.groupby(["region", "area"]).apply(summarise, include_groups=False).reset_index()
    terr = mtd.groupby(["territory_id", "territory", "district", "region", "area", "territory_officer", "lat", "lon"]) \
        .apply(summarise, include_groups=False).reset_index()
    districts = mtd.groupby(["district", "region"]).apply(summarise, include_groups=False).reset_index()
    brands_mtd = mtd.groupby("brand").apply(summarise, include_groups=False).reset_index()
    terr_brand = mtd[["territory_id", "brand", "target_value", "mtd_value", "projected_value", "ly_mtd_value"]]

    brand_month = _df(con, """select month, brand, sum(secondary_value) as v from marts.territory_brand_month
                              group by all order by 1, 2""")
    brand_ytd = _df(con, f"""
        select brand, sum(target_value) as target, sum(actual_value) as actual, sum(ly_value) as ly
        from marts.achievement_territory_brand where month between '{year}-01' and '{last_closed}' group by 1""")
    skus = _df(con, f"""
        with cur as (select sku_id, sku_name, brand, category, pack, sum(secondary_value) as v, sum(short_value) as s,
                            sum(units) as u, sum(units) / sum(units / fill_rate) as fill
                     from marts.sku_month where month between '{year}-01' and '{last_closed}' group by all),
             ly as (select sku_id, sum(secondary_value) as v from marts.sku_month
                    where month between '{int(year) - 1}-01' and '{int(year) - 1}{last_closed[4:]}' group by 1)
        select cur.*, ly.v as ly_v from cur left join ly using (sku_id) order by cur.v desc""")
    sku_short_month = _df(con, """select month, sku_name, short_value from marts.sku_month
                                  where month >= '2025-07' and short_value > 0 order by month""")

    srs = _df(con, f"""
        select s.sr_id, r.sr_name, t.territory, t.region, s.target_value, s.actual_value, s.achievement,
               s.strike_rate, s.lines_per_call, s.days_worked, s.payout_bdt, s.payout_ratio,
               r.join_date
        from marts.sr_scorecard s join staging.sr r using (sr_id) join staging.territory t on t.territory_id = s.territory_id
        where s.month = '{last_closed}' order by s.achievement desc""")
    srs["join_date"] = srs.join_date.astype(str)
    payout_trend = _df(con, """select month, sum(payout_bdt) as payout, avg((achievement >= 1)::int) as hit_rate,
                                      count(*) as srs, avg(strike_rate) as strike, avg(lines_per_call) as lpc
                               from marts.sr_scorecard where month <= (select max(month) from marts.sr_month_calls)
                               group by 1 order by 1""")
    vacancy = _df(con, f"""select count(*) filter (where sr_id = 'VACANT') as vacant, count(*) as total
                           from (select distinct month, position_id, sr_id from marts.target_sr_brand where month = '{month}')""").iloc[0]

    distribution = _df(con, """
        with u as (select t.region, sum(o.outlets) as universe from staging.outlet_universe o
                   join staging.territory t using (territory_id) group by 1),
             c as (select t.region, c.month, c.brand, sum(c.buying_outlets) as buying, sum(c.covered_outlets) as covered
                   from staging.coverage c join staging.territory t using (territory_id) group by all)
        select c.*, u.universe, c.buying / u.universe as numeric_distribution, c.covered / u.universe / 10 as coverage
        from c join u using (region) order by month""")
    universe = _df(con, """select channel, sum(outlets) as outlets from staging.outlet_universe group by 1 order by 2 desc""")

    stock = _df(con, f"""
        with sc as (select territory_id, cover_days, stock_value_dp from marts.stock_cover where month = '{last_closed}'),
             pri as (select territory_id, sum(primary_value) as p, sum(secondary_value) as s, sum(short_value) as sh,
                            sum(ordered_units) as o
                     from marts.territory_brand_month where month = '{last_closed}' group by 1),
             load as (select p.territory_id, sum(case when c.wd_in_month - c.wd_elapsed < 3 then p.invoice_value end)
                             / sum(p.invoice_value) as month_end_share
                      from staging.primary_sales p join staging.calendar c on c.date = p.date
                      where strftime(p.date, '%Y-%m') = '{last_closed}' group by 1)
        select t.territory, t.region, t.distributor, sc.cover_days, sc.stock_value_dp, pri.p as primary_value,
               pri.s as secondary_value, pri.sh as short_value, load.month_end_share
        from staging.territory t left join sc using (territory_id) left join pri using (territory_id)
        left join load using (territory_id) order by sc.cover_days desc""")
    loading_trend = _df(con, """
        select strftime(p.date, '%Y-%m') as month,
               sum(case when c.wd_in_month - c.wd_elapsed < 3 then p.invoice_value end) / sum(p.invoice_value) as share
        from staging.primary_sales p join staging.calendar c on c.date = p.date group by 1 order by 1""")

    audit = _df(con, """select period, category, sum(market_value) as market,
                               sum(market_value * kadam_share) / sum(market_value) as share,
                               sum(market_value * competitor_a_share) / sum(market_value) as comp_a,
                               sum(market_value * competitor_b_share) / sum(market_value) as comp_b,
                               sum(market_value * competitor_c_share) / sum(market_value) as comp_c
                        from staging.retail_audit group by all order by 1, 2""")
    audit_region = _df(con, """select region, category, kadam_share as share, market_value as market from staging.retail_audit
                               where period = (select max(period) from staging.retail_audit)""")

    plan = _df(con, f"""
        select t.territory, t.region, t.district, sum(g.target_value) as target, sum(g.ly_value) as ly,
               sum(g.target_value * g.ly_share) / nullif(sum(g.target_value), 0) as ly_share,
               sum((g.guardrail = 1)::int) as capped, sum((g.guardrail = -1)::int) as floored
        from marts.target_territory_brand g join staging.territory t using (territory_id)
        where g.month = '{next_month}' group by all order by target desc""")
    plan_brand = _df(con, f"""select brand, sum(target_value) as target, sum(ly_value) as ly, any_value(plan_growth) as plan_growth
                              from marts.target_territory_brand where month = '{next_month}' group by 1 order by 2 desc""")
    plan_sr = _df(con, f"""select count(distinct position_id) as positions,
                                  count(distinct position_id) filter (where sr_id = 'VACANT') as vacant
                           from marts.target_sr_brand where month = '{next_month}'""").iloc[0]

    data = {
        "meta": {"company": COMPANY, "as_of": as_of, "month": month, "last_closed": last_closed,
                 "next_month": next_month, "wd_elapsed": wd_elapsed, "wd_in_month": wd_in_month,
                 "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                 "note": "Synthetic data. The company, brands, people and every sales figure are invented."},
        "kpi": {**{k: (None if pd.isna(v) else float(v)) for k, v in overall.items()},
                "ytd_target": float(ytd.target), "ytd_actual": float(ytd.actual), "ytd_ly": float(ytd.ly),
                "fill_rate": float(fill), "stock_cover_days": float(cover), "active_srs": int(people),
                "territories": int(len(terr)), "distributors": int(len(terr)),
                "vacant_positions": int(vacancy.vacant), "positions": int(vacancy.total)},
        "trend": _records(trend.drop(columns="actual_mtd_only")),
        "regions": _records(regions), "areas": _records(areas), "territories": _records(terr),
        "districts": _records(districts), "brands_mtd": _records(brands_mtd),
        "territory_brand": _records(terr_brand, 0),
        "brand_month": _records(brand_month, 0), "brand_ytd": _records(brand_ytd, 0),
        "skus": _records(skus), "sku_short_month": _records(sku_short_month, 0),
        "srs": _records(srs), "payout_trend": _records(payout_trend),
        "distribution": _records(distribution), "universe": _records(universe),
        "stock": _records(stock), "loading_trend": _records(loading_trend),
        "audit": _records(audit), "audit_region": _records(audit_region),
        "plan": _records(plan), "plan_brand": _records(plan_brand),
        "plan_sr": {"positions": int(plan_sr.positions), "vacant": int(plan_sr.vacant)},
    }
    data["insights"] = insights(data)
    return data


def _cr(v: float) -> str:
    return f"BDT {v / 1e7:,.1f} crore" if abs(v) >= 1e7 else f"BDT {v / 1e5:,.1f} lakh"


def insights(d: dict) -> list[dict]:
    """Rule-based findings, written the way a sales analyst would brief the head of sales."""
    k, out = d["kpi"], []
    gap = k["required_per_day"] / k["current_per_day"] - 1
    out.append({"tone": "bad" if gap > 0.05 else "good",
                "text": f"To close {d['meta']['month']} on target, daily sales must run {gap:+.0%} versus the "
                        f"pace so far ({_cr(k['required_per_day'])} a day against {_cr(k['current_per_day'])})."})
    regs = sorted(d["regions"], key=lambda r: r["projected_achievement"])
    w, b = regs[0], regs[-1]
    out.append({"tone": "bad", "text": f"{w['region']} is projected at {w['projected_achievement']:.0%} of target, "
                                       f"the weakest region; {b['region']} leads at {b['projected_achievement']:.0%}."})
    by = sorted(d["brand_ytd"], key=lambda r: r["actual"] / r["ly"] - 1)
    fast, slow = by[-1], by[0]
    out.append({"tone": "good", "text": f"{fast['brand']} is the fastest-growing brand this year, "
                                        f"{fast['actual'] / fast['ly'] - 1:+.0%} on last year; "
                                        f"{slow['brand']} is the slowest at {slow['actual'] / slow['ly'] - 1:+.0%}."})
    short = sorted(d["skus"], key=lambda r: -r["s"])[0]
    out.append({"tone": "bad", "text": f"Unfilled orders cost {_cr(short['s'])} on {short['sku_name']} this year, "
                                       f"the most of any SKU (fill rate {short['fill']:.0%})."})
    lt = d["loading_trend"][-2]
    out.append({"tone": "warn", "text": f"{lt['share']:.0%} of primary sales in {lt['month']} were invoiced in the "
                                        f"last three working days: stock is being loaded to close the month."})
    hit = [r for r in d["srs"] if r["achievement"] >= 1]
    out.append({"tone": "neutral", "text": f"{len(hit)} of {len(d['srs'])} SRs hit their {d['meta']['last_closed']} "
                                           f"target; incentives paid {_cr(sum(r['payout_bdt'] for r in d['srs']))}."})
    return out


def write(con: duckdb.DuckDBPyConnection, settings: Settings) -> None:
    data = build(con, settings)
    settings.dashboard_data.mkdir(parents=True, exist_ok=True)
    (settings.dashboard_data / "dashboard.json").write_text(json.dumps(data, separators=(",", ":")), "utf8")
    shutil.copy(REFERENCE / "bd_districts.geojson", settings.dashboard_data / "bd_districts.geojson")
    size = (settings.dashboard_data / "dashboard.json").stat().st_size
    print(f"dashboard data written ({size / 1e6:.1f} MB) -> {settings.dashboard_data}")
