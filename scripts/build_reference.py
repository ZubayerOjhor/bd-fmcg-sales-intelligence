"""Build data/reference/ from three public sources.

Run once; the outputs are committed so the project works offline.

    python scripts/build_reference.py RAW_DIR

RAW_DIR must contain:
  districts.json, divisions.json   github.com/nuhil/bangladesh-geocode (district centroids, Bangla names)
  wiki_districts.json              Wikipedia "Districts of Bangladesh" wikitext via the MediaWiki API
                                   (area from the 2011 census, population from the 2022 census, BBS)
  adm2_simplified.geojson          geoBoundaries BGD ADM2, simplified (BBS / OCHA, CC BY 3.0 IGO)
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "reference"

# One spelling per district, following the 2018 official romanisation.
ALIASES = {
    "comilla": "cumilla", "chittagong": "chattogram", "bogra": "bogura", "jessore": "jashore",
    "barisal": "barishal", "chapai nawabganj": "chapainawabganj", "nawabganj": "chapainawabganj",
    "chapai nababganj": "chapainawabganj", "chapainababganj": "chapainawabganj", "maulvibazar": "moulvibazar", "netrakona": "netrokona",
    "jhalakati": "jhalokati", "jhalokathi": "jhalokati", "khagrachari": "khagrachhari",
    "brahamanbaria": "brahmanbaria", "cox's bazar": "coxsbazar", "coxs bazar": "coxsbazar",
    "cox’s bazar": "coxsbazar", "parbattya chattagram": "rangamati", "rangamati": "rangamati",
    "kushtia": "kushtia", "sirajgonj": "sirajganj", "narshingdi": "narsingdi",
    "munshigonj": "munshiganj", "gopalgonj": "gopalganj", "habiganj": "habiganj",
    "hobiganj": "habiganj", "panchagarh": "panchagarh", "panchagar": "panchagarh",
    "nilphamari zila": "nilphamari", "lakshmipur": "lakshmipur", "laxmipur": "lakshmipur",
    "patuakhali": "patuakhali", "pirojpur": "pirojpur", "thakurgaon": "thakurgaon",
    "chuadanga": "chuadanga", "jhenaidah": "jhenaidah", "jhenaida": "jhenaidah",
    "narail": "narail", "satkhira": "satkhira", "meherpur": "meherpur", "magura": "magura",
    "sherpur": "sherpur", "jamalpur": "jamalpur", "mymensingh": "mymensingh",
}


def key(name: str) -> str:
    n = re.sub(r"\s+district.*$", "", name.strip().lower())
    n = n.replace("-", " ").strip()
    n = ALIASES.get(n, n)
    return n.replace(" ", "").replace("'", "").replace("’", "")


def wiki_rows(wikitext: str) -> dict[str, dict]:
    table = wikitext[wikitext.find("{|"): wikitext.find("|}")]
    out: dict[str, dict] = {}
    for row in table.split("|-")[1:]:
        cells = [c.strip() for c in re.split(r"\n\|", "\n" + row.strip()) if c.strip()]
        cells = [re.sub(r'^(rowspan="\d+"\s*\||style="[^"]*"\s*\|)', "", c).strip() for c in cells]
        idx = [i for i, c in enumerate(cells) if c.startswith("[[") and "File:" not in c]
        if not idx:
            continue
        i = idx[-1]
        district = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", lambda m: m.group(1), cells[i])
        # After the district: map, established year, area (km2), population (2022), density, ...
        after = [c for c in cells[i + 1:] if "File:" not in c]
        area, pop = (int(re.sub(r"[^\d]", "", c)) for c in after[1:3])
        out[key(district)] = {"population_2022": pop, "area_km2_2011": area}
    return out


def main(raw: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    divs = {d["id"]: d["name"] for d in json.loads((raw / "divisions.json").read_text("utf8"))[2]["data"]}
    geo = json.loads((raw / "districts.json").read_text("utf8"))[2]["data"]
    wiki = wiki_rows(json.loads((raw / "wiki_districts.json").read_text("utf8"))["parse"]["wikitext"]["*"])

    rows = []
    for d in geo:
        k = key(d["name"])
        w = wiki.get(k)
        if w is None:
            raise SystemExit(f"no census row for {d['name']} ({k}); add an alias")
        rows.append({
            "district_id": int(d["id"]), "district": d["name"], "district_bn": d["bn_name"],
            "division": divs[d["division_id"]], "lat": round(float(d["lat"]), 4),
            "lon": round(float(d["lon"]), 4), "geo_key": k, **w,
        })
    if len(rows) != 64:
        raise SystemExit(f"expected 64 districts, got {len(rows)}")
    rows.sort(key=lambda r: (r["division"], r["district"]))
    with (OUT / "bd_districts.csv").open("w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # Boundaries: keep 3 decimals (about 100 m) so the dashboard map stays small.
    g = json.loads((raw / "adm2_simplified.geojson").read_text("utf8"))
    names = {r["geo_key"]: r["district"] for r in rows}

    def rnd(c):
        return [rnd(x) for x in c] if isinstance(c[0], list) else [round(c[0], 3), round(c[1], 3)]

    feats = []
    for ft in g["features"]:
        k = key(ft["properties"]["shapeName"])
        if k not in names:
            raise SystemExit(f"boundary {ft['properties']['shapeName']} ({k}) matches no district")
        feats.append({"type": "Feature", "properties": {"name": names[k]},
                      "geometry": {"type": ft["geometry"]["type"], "coordinates": rnd(ft["geometry"]["coordinates"])}})
    (OUT / "bd_districts.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")), "utf8")
    print(f"64 districts, population {sum(r['population_2022'] for r in rows):,}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
