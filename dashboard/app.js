/* Kadam Consumer sales intelligence: renders dashboard.json (built by `python -m fmcg_bd all`). */
const C = {
  ink: "#0f1b2d", body: "#42506a", muted: "#8391a7", line: "#e3e8ef", accent: "#0e7c66", flower: "#f2a516",
  good: "#1e9e6a", bad: "#d64545", warn: "#d0870b", grey: "#c9d1dd",
  series: ["#0e7c66", "#f2a516", "#3b6fb6", "#9b5de5", "#e76f51", "#2a9d8f", "#6d7b93", "#c2549d", "#7aa63a", "#b5838d"],
};
const REGION_COLOR = { "Dhaka Metro": "#0e7c66", "Dhaka Central": "#3b6fb6", "Chattogram": "#f2a516",
  "North": "#9b5de5", "South-West": "#e76f51", "North-East": "#2a9d8f" };
const charts = {};
let D;

// ---------- formatting ----------
const cr = v => v == null ? "–" : `৳${(v / 1e7).toLocaleString("en-IN", { maximumFractionDigits: 1, minimumFractionDigits: 1 })} Cr`;
const lakh = v => v == null ? "–" : `৳${(v / 1e5).toLocaleString("en-IN", { maximumFractionDigits: 1, minimumFractionDigits: 1 })} L`;
const money = v => Math.abs(v) >= 1e7 ? cr(v) : lakh(v);
const pct = (v, d = 0) => v == null || isNaN(v) ? "–" : `${(v * 100).toFixed(d)}%`;
const signed = (v, d = 1) => v == null || isNaN(v) ? "–" : `${v >= 0 ? "▲" : "▼"} ${Math.abs(v * 100).toFixed(d)}%`;
const cls = v => v == null ? "" : v >= 0 ? "up" : "down";
const chip = v => `<span class="chip ${v >= 1 ? "g" : v >= 0.95 ? "a" : "r"}">${pct(v)}</span>`;
const monthName = m => new Date(m + "-01T00:00:00").toLocaleDateString("en-GB", { month: "short", year: "numeric" });
const shortMonth = m => new Date(m + "-01T00:00:00").toLocaleDateString("en-GB", { month: "short", year: "2-digit" });

function chart(id, option) {
  const el = document.getElementById(id);
  if (!charts[id]) charts[id] = echarts.init(el, null, { renderer: "canvas" });
  charts[id].setOption({ textStyle: { fontFamily: "Inter, sans-serif", color: C.body }, animationDuration: 600, ...option }, true);
  return charts[id];
}
const axis = extra => ({ axisLine: { lineStyle: { color: C.line } }, axisTick: { show: false },
  axisLabel: { color: C.muted, fontSize: 11 }, splitLine: { lineStyle: { color: "#eef1f5" } }, ...extra });
const tip = { trigger: "axis", backgroundColor: "#fff", borderColor: C.line, textStyle: { color: C.ink, fontSize: 12 } };

function table(id, cols, rows, sortKey) {
  const el = document.getElementById(id);
  let key = sortKey, asc = false;
  const draw = () => {
    const sorted = key ? [...rows].sort((a, b) => ((a[key] ?? -1e18) > (b[key] ?? -1e18) ? 1 : -1) * (asc ? 1 : -1)) : rows;
    el.innerHTML = `<thead><tr>${cols.map(c => `<th class="${c.n ? "n" : ""}" data-k="${c.k}">${c.h}${c.k === key ? (asc ? " ↑" : " ↓") : ""}</th>`).join("")}</tr></thead>` +
      `<tbody>${sorted.map(r => `<tr>${cols.map(c => `<td class="${c.n ? "n" : ""} ${c.sub ? "sub" : ""}">${c.f ? c.f(r[c.k], r) : r[c.k] ?? "–"}</td>`).join("")}</tr>`).join("")}</tbody>`;
    el.querySelectorAll("th").forEach(th => th.onclick = () => { asc = th.dataset.k === key ? !asc : false; key = th.dataset.k; draw(); });
  };
  draw();
}

