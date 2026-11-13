"""Command line: python -m fmcg_bd [generate|build|export|all]"""

from __future__ import annotations

import sys

import duckdb

from . import build, export, generate
from .config import Settings


def main(argv: list[str]) -> int:
    step = argv[0] if argv else "all"
    settings = Settings.from_env()
    if step in ("generate", "all"):
        generate.run(settings)
    if step in ("build", "all"):
        con = build.run(settings)
        con.close()
    if step in ("export", "all"):
        con = duckdb.connect(str(settings.warehouse), read_only=True)
        export.write(con, settings)
        con.close()
    if step not in ("generate", "build", "export", "all"):
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
