"""Build the warehouse: staging -> sales marts -> targets -> performance marts -> checks."""

from __future__ import annotations

import time
from pathlib import Path

import duckdb

from . import checks, targets
from .config import ROOT, Settings

SQL = ROOT / "sql"


def run_sql(con: duckdb.DuckDBPyConnection, path: Path, settings: Settings) -> None:
    text = path.read_text("utf8").format(raw=settings.out_dir.as_posix(), as_of=settings.as_of.isoformat())
    for stmt in (s.strip() for s in text.split(";")):
        if stmt and not all(line.strip().startswith("--") or not line.strip() for line in stmt.splitlines()):
            con.execute(stmt)


def run(settings: Settings | None = None, quiet: bool = False) -> duckdb.DuckDBPyConnection:
    settings = settings or Settings()
    t0 = time.time()
    settings.warehouse.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(settings.warehouse))
    con.execute("create schema if not exists staging; create schema if not exists marts;")
    for f in sorted((SQL / "staging").glob("*.sql")):
        run_sql(con, f, settings)
    run_sql(con, SQL / "marts" / "01_sales.sql", settings)
    targets.build(con, settings)
    run_sql(con, SQL / "marts" / "02_performance.sql", settings)
    results = checks.run(con)
    if not quiet:
        for r in results:
            print(f"  {'PASS' if r.ok else 'FAIL'}  {r.name}: {r.detail}")
        print(f"warehouse built in {time.time() - t0:.0f}s -> {settings.warehouse}")
    failed = [r for r in results if not r.ok]
    if failed:
        raise SystemExit(f"{len(failed)} data check(s) failed")
    return con