// ---------- overview ----------
function kpiCard(l, v, d, opts = {}) {
  const bar = opts.bar != null ? `<div class="bar"><i style="width:${Math.min(opts.bar, 1.2) / 1.2 * 100}%"></i>${opts.mark != null ? `<b style="left:${opts.mark / 1.2 * 100}%"></b>` : ""}</div>` : "";
  return `<div class="kpi ${opts.focus ? "focus" : ""}"><div class="l">${l}</div><div class="v">${v}</div><div class="d">${d}</div>${bar}</div>`;
}

function overview() {
  const k = D.kpi, m = D.meta, timeGone = m.wd_elapsed / m.wd_in_month;
  document.getElementById("kpis").innerHTML = [
    kpiCard("Sales month to date", cr(k.mtd), `${pct(k.achievement)} of ${cr(k.target)} target`, { bar: k.achievement, mark: timeGone }),
    kpiCard("Projected month end", pct(k.projected_achievement), `${cr(k.projected)} at the current pace`, { focus: true }),
    kpiCard("Time gone", pct(timeGone), `${m.wd_elapsed} of ${m.wd_in_month} working days`),
    kpiCard("Required per day", lakh(k.required_per_day), `vs ${lakh(k.current_per_day)} so far <span class="${k.required_per_day > k.current_per_day ? "down" : "up"}">${signed(k.required_per_day / k.current_per_day - 1, 0)}</span>`),
    kpiCard("Growth vs last year", `<span class="${cls(k.yoy)}">${signed(k.yoy)}</span>`, `same days last year ${cr(k.ly_mtd)}`),
    kpiCard("Year to date", pct(k.ytd_actual / k.ytd_target), `${cr(k.ytd_actual)} · <span class="${cls(k.ytd_actual / k.ytd_ly - 1)}">${signed(k.ytd_actual / k.ytd_ly - 1)}</span> YoY`),
  ].join("");

  document.getElementById("insights").innerHTML = D.insights.map(i => `<li class="${i.tone}">${i.text}</li>`).join("");

  const t = D.trend.filter(r => r.month >= "2025-01");
  chart("c-trend", {
    tooltip: { ...tip, valueFormatter: v => v == null ? "–" : `৳${v.toFixed(1)} Cr` },
    legend: { top: 0, right: 0, itemWidth: 12, itemHeight: 8, textStyle: { color: C.body } },
    grid: { left: 44, right: 12, top: 34, bottom: 28 },
    xAxis: axis({ type: "category", data: t.map(r => shortMonth(r.month)) }),
    yAxis: axis({ type: "value", axisLabel: { color: C.muted, formatter: v => v } }),
    series: [
      { name: "Actual", type: "bar", barWidth: "58%", itemStyle: { color: C.accent }, data: t.map(r => ({ value: r.actual / 1e7,
        itemStyle: { color: r.month === m.month ? C.flower : (r.target && r.actual >= r.target ? C.accent : "#5fa596"), borderRadius: [4, 4, 0, 0] } })) },
      { name: "Target", type: "line", data: t.map(r => r.target ? r.target / 1e7 : null), symbol: "circle", symbolSize: 5,
        lineStyle: { color: C.ink, width: 2 }, itemStyle: { color: C.ink } },
      { name: "Last year", type: "line", data: t.map(r => r.ly_actual ? r.ly_actual / 1e7 : null), symbol: "none",
        lineStyle: { color: C.grey, width: 2, type: "dashed" }, itemStyle: { color: C.grey } },
    ],
  });

  echarts.registerMap("bd", D.geo);
  const dist = D.districts.map(r => ({ name: r.district, value: +(r.projected_achievement * 100).toFixed(1), r }));
  chart("c-map", {
    tooltip: { trigger: "item", backgroundColor: "#fff", borderColor: C.line, textStyle: { color: C.ink, fontSize: 12 },
      formatter: p => p.data ? `<b>${p.name}</b> · ${p.data.r.region}<br>Projected ${p.data.value}% of target<br>MTD ${money(p.data.r.mtd)} of ${money(p.data.r.target)}<br>vs last year <span style="color:${p.data.r.yoy >= 0 ? C.good : C.bad}">${signed(p.data.r.yoy)}</span>` : p.name },
    visualMap: { min: 88, max: 106, calculable: true, orient: "horizontal", left: 10, bottom: 6, itemHeight: 140, itemWidth: 10,
      formatter: v => `${Math.round(v)}%`, textStyle: { color: C.muted, fontSize: 11 },
      inRange: { color: ["#c93a3a", "#ef8f5b", "#f7d58b", "#a7d8b6", "#1e8f62"] } },
    series: [{ type: "map", map: "bd", roam: false, data: dist, aspectScale: 0.92, layoutCenter: ["50%", "48%"], layoutSize: "92%",
      itemStyle: { borderColor: "#fff", borderWidth: 0.8 }, emphasis: { label: { show: true, color: C.ink, fontWeight: 700 }, itemStyle: { areaColor: C.flower } },
      select: { disabled: true } }],
  });

  document.getElementById("tg-hint").textContent = `Time gone ${pct(timeGone)} · ${monthName(m.month)}`;
  const regs = [...D.regions].sort((a, b) => b.target - a.target);
  table("t-regions", [
    { k: "region", h: "Region" },
    { k: "target", h: "Target", n: 1, f: cr }, { k: "mtd", h: "MTD", n: 1, f: cr },
    { k: "achievement", h: "Ach.", n: 1, f: v => pct(v) },
    { k: "projected_achievement", h: "Projected", n: 1, f: chip },
    { k: "yoy", h: "vs LY", n: 1, f: v => `<span class="${cls(v)}">${signed(v)}</span>` },
  ], regs);

  chart("c-pace", {
    tooltip: { ...tip, valueFormatter: v => `৳${v.toFixed(1)} L` },
    legend: { top: 0, right: 0, itemWidth: 12, itemHeight: 8 },
    grid: { left: 96, right: 16, top: 28, bottom: 18 },
    yAxis: axis({ type: "category", data: regs.map(r => r.region), inverse: true }),
    xAxis: axis({ type: "value" }),
    series: [
      { name: "So far", type: "bar", data: regs.map(r => r.current_per_day / 1e5), itemStyle: { color: C.grey, borderRadius: 3 }, barGap: "10%" },
      { name: "Required", type: "bar", itemStyle: { color: C.bad }, data: regs.map(r => ({ value: r.required_per_day / 1e5, itemStyle: { color: r.required_per_day > r.current_per_day * 1.05 ? C.bad : C.accent, borderRadius: 3 } })) },
    ],
  });
}

