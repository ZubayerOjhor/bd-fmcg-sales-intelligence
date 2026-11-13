"""The sales organisation: regions, areas, territories, distributors and the field force."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from ..config import REFERENCE, REGION_AFFLUENCE, Settings, region_for

FIRST = ["Rakib", "Sabbir", "Tanvir", "Mahmud", "Arif", "Jahid", "Rasel", "Shakil", "Fahim", "Imran",
         "Nayeem", "Sohel", "Mamun", "Rubel", "Masud", "Kamrul", "Habib", "Shafiq", "Asif", "Riyad",
         "Tuhin", "Sajib", "Milon", "Babul", "Shimul", "Liton", "Nasir", "Faruk", "Monir", "Delwar",
         "Polash", "Ripon", "Sumon", "Jewel", "Shahin", "Nusrat", "Sharmin", "Tania", "Farhana", "Mitu",
         "Anik", "Pritom", "Joy", "Dipu", "Robin", "Selim", "Kawsar", "Rana", "Hasib", "Tamim"]
LAST = ["Hossain", "Rahman", "Islam", "Ahmed", "Uddin", "Alam", "Chowdhury", "Sarker", "Mia", "Khan",
        "Kabir", "Haque", "Karim", "Molla", "Sheikh", "Biswas", "Das", "Roy", "Paul", "Saha"]
TRADE_NAMES = ["Enterprise", "Traders", "Distribution", "Corporation", "& Sons", "Agency", "Store"]

PEOPLE_PER_TERRITORY = 1.45e6  # one territory per this many people (at least one per district)
PEOPLE_PER_SR = 260e3          # field force density, adjusted by purchasing power


def districts() -> pd.DataFrame:
    d = pd.read_csv(REFERENCE / "bd_districts.csv")
    d["region"] = [region_for(v, n) for v, n in zip(d.division, d.district)]
    return d


def _kmeans(xy: np.ndarray, w: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    """Weighted k-means on district centroids; deterministic for a given generator."""
    if k <= 1:
        return np.zeros(len(xy), dtype=int)
    centres = xy[np.argsort(-w)[:k]].copy()
    for _ in range(50):
        lab = np.argmin(((xy[:, None, :] - centres[None]) ** 2).sum(-1), axis=1)
        new = np.array([np.average(xy[lab == j], axis=0, weights=w[lab == j]) if (lab == j).any()
                        else centres[j] for j in range(k)])
        if np.allclose(new, centres):
            break
        centres = new
    return lab


def _name(rng: np.random.Generator) -> str:
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def build(settings: Settings, rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    d = districts()
    if settings.regions:
        d = d[d.region.isin(settings.regions)].reset_index(drop=True)

    # Areas: cluster districts inside each region, about five territories per area.
    d["n_territories"] = np.maximum(1, np.round(d.population_2022 / PEOPLE_PER_TERRITORY)).astype(int)
    area_rows = []
    for region, g in d.groupby("region", sort=True):
        k = max(2, round(g.n_territories.sum() / 5))
        lab = _kmeans(g[["lat", "lon"]].to_numpy(), g.population_2022.to_numpy(float), k, rng)
        # Name each area after its largest district.
        for j in sorted(set(lab)):
            members = g[lab == j]
            hub = members.sort_values("population_2022").district.iloc[-1]
            area_rows.append({"region": region, "area": f"{hub} Area", "districts": list(members.district)})
    areas = pd.DataFrame(area_rows)
    areas.insert(0, "area_id", [f"A{i + 1:02d}" for i in range(len(areas))])
    district_area = {dist: a.area_id for a in areas.itertuples() for dist in a.districts}

    # Territories, one distributor each.
    terr = []
    for r in d.sort_values(["region", "district"]).itertuples():
        n = r.n_territories
        for i in range(n):
            suffix = "" if n == 1 else f" {i + 1}"
            terr.append({
                "district": r.district, "division": r.division, "region": r.region,
                "area_id": district_area[r.district], "territory": f"{r.district}{suffix}",
                "population": int(r.population_2022 / n),
                "lat": r.lat + (rng.normal(0, 0.04) if n > 1 else 0.0),
                "lon": r.lon + (rng.normal(0, 0.04) if n > 1 else 0.0),
            })
    territories = pd.DataFrame(terr)
    territories.insert(0, "territory_id", [f"T{i + 1:03d}" for i in range(len(territories))])
    aff = territories.region.map(REGION_AFFLUENCE)
    territories["affluence"] = aff
    territories["sr_positions"] = np.clip(np.round(territories.population * aff / PEOPLE_PER_SR), 3, 8).astype(int)
    # Persistent local strength of the business (distributor quality, history, competition).
    territories["strength"] = np.round(rng.lognormal(0, 0.14, len(territories)), 3)

    distributors = pd.DataFrame({
        "distributor_id": [f"D{i + 1:03d}" for i in range(len(territories))],
        "territory_id": territories.territory_id,
        "distributor": [f"{rng.choice(LAST)} {rng.choice(TRADE_NAMES)}" for _ in range(len(territories))],
        "credit_days": rng.choice([0, 0, 0, 7, 15], len(territories)),
    })

    managers = {
        "rsm": {r: _name(rng) for r in sorted(territories.region.unique())},
        "am": {a: _name(rng) for a in areas.area_id},
        "to": {t: _name(rng) for t in territories.territory_id},
    }
    areas["area_manager"] = areas.area_id.map(managers["am"])
    areas["regional_manager"] = areas.region.map(managers["rsm"])
    territories["territory_officer"] = territories.territory_id.map(managers["to"])

    srs = _field_force(settings, territories, rng)
    return {
        "dim_area": areas.drop(columns="districts"),
        "dim_territory": territories,
        "dim_distributor": distributors,
        "dim_sr": srs,
    }


def _field_force(settings: Settings, territories: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """SR positions with turnover: people leave, the beat stays empty for a while, a new SR joins."""
    months = pd.period_range(settings.start, settings.as_of, freq="M")
    rows, n = [], 0
    for t in territories.itertuples():
        for p in range(t.sr_positions):
            pos = f"{t.territory_id}-P{p + 1}"
            join = settings.start - pd.Timedelta(days=int(rng.integers(120, 2500)))
            quality = float(np.clip(rng.lognormal(0, 0.13), 0.7, 1.4))
            route = int(rng.integers(30, 43))
            i = 0
            while i < len(months):
                if rng.random() < 0.022 and i > 0:  # leaves at the end of month i-1
                    leave = months[i - 1].end_time.date()
                    n += 1
                    rows.append(_sr(n, pos, t, join, leave, quality, route, rng))
                    gap = 1 if rng.random() < 0.6 else 2
                    i += gap
                    if i >= len(months):
                        break
                    join = months[i].start_time.date() + pd.Timedelta(days=int(rng.integers(0, 10)))
                    quality = float(np.clip(rng.lognormal(-0.03, 0.15), 0.65, 1.4))
                    route = int(rng.integers(30, 43))
                i += 1
            n += 1
            rows.append(_sr(n, pos, t, join, None, quality, route, rng))
    return pd.DataFrame(rows)


def _sr(n, pos, t, join, leave, quality, route, rng) -> dict:
    return {
        "sr_id": f"SR{n:04d}", "position_id": pos, "territory_id": t.territory_id, "sr_name": _name(rng),
        "join_date": pd.Timestamp(join).date(), "leave_date": None if leave is None else pd.Timestamp(leave).date(),
        "quality": round(quality, 3), "route_outlets": route,
    }


def is_active(srs: pd.DataFrame, day: date) -> np.ndarray:
    leave = pd.to_datetime(srs.leave_date).dt.date
    return ((srs.join_date <= day) & (leave.isna() | (leave >= day))).to_numpy()
