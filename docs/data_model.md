# Data model and KPI definitions

## Source tables (`data/raw/`, written by the simulator)

| Table | System | Grain | Notes |
|---|---|---|---|
| `erp_primary_invoices` | ERP | invoice x SKU | Company to distributor, at distributor price (DP) |
| `dms_secondary_sales` | DMS | day x distributor x SKU | Distributor to shops: ordered vs delivered units, value at trade price (TP) |
| `dms_sr_sales` | DMS | day x SR x brand | The same sales by SR (memo summary). `sr_id` is empty when no SR covered the beat |
| `dms_sr_calls` | DMS | day x SR | Scheduled, visited and productive calls, lines sold |
| `dms_month_end_stock` | DMS | month end x distributor x SKU | Physical stock count |
| `outlet_universe` | Census | territory x channel | Grocery, pharmacy, cosmetics, wholesale, modern trade |
| `outlet_coverage` | SFA | month x territory x brand | Outlets on routes, outlets that bought |
| `retail_audit` | Audit agency | two-month period x region x category | Market value, own and competitor shares |
| `dim_*`, `price_list` | Masters | | Hierarchy, SKUs, price history (slowly changing), calendar |

## Warehouse (`data/warehouse.duckdb`)

**`staging`:** one clean table per source. Types are fixed, every row is keyed to its territory, and values are priced from the price list in force that day.

**`marts`:**

| Table | Grain | Used for |
|---|---|---|
| `territory_brand_month` | month x territory x brand | Secondary, primary, unfilled orders. The target engine reads this |
| `territory_brand_day` | day x territory x brand | Month-to-date tracking |
| `sku_month` | month x SKU | Mix, growth, fill rate |
| `sr_brand_month`, `sr_month_calls` | month x SR | SR performance |
| `stock_cover` | month end x territory | Stock against the next 30 days of sales |
| `target_territory_brand` | month x territory x brand | Targets with every input kept: last year, shares, guardrail flag, plan growth |
| `target_sr_brand` | month x position x brand | SR targets |
| `achievement_territory_brand` | month x territory x brand | Target vs actual |
| `sr_scorecard` | month x SR | Achievement, strike rate, lines per call, incentive |
| `mtd_territory_brand` | territory x brand, as of a day | Time gone, projection, required run rate |

## KPI definitions

| KPI | Definition |
|---|---|
| Secondary sales | Value delivered by distributors to shops, at trade price |
| Primary sales | Value invoiced by the company to distributors, at distributor price |
| Fill rate | Delivered units / ordered units |
| Lost to short supply | (Ordered - delivered units) x trade price |
| Achievement | Actual / target |
| Projected achievement | Run-rate projection of the month / target |
| Strike rate | Productive calls / outlets visited |
| Lines per call | SKU lines sold / productive calls |
| Effective coverage | Outlets that bought the brand in the month / outlets on SR routes |
| Route reach | Outlets on SR routes / all outlets in the universe |
| Stock cover | Month-end stock at DP / average daily secondary sales at DP over the next 30 days |
| Month-end loading | Share of the month's primary sales invoiced in its last three working days |
| Value share | Own sales / category market value, from the retail audit |