// ---------- targets ----------
function targets() {
  const regionSel = document.getElementById("f-region"), brandSel = document.getElementById("f-brand");
  regionSel.innerHTML = ["All regions", ...Object.keys(REGION_COLOR)].map(r => `<option>${r}</option>`).join("");
  brandSel.innerHTML = ["All brands", ...D.brands_mtd.map(b => b.brand).sort()].map(b => `<option>${b}</option>`).join("");
  const draw = () => {
    const reg = regionSel.value, brand = brandSel.value;
    const tb = brand === "All brands" ? null : D.territory_brand.filter(r => r.brand === brand);
    const rows = D.territories.filter(t => reg === "All regions" || t.region === reg).map(t => {
      if (!tb) return t;
      const x = tb.find(r => r.territory_id === t.territory_id);
      return { ...t, target: x.target_value, mtd: x.mtd_value, projected: x.projected_value,
        achievement: x.mtd_value / x.target_value, projected_achievement: x.projected_value / x.target_value,
        yoy: x.ly_mtd_value ? x.mtd_value / x.ly_mtd_value - 1 : null,
        required_per_day: (x.target_value - x.mtd_value) / Math.max(D.meta.wd_in_month - D.meta.wd_elapsed, 1) };
    });
    const tot = rows.reduce((a, r) => ({ t: a.t + r.target, p: a.p + r.projected }), { t: 0, p: 0 });
    document.getElementById("f-note").textContent = `${rows.length} territories · projected ${pct(tot.p / tot.t)} of ${cr(tot.t)}`;
    table("t-terr", [
      { k: "territory", h: "Territory" }, { k: "area", h: "Area", sub: 1 }, { k: "territory_officer", h: "Territory officer", sub: 1 },
      { k: "target", h: "Target", n: 1, f: lakh }, { k: "mtd", h: "MTD", n: 1, f: lakh },
      { k: "projected_achievement", h: "Projected", n: 1, f: chip },
      { k: "yoy", h: "vs LY", n: 1, f: v => `<span class="${cls(v)}">${signed(v)}</span>` },
      { k: "required_per_day", h: "Need / day", n: 1, f: lakh },
    ], rows, "projected_achievement");

    const areas = {};
    rows.forEach(r => { const a = areas[r.area] ??= { area: r.area, region: r.region, t: 0, p: 0 }; a.t += r.target; a.p += r.projected; });
    const list = Object.values(areas).map(a => ({ ...a, v: a.p / a.t })).sort((a, b) => a.v - b.v);
    chart("c-areas", {
      tooltip: { ...tip, formatter: p => `<b>${p[0].name}</b><br>${list[p[0].dataIndex].region}<br>Projected ${p[0].value.toFixed(1)}%` },
      grid: { left: 130, right: 46, top: 6, bottom: 24 },
      yAxis: axis({ type: "category", data: list.map(a => a.area) }),
      xAxis: axis({ type: "value", min: v => Math.floor(Math.min(v.min, 90) / 5) * 5, axisLabel: { formatter: "{value}%", color: C.muted } }),
      series: [{ type: "bar", data: list.map(a => ({ value: a.v * 100, itemStyle: { color: REGION_COLOR[a.region], borderRadius: 3 } })),
        label: { show: true, position: "right", formatter: p => `${p.value.toFixed(0)}%`, color: C.ink, fontSize: 11 },
        markLine: { symbol: "none", data: [{ xAxis: 100 }], lineStyle: { color: C.ink, type: "dashed" }, label: { show: false } } }],
    });
  };
  regionSel.onchange = brandSel.onchange = draw;
  draw();
}

