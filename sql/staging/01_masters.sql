-- Masters: one clean row per thing, with the hierarchy flattened onto the territory.

create or replace table staging.territory as
select t.territory_id, t.territory, t.district, t.division, t.region, a.area_id, a.area,
       t.population, t.affluence, t.sr_positions, t.lat, t.lon,
       d.distributor_id, d.distributor, d.credit_days,
       t.territory_officer, a.area_manager, a.regional_manager
from read_parquet('{raw}/dim_territory.parquet') t
join read_parquet('{raw}/dim_area.parquet') a using (area_id)
join read_parquet('{raw}/dim_distributor.parquet') d using (territory_id);

create or replace table staging.product as
select sku_id, sku_name, brand, category, pack, mrp_list, case_size,
       cast(launch_date as date) as launch_date
from read_parquet('{raw}/dim_product.parquet');

create or replace table staging.price_list as
select sku_id, cast(valid_from as date) as valid_from,
       coalesce(cast(valid_to as date), date '2099-12-31') as valid_to, mrp, tp, dp
from read_parquet('{raw}/price_list.parquet');

create or replace table staging.sr as
select sr_id, position_id, territory_id, sr_name, cast(join_date as date) as join_date,
       cast(leave_date as date) as leave_date, route_outlets
from read_parquet('{raw}/dim_sr.parquet');

-- Trading calendar with the working-day position inside each month (for pro-rata targets).
create or replace table staging.calendar as
select cast(date as date) as date, weekday, is_friday, is_holiday, is_working_day, eid,
       month,
       sum(case when is_working_day then 1 else 0 end) over (partition by month order by date) as wd_elapsed,
       sum(case when is_working_day then 1 else 0 end) over (partition by month) as wd_in_month
from read_parquet('{raw}/dim_date.parquet');
