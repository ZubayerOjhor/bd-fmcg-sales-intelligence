from datetime import date

import numpy as np
import pytest

from fmcg_bd.config import DISTRIBUTOR_MARGIN, RETAILER_MARGIN, Settings
from fmcg_bd.generate import catalog
from fmcg_bd.generate.sales import allocate
from fmcg_bd.targets import apply_guardrails, round_to


def test_allocate_parts_add_up_exactly():
    rng = np.random.default_rng(1)
    total = np.array([1_000_003, 7, 0, 55])
    group = np.array([0, 0, 0, 1, 1, 3, 3, 3])
    weights = rng.random(len(group))
    parts, unallocated = allocate(total, weights, group)
    assert np.bincount(group, parts, minlength=4).tolist()[:2] == [1_000_003, 7]
    assert parts[group == 3].sum() == 55
    assert unallocated.tolist() == [0, 0, 0, 0]
    assert (parts >= 0).all()


def test_allocate_group_without_weight_is_reported():
    parts, unallocated = allocate(np.array([10, 20]), np.array([1.0, 0.0]), np.array([0, 1]))
    assert parts.tolist() == [10, 0]
    assert unallocated.tolist() == [0, 20]


def test_allocate_follows_weights():
    parts, _ = allocate(np.array([1000]), np.array([1.0, 3.0]), np.array([0, 0]))
    assert parts.tolist() == [250, 750]


@pytest.mark.parametrize("step", [100, 1000])
def test_round_to_keeps_the_total(step):
    v = np.array([123456.7, 98765.4, 5555.5, 1.2])
    out = round_to(v, step, total=v.sum())
    assert out.sum() == round(v.sum() / step) * step
    assert all(x % step == 0 for x in out)


def test_guardrails_hold_the_band_and_the_total():
    ly = np.array([100.0, 100.0, 100.0, 0.0])
    raw = np.array([200.0, 50.0, 100.0, 50.0])  # one far above, one far below, one new territory
    out, flag = apply_guardrails(raw, ly, floor=-0.05, cap=0.30)
    assert out.sum() == pytest.approx(raw.sum())
    assert out[0] == pytest.approx(130.0) and flag[0] == 1
    assert out[1] == pytest.approx(95.0) and flag[1] == -1
    assert flag[3] == 0  # no history: never clipped


def test_calendar_marks_fridays_and_eid():
    cal = catalog.calendar(Settings(start=date(2026, 3, 1), as_of=date(2026, 3, 31)))
    fri = cal[cal.weekday == "Fri"]
    assert not fri.is_working_day.any()
    eid = cal[cal.date == date(2026, 3, 21)].iloc[0]
    assert eid.is_holiday and eid.eid == "Eid ul-Fitr"


def test_price_list_margins_and_changes():
    prod = catalog.products()
    prices = catalog.price_list(prod, Settings())
    row = prices.iloc[0]
    assert row.tp == pytest.approx(row.mrp * (1 - RETAILER_MARGIN), abs=0.01)
    assert row.dp == pytest.approx(row.tp * (1 - DISTRIBUTOR_MARGIN), abs=0.01)
    jhak = prices[prices.sku_id.str.startswith("JHA")]
    assert len(jhak) == 2 * prod.brand.eq("Jhakjhak").sum()  # one price change, two periods each


def test_catalogue_is_unique():
    prod = catalog.products()
    assert prod.sku_id.is_unique
    assert prod.groupby("brand").mix_weight.sum().between(0.9, 1.25).all()
