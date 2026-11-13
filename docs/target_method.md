# How targets are set

Targets for month M are issued on the 25th of M-1. At that point the latest fully closed month is M-2, so "recent" always means the three months M-4 to M-2. The code is in [`src/fmcg_bd/targets.py`](../src/fmcg_bd/targets.py).

## 1. Annual plan, by brand

```
plan(brand, Y) = actual(brand, Y-1) x (1 + growth(brand, Y))
growth(brand, Y) = company plan growth + 0.5 x (brand growth last year - company growth last year), at least 3%
```

The company plan growth is a stretch above the real trend (11% for 2025, 13% for 2026). Brands that outgrew the company last year are asked for more, and slower brands for less, so one brand doesn't carry the whole gap.

## 2. Monthly phasing

Last year's monthly shape for the brand, corrected for working days:

```
weight(m) = actual(brand, m, Y-1) x working_days(m, Y) / working_days(m, Y-1)
target(brand, m) = plan(brand, Y) x weight(m) / sum of weights
```

Working days exclude Fridays, the Eid holidays and national holidays. One known limitation is that Eid moves about 11 days earlier each year. When the pre-Eid rush crosses a month boundary, last year's shape puts it in the wrong month. You can see this in the hit rate on the Field force tab.

## 3. Territory split

Each territory's share of the brand-month target blends three views:

| Weight | View | Why |
|---|---|---|
| 40% | Share of the same month last year | Seasonality and local festivals |
| 40% | Share of the latest three closed months | Momentum: new distributors, new SRs, competition |
| 20% | Share of potential: population x purchasing power | Pulls under-penetrated territories up over time |

## 4. Guardrails

No territory gets less than its own last year -5%, or more than +30%. The engine clips each territory to its band and moves the difference to the territories still inside the band, in proportion to their size. It repeats until nothing moves. Territories with no history are never clipped.

## 5. Rounding that still adds up

Territory targets are rounded to BDT 1,000 and SR targets to BDT 100 using the largest-remainder method. The rounded parts add up exactly to the total above them, so a manager who sums the SR sheet gets the territory number, and the territories add up to the plan.

## 6. SR split

Each SR position gets:

```
weight = 0.7 x median monthly share of the territory (latest three closed months) + 0.3 x share of route outlets
weight = max(weight, 0.6 x share of route outlets)
```

The median and the floor stop a beat that was empty, or had a new SR ramping up, from getting a tiny target. A position empty on the 1st is held as `VACANT` for the territory officer to cover.

## Tracking during the month

| Measure | Definition |
|---|---|
| Time gone | Working days elapsed / working days in the month |
| Achievement | Month-to-date sales / monthly target |
| Projected | Month-to-date sales / working days elapsed x working days in the month |
| Required per day | (Target - month-to-date sales) / working days left |
| Current per day | Month-to-date sales / working days elapsed |

## Incentive

Paid monthly on value achievement across all brands, with a base of BDT 5,000:

| Achievement | Payout |
|---|---|
| Below 80% | 0 |
| 80% to 100% | 50% to 100% of the base, linear |
| Above 100% | +1.5% of the base per point, capped at 130% |
| Strike rate 55% or more | +10% of the base |