// ---------- brands ----------
function brands() {
  const ytd = [...D.brand_ytd].sort((a, b) => b.actual - a.actual);
  const cat = Object.fromEntries(D.skus.map(s => [s.brand, s.category]));
  document.getElementById("brand-cards").innerHTML = ytd.map(b => {
    const g = b.actual / b.ly - 1, a = b.actual / b.target;
    return `<div class="bc"><div class="t">${b.brand}<span class="${cls(g)}">${signed(g, 0)}</span></div><div class="c">${cat[b.brand]}</div>
      <div class="v">${cr(b.actual)}</div><div class="d">${pct(a)} of target YTD</div></div>`;
  }).join("");

  const months = [...new Set(D.brand_month.map(r => r.month))].filter(m => m >= "2025-01" && m < D.meta.month);
  const names = ytd.map(b => b.brand);
  const avg = Object.fromEntries(names.map(n => {
    const v = D.brand_month.filter(r => r.brand === n && months.includes(r.month)).map(r => r.v);
    return [n, v.reduce((a, b) => a + b, 0) / v.length];
  }));
  const cells = D.brand_month.filter(r => months.includes(r.month))
    .map(r => [months.indexOf(r.month), names.indexOf(r.brand), +(r.v / avg[r.brand]).toFixed(2)]);
  chart("c-season", {
    tooltip: { position: "top", formatter: p => `${names[p.value[1]]} · ${monthName(months[p.value[0]])}<br>${p.value[2].toFixed(2)}× its average month` },
    grid: { left: 70, right: 10, top: 6, bottom: 62 },
    xAxis: axis({ type: "category", data: months.map(shortMonth), splitArea: { show: false }, axisLabel: { color: C.muted, fontSize: 10, rotate: 45 } }),
    yAxis: axis({ type: "category", data: names }),
    visualMap: { min: 0.3, max: 2.2, show: false, inRange: { color: ["#e6eef7", "#ffffff", "#ffe2a6", "#f2a516", "#c25e00"] } },
    series: [{ type: "heatmap", data: cells, itemStyle: { borderColor: "#fff", borderWidth: 1 } }],
  });

  const sm = D.sku_short_month;
  const top = Object.entries(sm.reduce((a, r) => (a[r.sku_name] = (a[r.sku_name] || 0) + r.short_value, a), {}))
    .sort((a, b) => b[1] - a[1]).slice(0, 6).map(x => x[0]);
  const ms = [...new Set(sm.map(r => r.month))].filter(m => m < D.meta.month);
  chart("c-short", {
    tooltip: { ...tip, valueFormatter: v => `৳${(v || 0).toFixed(1)} L` },
    legend: { bottom: 0, itemWidth: 10, itemHeight: 8, textStyle: { fontSize: 11 } },
    grid: { left: 44, right: 10, top: 10, bottom: 56 },
    xAxis: axis({ type: "category", data: ms.map(shortMonth) }), yAxis: axis({ type: "value" }),
    series: top.map((n, i) => ({ name: n, type: "bar", stack: "s", data: ms.map(m => (sm.find(r => r.month === m && r.sku_name === n)?.short_value || 0) / 1e5),
      itemStyle: { color: C.series[i] } })),
  });

  document.getElementById("sku-hint").textContent = `January to ${monthName(D.meta.last_closed)}, against the same months last year`;
  table("t-sku", [
    { k: "sku_name", h: "SKU" }, { k: "category", h: "Category", sub: 1 },
    { k: "v", h: "Sales YTD", n: 1, f: lakh },
    { k: "g", h: "vs LY", n: 1, f: v => `<span class="${cls(v)}">${signed(v)}</span>` },
    { k: "u", h: "Units", n: 1, f: v => Math.round(v).toLocaleString("en-IN") },
    { k: "fill", h: "Fill rate", n: 1, f: v => `<span class="${v < 0.95 ? "down" : ""}">${pct(v, 1)}</span>` },
    { k: "s", h: "Lost to short supply", n: 1, f: lakh },
  ], D.skus.map(s => ({ ...s, g: s.ly_v ? s.v / s.ly_v - 1 : null })), "v");
}

