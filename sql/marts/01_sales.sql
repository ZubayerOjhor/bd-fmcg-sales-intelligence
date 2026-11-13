-- Sales marts: the grain everyone reads from. Targets are built on top of these.

-- Territory x brand x month: secondary, primary and lost sales in one place.
create or replace table marts.territory_brand_month as
with sec as (
    select strftime(s.date, '%Y-%m') as month, s.territory_id, p.brand,
           sum(s.delivered_value) as secondary_value, sum(s.delivered_units) as secondary_units,
           sum(s.short_value) as short_value, sum(s.ordered_units) as ordered_units
    from staging.secondary s join staging.product p using (sku_id)
    group by all
), pri as (
    select strftime(i.date, '%Y-%m') as month, i.territory_id, p.brand,
           sum(i.invoice_value) as primary_value
    from staging.primary_sales i join staging.product p using (sku_id)
    group by all
)
select coalesce(sec.month, pri.month) as month, coalesce(sec.territory_id, pri.territory_id) as territory_id,
       coalesce(sec.brand, pri.brand) as brand,
       coalesce(secondary_value, 0) as secondary_value, coalesce(secondary_units, 0) as secondary_units,
       coalesce(short_value, 0) as short_value, coalesce(ordered_units, 0) as ordered_units,
       coalesce(primary_value, 0) as primary_value
from sec full join pri using (month, territory_id, brand);

-- Daily secondary by territory and brand (for month-to-date tracking).
create or replace table marts.territory_brand_day as
select s.date, s.territory_id, p.brand, sum(s.delivered_value) as secondary_value,
       sum(s.short_value) as short_value
from staging.secondary s join staging.product p using (sku_id)
group by all;

-- SKU x month nationally, for mix and pack-size analysis.
create or replace table marts.sku_month as
select strftime(s.date, '%Y-%m') as month, s.sku_id, p.sku_name, p.brand, p.category, p.pack,
       sum(s.delivered_value) as secondary_value, sum(s.delivered_units) as units,
       sum(s.short_value) as short_value,
       sum(s.delivered_units) / nullif(sum(s.ordered_units), 0) as fill_rate
from staging.secondary s join staging.product p using (sku_id)
group by all;

-- SR x month: sales by brand and the calls behind them.
create or replace table marts.sr_brand_month as
select strftime(date, '%Y-%m') as month, sr_id, territory_id, brand,
       sum(value) as secondary_value, sum(units) as units
from staging.sr_sales
group by all;

create or replace table marts.sr_month_calls as
select strftime(c.date, '%Y-%m') as month, c.sr_id, any_value(s.territory_id) as territory_id,
       count(*) as days_worked, sum(scheduled_calls) as scheduled_calls, sum(visited) as visited,
       sum(productive_calls) as productive_calls, sum(lines_sold) as lines_sold
from staging.sr_calls c join staging.sr s using (sr_id)
group by all;

-- Distributor stock at month end against the next 30 days of secondary sales.
create or replace table marts.stock_cover as
with stock as (
    select date, territory_id, sum(closing_value_dp) as stock_value_dp
    from staging.stock group by all
), fwd as (
    select st.date, st.territory_id,
           sum(s.delivered_units * s.dp) / count(distinct case when c.is_working_day then s.date end) as daily_sales_dp
    from stock st
    join staging.secondary s on s.territory_id = st.territory_id
         and s.date > st.date and s.date <= st.date + interval 30 day
    join staging.calendar c on c.date = s.date
    group by all
)
select st.date, strftime(st.date, '%Y-%m') as month, st.territory_id, st.stock_value_dp,
       f.daily_sales_dp, st.stock_value_dp / nullif(f.daily_sales_dp, 0) as cover_days
from stock st left join fwd f using (date, territory_id);
