"""Data checks that must pass before anything is published. Each returns pass/fail and a detail."""

from __future__ import annotations

from dataclasses import dataclass

import duckdb


@dataclass
class Result:
    name: str
    ok: bool
    detail: str


def _one(con, sql):
    return con.execute(sql).fetchone()


def run(con: duckdb.DuckDBPyConnection) -> list[Result]:
    out = []

    dup = _one(con, "select count(*) - count(distinct sku_id) from staging.product")[0] + \
        _one(con, "select count(*) - count(distinct territory_id) from staging.territory")[0]
    out.append(Result("unique keys", dup == 0, f"{dup} duplicate SKU or territory keys"))

    bad_price = _one(con, """select count(*) from staging.secondary
                             where abs(delivered_value - delivered_units * tp) > 0.011""")[0]
    out.append(Result("value = units x trade price", bad_price == 0, f"{bad_price:,} rows off"))

    over = _one(con, "select count(*) from staging.secondary where delivered_units > ordered_units")[0]
    out.append(Result("delivered never exceeds ordered", over == 0, f"{over:,} rows"))

    neg = _one(con, "select count(*) from staging.stock where closing_units < 0")[0]
    out.append(Result("no negative distributor stock", neg == 0, f"{neg:,} rows"))

    gap = _one(con, """
        with sr as (select date, territory_id, brand, sum(value) v from staging.sr_sales group by all)
        select coalesce(max(abs(d.secondary_value - coalesce(sr.v, 0))), 0), count(*)
        from marts.territory_brand_day d left join sr using (date, territory_id, brand)""")
    out.append(Result("SR sales tie to distributor sales", gap[0] < 0.05,
                      f"largest gap BDT {gap[0]:.3f} across {gap[1]:,} territory-brand-days"))

    tie = _one(con, """
        with s as (select month, territory_id, brand, sum(target_value) v from marts.target_sr_brand group by all)
        select coalesce(max(abs(t.target_value - s.v)), 0) from marts.target_territory_brand t join s using (month, territory_id, brand)""")[0]
    out.append(Result("SR targets add up to territory targets", tie < 0.5, f"largest gap BDT {tie:,.2f}"))

    band = _one(con, """select count(*) from marts.target_territory_brand
                        where ly_value > 0 and (target_value < ly_value * 0.95 - 1000
                                                or target_value > ly_value * 1.30 + 1000)""")[0]
    out.append(Result("targets inside the -5% / +30% guardrail", band == 0, f"{band:,} outside"))

    grid = _one(con, """select count(*) from (select month, count(*) n from marts.target_territory_brand group by 1)
                        where n <> (select count(*) from staging.territory) *
                                 (select count(distinct brand) from staging.product)""")[0]
    out.append(Result("every territory has a target for every brand", grid == 0, f"{grid} incomplete months"))
    return out
