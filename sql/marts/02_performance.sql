-- Performance marts: targets against actuals, built after the target engine has run.

create or replace table marts.achievement_territory_brand as
select t.month, t.territory_id, t.brand, t.target_value,
       coalesce(a.secondary_value, 0) as actual_value, t.ly_value, t.guardrail,
       coalesce(a.secondary_value, 0) / nullif(t.target_value, 0) as achievement,
       coalesce(a.short_value, 0) as short_value, coalesce(a.primary_value, 0) as primary_value
from marts.target_territory_brand t
left join marts.territory_brand_month a using (month, territory_id, brand);

-- SR scorecard and incentive. Value achievement across all brands drives the payout:
--   below 80%: nothing, 80-100%: 50% to 100% of the base, above 100%: +1.5% per point up to 130%.
--   Productive calls of 55% or more add 10% of the base. Base: BDT 5,000 a month.
create or replace table marts.sr_scorecard as
with tgt as (
    select month, sr_id, any_value(territory_id) as territory_id, sum(target_value) as target_value
    from marts.target_sr_brand where sr_id <> 'VACANT' group by all
), act as (
    select month, sr_id, sum(secondary_value) as actual_value from marts.sr_brand_month group by all
), base as (
    select tgt.*, coalesce(act.actual_value, 0) as actual_value,
           coalesce(act.actual_value, 0) / nullif(tgt.target_value, 0) as achievement,
           c.days_worked, c.scheduled_calls, c.visited, c.productive_calls, c.lines_sold,
           c.productive_calls / nullif(c.visited, 0) as strike_rate,
           c.lines_sold / nullif(c.productive_calls, 0) as lines_per_call
    from tgt left join act using (month, sr_id) left join marts.sr_month_calls c using (month, sr_id)
)
select base.*,
       case when achievement < 0.8 then 0
            when achievement < 1.0 then 0.5 + (achievement - 0.8) / 0.2 * 0.5
            else least(1.0 + (achievement - 1.0) * 1.5, 1.3) end
       + case when strike_rate >= 0.55 then 0.10 else 0 end as payout_ratio,
       5000 * (case when achievement < 0.8 then 0
                    when achievement < 1.0 then 0.5 + (achievement - 0.8) / 0.2 * 0.5
                    else least(1.0 + (achievement - 1.0) * 1.5, 1.3) end
               + case when strike_rate >= 0.55 then 0.10 else 0 end) as payout_bdt
from base;

-- Month to date, as of the last day with data: where each territory and brand stands today.
create or replace table marts.mtd_territory_brand as
with ref as (select date '{as_of}' as d),
cal as (
    select max(wd_elapsed) as wd_elapsed, max(wd_in_month) as wd_in_month
    from staging.calendar, ref where month = strftime(ref.d, '%Y-%m') and date <= ref.d
), mtd as (
    select territory_id, brand, sum(secondary_value) as mtd_value, sum(short_value) as mtd_short
    from marts.territory_brand_day, ref
    where date >= date_trunc('month', ref.d) and date <= ref.d group by all
), lymtd as (
    select territory_id, brand, sum(secondary_value) as ly_mtd_value
    from marts.territory_brand_day, ref
    where date >= date_trunc('month', ref.d) - interval 1 year and date <= ref.d - interval 1 year
    group by all
)
select t.month, t.territory_id, t.brand, t.target_value, coalesce(m.mtd_value, 0) as mtd_value,
       coalesce(m.mtd_short, 0) as mtd_short, coalesce(l.ly_mtd_value, 0) as ly_mtd_value,
       cal.wd_elapsed, cal.wd_in_month,
       coalesce(m.mtd_value, 0) / cal.wd_elapsed * cal.wd_in_month as projected_value,
       (t.target_value - coalesce(m.mtd_value, 0)) / nullif(cal.wd_in_month - cal.wd_elapsed, 0) as required_per_day,
       coalesce(m.mtd_value, 0) / cal.wd_elapsed as current_per_day
from marts.target_territory_brand t
cross join cal cross join ref
left join mtd m on m.territory_id = t.territory_id and m.brand = t.brand
left join lymtd l on l.territory_id = t.territory_id and l.brand = t.brand
where t.month = strftime(ref.d, '%Y-%m');