// ---------- field force ----------
function field() {
  const s = D.srs, pt = D.payout_trend.filter(r => r.month < D.meta.month);
  const hit = s.filter(r => r.achievement >= 1).length;
  const avg = k => s.reduce((a, r) => a + (r[k] || 0), 0) / s.length;
  const payout = s.reduce((a, r) => a + r.payout_bdt, 0);
  document.getElementById("kpis-field").innerHTML = [
    kpiCard("SRs scored", s.length, `${monthName(D.meta.last_closed)} · ${D.kpi.vacant_positions} beats open on the 1st`),
    kpiCard("Hit target", pct(hit / s.length), `${hit} SRs at 100% or more`, { focus: true }),
    kpiCard("Median achievement", pct(s.map(r => r.achievement).sort((a, b) => a - b)[Math.floor(s.length / 2)]), "value across all brands"),
    kpiCard("Strike rate", pct(avg("strike_rate")), "productive calls / visits"),
    kpiCard("Lines per call", avg("lines_per_call").toFixed(2), "SKUs per productive memo"),
    kpiCard("Incentive paid", lakh(payout), `avg ৳${Math.round(payout / s.length).toLocaleString("en-IN")} per SR`),
  ].join("");
  document.getElementById("field-hint").textContent = `${monthName(D.meta.last_closed)} · one dot per SR, coloured by region`;

  const regions = Object.keys(REGION_COLOR);
  chart("c-scatter", {
    tooltip: { trigger: "item", formatter: p => `<b>${p.data[3]}</b> · ${p.data[4]}<br>Achievement ${p.data[1].toFixed(0)}%<br>Strike rate ${p.data[0].toFixed(0)}%<br>Incentive ৳${Math.round(p.data[5]).toLocaleString("en-IN")}` },
    legend: { top: 0, right: 0, itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 11 } },
    grid: { left: 46, right: 14, top: 34, bottom: 40 },
    xAxis: axis({ type: "value", name: "Strike rate", nameLocation: "middle", nameGap: 26, min: 30, max: 85, axisLabel: { formatter: "{value}%", color: C.muted } }),
    yAxis: axis({ type: "value", name: "Achievement", min: 60, max: 150, axisLabel: { formatter: "{value}%", color: C.muted } }),
    series: regions.map(rg => ({ name: rg, type: "scatter", symbolSize: 7, itemStyle: { color: REGION_COLOR[rg], opacity: 0.72 },
      data: s.filter(r => r.region === rg).map(r => [r.strike_rate * 100, r.achievement * 100, 0, r.sr_name, r.territory, r.payout_bdt]),
      markLine: rg === regions[0] ? { symbol: "none", silent: true, lineStyle: { color: C.ink, type: "dashed" }, label: { show: false }, data: [{ yAxis: 100 }, { xAxis: 55 }] } : undefined })),
  });

  chart("c-payout", {
    tooltip: tip, legend: { top: 0, right: 0, itemWidth: 12, itemHeight: 8 },
    grid: { left: 44, right: 44, top: 34, bottom: 28 },
    xAxis: axis({ type: "category", data: pt.map(r => shortMonth(r.month)) }),
    yAxis: [axis({ type: "value" }), axis({ type: "value", min: 0, max: 1, axisLabel: { formatter: v => pct(v), color: C.muted }, splitLine: { show: false } })],
    series: [
      { name: "Incentive (৳ lakh)", type: "bar", data: pt.map(r => +(r.payout / 1e5).toFixed(1)), itemStyle: { color: C.flower, borderRadius: [3, 3, 0, 0] } },
      { name: "Hit rate", type: "line", yAxisIndex: 1, data: pt.map(r => +r.hit_rate.toFixed(3)), lineStyle: { color: C.accent, width: 2 }, itemStyle: { color: C.accent }, symbolSize: 5 },
    ],
  });
  const cols = [
    { k: "sr_name", h: "SR" }, { k: "territory", h: "Territory", sub: 1 },
    { k: "achievement", h: "Ach.", n: 1, f: chip }, { k: "actual_value", h: "Sales", n: 1, f: lakh },
    { k: "strike_rate", h: "Strike", n: 1, f: v => pct(v) }, { k: "lines_per_call", h: "LPC", n: 1, f: v => v?.toFixed(1) },
    { k: "payout_bdt", h: "Incentive", n: 1, f: v => `৳${Math.round(v).toLocaleString("en-IN")}` },
  ];
  table("t-top", cols, s.slice(0, 10));
  table("t-bottom", cols, s.slice(-10).reverse());
}

