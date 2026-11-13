-- Transactions: typed, keyed to the territory, priced from the price list in force that day.

create or replace table staging.secondary as
select cast(s.delivery_date as date) as date, t.territory_id, s.sku_id,
       s.ordered_units, s.delivered_units, s.ordered_units - s.delivered_units as short_units,
       s.delivered_value, p.tp, p.dp,
       (s.ordered_units - s.delivered_units) * p.tp as short_value
from read_parquet('{raw}/dms_secondary_sales.parquet') s
join staging.territory t using (distributor_id)
join staging.price_list p
  on p.sku_id = s.sku_id and cast(s.delivery_date as date) between p.valid_from and p.valid_to;

create or replace table staging.primary_sales as
select i.invoice_no, cast(i.invoice_date as date) as date, t.territory_id, i.sku_id, i.units,
       i.invoice_value, cast(i.invoice_date as date) + cast(i.lead_days as integer) as delivery_date
from read_parquet('{raw}/erp_primary_invoices.parquet') i
join staging.territory t using (distributor_id);

create or replace table staging.sr_sales as
select cast(sales_date as date) as date, coalesce(sr_id, 'VACANT') as sr_id, territory_id, brand,
       units, value
from read_parquet('{raw}/dms_sr_sales.parquet');

create or replace table staging.sr_calls as
select cast(visit_date as date) as date, sr_id, scheduled_calls, visited, productive_calls, lines_sold
from read_parquet('{raw}/dms_sr_calls.parquet');

create or replace table staging.stock as
select cast(s.count_date as date) as date, t.territory_id, s.sku_id, s.closing_units,
       s.closing_units * p.dp as closing_value_dp
from read_parquet('{raw}/dms_month_end_stock.parquet') s
join staging.territory t using (distributor_id)
join staging.price_list p
  on p.sku_id = s.sku_id and cast(s.count_date as date) between p.valid_from and p.valid_to;

create or replace table staging.outlet_universe as
select * from read_parquet('{raw}/outlet_universe.parquet');

create or replace table staging.coverage as
select * from read_parquet('{raw}/outlet_coverage.parquet');

create or replace table staging.retail_audit as
select * from read_parquet('{raw}/retail_audit.parquet');
