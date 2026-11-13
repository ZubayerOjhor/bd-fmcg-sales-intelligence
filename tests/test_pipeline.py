"""End to end on a small slice: one region, 15 months. Generates, builds, checks and exports."""

import json
from datetime import date

import duckdb
import pytest

from fmcg_bd import build, checks, export, generate
from fmcg_bd.config import Settings


@pytest.fixture(scope="module")
def small(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("run")
    s = Settings(start=date(2024, 1, 1), as_of=date(2025, 3, 18), out_dir=tmp / "raw",
                 warehouse=tmp / "w.duckdb", dashboard_data=tmp / "dash", regions=("North-East",))
    generate.run(s, quiet=True)
    con = build.run(s, quiet=True)
    yield s, con
    con.close()


def test_every_data_check_passes(small):
    _, con = small
    failed = [r for r in checks.run(con) if not r.ok]
    assert not failed, failed


def test_targets_roll_up_to_the_plan(small):
    _, con = small
    # Each brand-month adds up across territories, and territories add up across SRs.
    n = con.execute("select count(distinct month) from marts.target_territory_brand").fetchone()[0]
    assert n == 4  # Jan to Apr 2025: targets run one month past the as-of date
    gap = con.execute("""
        with s as (select month, brand, sum(target_value) v from marts.target_sr_brand group by all),
             t as (select month, brand, sum(target_value) v from marts.target_territory_brand group by all)
        select max(abs(s.v - t.v)) from s join t using (month, brand)""").fetchone()[0]
    assert gap < 1


def test_month_to_date_uses_working_days(small):
    s, con = small
    wd = con.execute("select max(wd_elapsed), max(wd_in_month) from marts.mtd_territory_brand").fetchone()
    assert 0 < wd[0] < wd[1] <= 27


def test_export_has_every_section(small):
    s, con = small
    export.write(con, s)
    d = json.loads((s.dashboard_data / "dashboard.json").read_text("utf8"))
    for key in ("meta", "kpi", "trend", "regions", "territories", "districts", "srs", "plan", "insights"):
        assert d[key], key
    assert d["meta"]["as_of"] == "2025-03-18"
    assert len(d["insights"]) >= 5
    assert (s.dashboard_data / "bd_districts.geojson").exists()


def test_raw_tables_are_consistent(small):
    s, _ = small
    con = duckdb.connect()
    raw = s.out_dir.as_posix()
    sec = con.execute(f"select sum(delivered_value) from '{raw}/dms_secondary_sales.parquet'").fetchone()[0]
    sr = con.execute(f"select sum(value) from '{raw}/dms_sr_sales.parquet'").fetchone()[0]
    assert sr == pytest.approx(sec, rel=1e-9)