// ---------- distribution ----------
function distribution() {
  const last = D.meta.last_closed;
  const nd = {};
  D.distribution.filter(r => r.month === last).forEach(r => { const b = nd[r.brand] ??= { b: 0, c: 0 }; b.b += r.buying; b.c += r.covered; });
  const ndl = Object.entries(nd).map(([k, v]) => ({ brand: k, v: v.b / v.c })).sort((a, b) => a.v - b.v);
  const cov = D.kpi.covered_outlets / D.universe.reduce((a, r) => a + r.outlets, 0);
  document.getElementById("nd-hint").textContent = `Outlets on SR routes that bought the brand in ${monthName(last)} · routes reach ${pct(cov)} of all shops`;
  chart("c-nd", {
    tooltip: { ...tip, valueFormatter: v => `${v.toFixed(1)}%` }, grid: { left: 74, right: 40, top: 6, bottom: 20 },
    yAxis: axis({ type: "category", data: ndl.map(r => r.brand) }), xAxis: axis({ type: "value", axisLabel: { formatter: "{value}%", color: C.muted } }),
    series: [{ type: "bar", data: ndl.map(r => +(r.v * 100).toFixed(1)), itemStyle: { color: C.accent, borderRadius: 3 },
      label: { show: true, position: "right", formatter: "{c}%", color: C.ink, fontSize: 11 } }],
  });
  const lt = D.loading_trend.filter(r => r.month < D.meta.month && r.month >= "2025-01");
  chart("c-loading", {
    tooltip: { ...tip, valueFormatter: v => `${v.toFixed(1)}%` }, grid: { left: 40, right: 12, top: 14, bottom: 28 },
    xAxis: axis({ type: "category", data: lt.map(r => shortMonth(r.month)) }),
    yAxis: axis({ type: "value", min: 0, axisLabel: { formatter: "{value}%", color: C.muted } }),
    series: [{ type: "line", smooth: true, data: lt.map(r => +(r.share * 100).toFixed(1)), lineStyle: { color: C.flower, width: 3 }, itemStyle: { color: C.flower },
      areaStyle: { color: "rgba(242,165,22,.12)" }, markLine: { symbol: "none", data: [{ yAxis: 11.5, name: "even pace" }],
        lineStyle: { color: C.muted, type: "dashed" }, label: { formatter: "even pace", position: "insideStartTop", color: C.muted, fontSize: 11 } } }],
  });
  chart("c-universe", {
    tooltip: { trigger: "item", formatter: p => `${p.name}: ${p.value.toLocaleString("en-IN")} shops` },
    grid: { left: 96, right: 70, top: 6, bottom: 10 },
    yAxis: axis({ type: "category", data: D.universe.map(r => r.channel), inverse: true }), xAxis: axis({ type: "value", show: false }),
    series: [{ type: "bar", data: D.universe.map(r => r.outlets), itemStyle: { color: C.ink, borderRadius: 3 },
      label: { show: true, position: "right", formatter: p => p.value.toLocaleString("en-IN"), color: C.ink, fontSize: 11 } }],
  });
  document.getElementById("stock-hint").textContent = `Stock at ${monthName(last)} month end, against the next 30 days of sales`;
  table("t-stock", [
    { k: "distributor", h: "Distributor" }, { k: "territory", h: "Territory", sub: 1 },
    { k: "cover_days", h: "Cover (days)", n: 1, f: v => `<span class="${v > 14 ? "warn" : v < 4 ? "down" : ""}">${v?.toFixed(1)}</span>` },
    { k: "stock_value_dp", h: "Stock", n: 1, f: lakh },
    { k: "primary_value", h: "Primary", n: 1, f: lakh }, { k: "secondary_value", h: "Secondary", n: 1, f: lakh },
    { k: "month_end_share", h: "Month-end loading", n: 1, f: v => `<span class="${v > 0.3 ? "warn" : ""}">${pct(v)}</span>` },
    { k: "short_value", h: "Unfilled", n: 1, f: lakh },
  ], D.stock, "cover_days");
}

// ---------- market ----------
function market() {
  const periods = [...new Set(D.audit.map(r => r.period))];
  const cats = [...new Set(D.audit.map(r => r.category))];
  chart("c-share", {
    tooltip: { ...tip, valueFormatter: v => `${v.toFixed(1)}%` },
    legend: { bottom: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 11 } },
    grid: { left: 40, right: 16, top: 12, bottom: 64 },
    xAxis: axis({ type: "category", data: periods }), yAxis: axis({ type: "value", axisLabel: { formatter: "{value}%", color: C.muted } }),
    series: cats.map((c, i) => ({ name: c, type: "line", symbolSize: 5, data: periods.map(p => +((D.audit.find(r => r.period === p && r.category === c)?.share || 0) * 100).toFixed(1)),
      lineStyle: { width: 2, color: C.series[i] }, itemStyle: { color: C.series[i] } })),
  });
  const regs = Object.keys(REGION_COLOR);
  const cells = D.audit_region.map(r => [cats.indexOf(r.category), regs.indexOf(r.region), +(r.share * 100).toFixed(1)]);
  document.getElementById("share-hint").textContent = periods[periods.length - 1];
  chart("c-share-region", {
    tooltip: { formatter: p => `${regs[p.value[1]]} · ${cats[p.value[0]]}<br>Share ${p.value[2]}%` },
    grid: { left: 96, right: 8, top: 6, bottom: 92 },
    xAxis: axis({ type: "category", data: cats, axisLabel: { rotate: 40, color: C.muted, fontSize: 10.5 } }), yAxis: axis({ type: "category", data: regs }),
    visualMap: { min: 5, max: 32, show: false, inRange: { color: ["#eef5f3", "#9fd3c5", "#0e7c66"] } },
    series: [{ type: "heatmap", data: cells, label: { show: true, color: C.ink, fontSize: 10.5 }, itemStyle: { borderColor: "#fff", borderWidth: 2 } }],
  });
  const latest = D.audit.filter(r => r.period === periods[periods.length - 1]).sort((a, b) => b.market - a.market);
  const part = k => latest.map(r => +(r.market * r[k] / 1e7).toFixed(1));
  chart("c-market", {
    tooltip: { ...tip, valueFormatter: v => `৳${v} Cr` }, legend: { top: 0, right: 0, itemWidth: 12, itemHeight: 8 },
    grid: { left: 40, right: 10, top: 30, bottom: 50 },
    xAxis: axis({ type: "category", data: latest.map(r => r.category), axisLabel: { color: C.muted, fontSize: 11, interval: 0, rotate: 18 } }), yAxis: axis({ type: "value" }),
    series: [["Kadam", "share", C.accent], ["Competitor A", "comp_a", "#3b6fb6"], ["Competitor B", "comp_b", "#9fb2cc"], ["Competitor C", "comp_c", "#c9d1dd"]]
      .map(([n, k, c]) => ({ name: n, type: "bar", stack: "m", data: part(k), itemStyle: { color: c } })),
  });
}

// ---------- planner ----------
function planner() {
  const nm = monthName(D.meta.next_month);
  document.getElementById("plan-title").textContent = `How the ${nm} targets were set (draft, issued on the 25th)`;
  const t = D.plan.reduce((a, r) => ({ t: a.t + r.target, ly: a.ly + r.ly, c: a.c + r.capped, f: a.f + r.floored }), { t: 0, ly: 0, c: 0, f: 0 });
  document.getElementById("kpis-plan").innerHTML = [
    kpiCard(`${nm} target`, cr(t.t), `${signed(t.t / t.ly - 1)} on ${monthName(D.meta.next_month.replace(/^\d{4}/, y => y - 1))}`, { focus: true }),
    kpiCard("Territories", D.plan.length, "one distributor each"),
    kpiCard("SR positions", D.plan_sr.positions, `${D.plan_sr.vacant} vacant on the 1st, held by the TO`),
    kpiCard("Held at the cap", t.c, "territory-brands limited to +30%"),
    kpiCard("Held at the floor", t.f, "territory-brands kept at -5%"),
    kpiCard("Exact roll-up", "৳0", "difference between SR, territory and plan totals"),
  ].join("");
  table("t-plan-brand", [
    { k: "brand", h: "Brand" }, { k: "target", h: "Target", n: 1, f: cr }, { k: "ly", h: "Last year", n: 1, f: cr },
    { k: "g", h: "Growth", n: 1, f: v => `<span class="${cls(v)}">${signed(v)}</span>` },
    { k: "plan_growth", h: "Annual plan", n: 1, f: v => `+${pct(v, 1)}` },
  ], D.plan_brand.map(r => ({ ...r, g: r.target / r.ly - 1 })), "target");
  table("t-plan", [
    { k: "territory", h: "Territory" }, { k: "region", h: "Region", sub: 1 },
    { k: "target", h: "Target", n: 1, f: lakh }, { k: "ly", h: "Last year", n: 1, f: lakh },
    { k: "g", h: "Growth", n: 1, f: v => `<span class="${cls(v)}">${signed(v)}</span>` },
    { k: "capped", h: "Capped", n: 1, f: v => v || "–" }, { k: "floored", h: "Floored", n: 1, f: v => v || "–" },
  ], D.plan.map(r => ({ ...r, g: r.target / r.ly - 1 })), "target");
}

// ---------- boot ----------
const renderers = { overview, targets, brands, field, distribution, market, planner };
const done = new Set();
function show(tab) {
  document.querySelectorAll(".tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === tab));
  document.querySelectorAll(".page").forEach(p => p.classList.toggle("on", p.id === tab));
  if (!done.has(tab)) { renderers[tab](); done.add(tab); }
  Object.values(charts).forEach(c => c.resize());
  history.replaceState(null, "", `#${tab}`);
}
document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => show(b.dataset.tab));
window.addEventListener("resize", () => Object.values(charts).forEach(c => c.resize()));

Promise.all([fetch("data/dashboard.json").then(r => r.json()), fetch("data/bd_districts.geojson").then(r => r.json())])
  .then(([d, geo]) => {
    D = d; D.geo = geo;
    const m = D.meta;
    document.getElementById("asof").textContent = `As of ${new Date(m.as_of + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })} · day ${m.wd_elapsed} of ${m.wd_in_month} working days · ${D.kpi.territories} territories · ${D.kpi.active_srs} SRs`;
    document.getElementById("foot-note").textContent = m.note;
    const start = location.hash.slice(1);
    show(renderers[start] ? start : "overview");
  });
