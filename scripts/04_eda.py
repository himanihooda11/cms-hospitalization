# Task 4: exploratory analysis and interactive state map.
#
# Reads output/hospitalization_risk.csv (and the raw csvs for the two charts that
# need counts not in the output table) and writes to output/eda/:
#   1_flow.png            people and hospitalizations per year, before and after the HMO rule
#   2_risk_by_year.png    overall risk per year, next to claims per admission year
#   3_risk_by_age.png     risk by age group, one line per year
#   4_sex_by_age.png      risk by sex across age groups, one panel per year
#   5_race.png            crude vs age-standardized risk by race, per year
#   6_group_sizes.png     histogram of n_at_risk, groups under 11 highlighted
#   7_race_age_heatmap.png risk by race and age group, per year
#   risk_map.html         interactive map: age-standardized risk by state
#
# Every table behind a chart is printed, so the numbers can be checked.
# Risk for combined groups = total hospitalized / total at risk (never an average of risks).
#
# Age standardization (direct): weights are the share of each age group in the
# pooled 2008-2010 at-risk population. Standardized risk = sum(weight x age-specific risk).
#
# Usage: python scripts/04_eda.py

import json
from pathlib import Path

import duckdb
import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

root = Path(__file__).resolve().parents[1]
csv_dir = root / "files" / "csv"
risk_file = root / "output" / "hospitalization_risk.csv"
eda_dir = root / "output" / "eda"

age_order = ["<65", "65-69", "70-74", "75-79", "80-84", "85-89", "90+"]
race_order = ["White", "Black", "Other", "Hispanic"]
years = [2008, 2009, 2010]
min_n_map = 100  # states with fewer people at risk in the selected group are greyed out on the map

# colors (validated categorical slots 1-3, a single-hue ramp for magnitude, neutral greys)
blue, orange, aqua = "#2a78d6", "#eb6834", "#1baf7a"
year_color = {2008: blue, 2009: orange, 2010: aqua}
ink, muted, grid = "#0b0b0b", "#52514e", "#e4e3df"
blue_ramp = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

# SSA state code -> postal abbreviation (needed to place states on the map)
state_abbr = {
    1: "AL", 2: "AK", 3: "AZ", 4: "AR", 5: "CA", 6: "CO", 7: "CT", 8: "DE", 9: "DC",
    10: "FL", 11: "GA", 12: "HI", 13: "ID", 14: "IL", 15: "IN", 16: "IA", 17: "KS",
    18: "KY", 19: "LA", 20: "ME", 21: "MD", 22: "MA", 23: "MI", 24: "MN", 25: "MS",
    26: "MO", 27: "MT", 28: "NE", 29: "NV", 30: "NH", 31: "NJ", 32: "NM", 33: "NY",
    34: "NC", 35: "ND", 36: "OH", 37: "OK", 38: "OR", 39: "PA", 41: "RI", 42: "SC",
    43: "SD", 44: "TN", 45: "TX", 46: "UT", 47: "VT", 49: "VA", 50: "WA", 51: "WV",
    52: "WI", 53: "WY",
}

plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": muted, "axes.labelcolor": muted,
    "xtick.color": muted, "ytick.color": muted, "axes.titlecolor": ink,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": grid, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "legend.frameon": False, "figure.dpi": 120, "savefig.bbox": "tight",
})


def section(title):
    print(f"\n=== {title} ===")


def show(table):
    print(table.to_string())


def short(v, _=None):
    # 2326856 -> 2.3M, 551828 -> 552K, 640 -> 640
    if abs(v) >= 1e6:
        return f"{v / 1e6:.1f}M"
    if abs(v) >= 1e3:
        return f"{v / 1e3:.0f}K"
    return f"{v:.0f}"


def pct(ax):
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))


def save(fig, name):
    fig.savefig(eda_dir / name)
    plt.close(fig)
    print(f"saved output/eda/{name}")


def combine(df, by):
    # total hospitalized / total at risk for each group
    g = df.groupby(by, as_index=False)[["n_at_risk", "n_hospitalized"]].sum()
    g["risk"] = g["n_hospitalized"] / g["n_at_risk"]
    return g


def age_weights(df):
    w = df.groupby("age_group")["n_at_risk"].sum().reindex(age_order)
    return w / w.sum()


def standardize(df, by, weights):
    # age-specific risk inside each group, then weighted with the standard age mix.
    # A group missing any age group gets no standardized value.
    a = combine(df, by + ["age_group"])
    crude = combine(df, by)
    rows = []
    for key, part in a.groupby(by):
        part = part.set_index("age_group").reindex(age_order)
        std = (part["risk"] * weights).sum() if part["risk"].notna().all() else float("nan")
        rows.append((*(key if isinstance(key, tuple) else (key,)), std))
    std = pd.DataFrame(rows, columns=by + ["std_risk"])
    return crude.merge(std, on=by)


def raw_counts():
    # counts that are not in the output table: rows before the HMO rule,
    # hospitalized people before the HMO rule, and claims per admission year
    con = duckdb.connect()
    people = con.execute(f"""
        SELECT CAST(regexp_extract(filename, '_(\\d{{4}})_Beneficiary', 1) AS INTEGER) AS year,
               count(*) AS rows_in_file,
               count(*) FILTER (WHERE CAST(BENE_HMO_CVRAGE_TOT_MONS AS INTEGER) > 0) AS hmo_excluded
        FROM read_csv('{csv_dir}/DE1_0_*_Beneficiary_Summary_File_*.csv', all_varchar = true, filename = true)
        GROUP BY 1 ORDER BY 1
    """).df()
    con.execute(f"""
        CREATE TABLE claims AS
        SELECT CLM_ID, min(DESYNPUF_ID) AS id,
               min(CAST(try_strptime(CLM_ADMSN_DT, '%Y%m%d') AS DATE)) AS adm
        FROM read_csv('{csv_dir}/DE1_0_2008_to_2010_Inpatient_Claims_*.csv', all_varchar = true)
        GROUP BY CLM_ID
    """)
    claims = con.execute("""
        SELECT year(adm) AS year, count(*) AS claims FROM claims GROUP BY 1 ORDER BY 1
    """).df()
    hosp = con.execute("""
        SELECT year, count(*) AS hospitalized_all
        FROM (SELECT DISTINCT id, year(adm) AS year FROM claims WHERE year(adm) BETWEEN 2008 AND 2010)
        GROUP BY 1 ORDER BY 1
    """).df()
    return people.merge(hosp, on="year"), claims


def chart_flow(df, people):
    # 1. people and hospitalizations per year, before and after the HMO rule
    t = people.merge(combine(df, ["year"]), on="year")
    t["hospitalized_not_counted"] = t["hospitalized_all"] - t["n_hospitalized"]
    section("1. People and hospitalizations per year")
    show(t[["year", "rows_in_file", "hmo_excluded", "n_at_risk",
            "hospitalized_all", "hospitalized_not_counted", "n_hospitalized"]])

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    x = range(len(years))
    for ax, cols, labels, title in [
        (axes[0], ["rows_in_file", "hmo_excluded", "n_at_risk"],
         ["In beneficiary files", "Excluded: HMO months", "At risk (denominator)"], "People"),
        (axes[1], ["hospitalized_all", "hospitalized_not_counted", "n_hospitalized"],
         ["With an admission", "Not counted (HMO months)", "Hospitalized (numerator)"], "People with an admission"),
    ]:
        for i, (c, lab, color) in enumerate(zip(cols, labels, [muted, orange, blue])):
            bars = ax.bar([p + (i - 1) * 0.27 for p in x], t[c], width=0.25, color=color, label=lab)
            ax.bar_label(bars, labels=[short(v) for v in t[c]], fontsize=7, color=muted, padding=2)
        ax.set_xticks(list(x), years)
        ax.set_title(title, loc="left")
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(short))
        ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=1)
    save(fig, "1_flow.png")


def chart_year(df, claims):
    # 2. overall risk per year, next to claims per admission year
    t = combine(df, ["year"])
    section("2. Risk per year and claims per admission year")
    show(t)
    show(claims)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    bars = axes[0].bar(t["year"].astype(str), t["risk"], color=blue, width=0.5)
    axes[0].bar_label(bars, labels=[f"{r:.1%}" for r in t["risk"]], color=ink, padding=2)
    axes[0].set_title("Hospitalization risk, all groups", loc="left")
    pct(axes[0])
    bars = axes[1].bar(claims["year"].astype(str), claims["claims"], color=muted, width=0.5)
    axes[1].bar_label(bars, labels=[f"{c:,}" for c in claims["claims"]], color=ink, padding=2, fontsize=8)
    axes[1].set_title("Inpatient claims by admission year (2007 not used)", loc="left")
    axes[1].yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(short))
    save(fig, "2_risk_by_year.png")


def chart_age(df):
    # 3. risk by age group, one line per year
    t = combine(df, ["year", "age_group"])
    section("3. Risk by age group and year")
    show(t.pivot(index="age_group", columns="year", values="risk").reindex(age_order).round(4))

    fig, ax = plt.subplots(figsize=(8, 4))
    for y in years:
        part = t[t["year"] == y].set_index("age_group").reindex(age_order)
        ax.plot(age_order, part["risk"], color=year_color[y], linewidth=2, marker="o", markersize=5, label=str(y))
    ax.set_title("Hospitalization risk by age group", loc="left")
    ax.set_xlabel("Age group (age on Dec 31)")
    pct(ax)
    ax.legend(title="Year")
    save(fig, "3_risk_by_age.png")


def chart_sex_age(df):
    # 4. risk by sex across age groups, one panel per year
    t = combine(df, ["year", "sex", "age_group"])
    section("4. Risk by sex and age group")
    show(t.pivot_table(index="age_group", columns=["year", "sex"], values="risk").reindex(age_order).round(4))

    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
    for ax, y in zip(axes, years):
        for sex, color in [("Female", blue), ("Male", orange)]:
            part = t[(t["year"] == y) & (t["sex"] == sex)].set_index("age_group").reindex(age_order)
            ax.plot(age_order, part["risk"], color=color, linewidth=2, marker="o", markersize=5, label=sex)
        ax.set_title(str(y), loc="left")
        ax.tick_params(axis="x", labelrotation=45)
    pct(axes[0])
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper right", ncol=2, bbox_to_anchor=(1, 1.06))
    fig.suptitle("Hospitalization risk by sex and age group", x=0.01, y=1.04, ha="left", color=ink)
    save(fig, "4_sex_by_age.png")


def chart_race(df, weights):
    # 5. crude vs age-standardized risk by race, per year
    t = standardize(df, ["year", "race"], weights)
    section("5. Risk by race: crude vs age-standardized")
    show(t.round(4))

    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
    for ax, y in zip(axes, years):
        part = t[t["year"] == y].set_index("race").reindex(race_order)
        x = range(len(race_order))
        ax.bar([p - 0.2 for p in x], part["risk"], width=0.38, color=muted, label="Crude")
        ax.bar([p + 0.2 for p in x], part["std_risk"], width=0.38, color=blue, label="Age-standardized")
        ax.set_xticks(list(x), race_order)
        ax.set_title(str(y), loc="left")
    pct(axes[0])
    fig.legend(*axes[0].get_legend_handles_labels(), loc="upper right", ncol=2, bbox_to_anchor=(1, 1.06))
    fig.suptitle("Hospitalization risk by race, crude and age-standardized", x=0.01, y=1.04, ha="left", color=ink)
    save(fig, "5_race.png")


def chart_group_sizes(df):
    # 6. how many people each output row is based on
    small = df["n_at_risk"] < 11
    section("6. Group sizes (n_at_risk per output row)")
    print(df["n_at_risk"].describe().round(1).to_string())
    print(f"rows with fewer than 11 people: {small.sum():,} of {len(df):,}")
    print(f"risk in those rows: min {df.loc[small, 'risk'].min():.2f}, max {df.loc[small, 'risk'].max():.2f}")

    bins = [1, 2, 5, 11, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(df.loc[~small, "n_at_risk"], bins=bins, color=blue, label="11 or more people", rwidth=0.9)
    ax.hist(df.loc[small, "n_at_risk"], bins=bins, color=orange, label="Fewer than 11 people", rwidth=0.9)
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_title(f"People at risk per output row ({small.sum():,} of {len(df):,} rows under 11)", loc="left")
    ax.set_xlabel("n_at_risk (log scale)")
    ax.set_ylabel("Output rows")
    ax.legend()
    save(fig, "6_group_sizes.png")


def chart_heatmap(df):
    # 7. risk by race and age group, per year
    t = combine(df, ["year", "race", "age_group"])
    section("7. Risk by race and age group")
    show(t.pivot_table(index=["year", "race"], columns="age_group", values="risk")[age_order].round(4))

    vmax = t["risk"].max()
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list("blue", blue_ramp)
    fig, axes = plt.subplots(1, 3, figsize=(14, 3.6), sharey=True)
    for ax, y in zip(axes, years):
        m = t[t["year"] == y].pivot(index="race", columns="age_group", values="risk").reindex(race_order)[age_order]
        im = ax.imshow(m.values, cmap=cmap, vmin=0, vmax=vmax, aspect="auto")
        for i in range(m.shape[0]):
            for j in range(m.shape[1]):
                v = m.values[i, j]
                ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=8,
                        color="white" if v > vmax * 0.6 else ink)
        ax.set_xticks(range(len(age_order)), age_order, rotation=45)
        ax.set_yticks(range(len(race_order)), race_order)
        ax.set_title(str(y), loc="left")
        ax.grid(False)
    fig.colorbar(im, ax=axes, format=matplotlib.ticker.PercentFormatter(1.0, decimals=0), shrink=0.8)
    fig.suptitle("Hospitalization risk by race and age group", x=0.01, y=1.04, ha="left", color=ink)
    save(fig, "7_race_age_heatmap.png")


def build_map(df, weights):
    # one record per year x group x state, then a small html page with two dropdowns
    groups = [("All", None)] + [(s, ("sex", s)) for s in ["Female", "Male"]] + [(r, ("race", r)) for r in race_order]
    records = []
    for name, filt in groups:
        part = df if filt is None else df[df[filt[0]] == filt[1]]
        t = standardize(part, ["year", "state_code", "state"], weights)
        t["group"] = name
        records.append(t)
    t = pd.concat(records)

    other = t[~t["state_code"].isin(state_abbr)]
    t = t[t["state_code"].isin(state_abbr)].copy()
    t["abbr"] = t["state_code"].map(state_abbr)

    section("8. Map data (All, age-standardized), lowest and highest states per year")
    for y in years:
        p = t[(t["year"] == y) & (t["group"] == "All")].sort_values("std_risk")
        print(f"{y}: lowest {p.iloc[0]['state']} {p.iloc[0]['std_risk']:.4f}, "
              f"highest {p.iloc[-1]['state']} {p.iloc[-1]['std_risk']:.4f}")
    print("not on the map (no state location):")
    show(other[other["group"] == "All"][["year", "state_code", "state", "n_at_risk", "n_hospitalized", "risk", "std_risk"]].round(4))

    data = {}
    for (y, g), p in t.groupby(["year", "group"]):
        data[f"{y}|{g}"] = [
            {"abbr": r.abbr, "state": r.state, "n": int(r.n_at_risk), "hosp": int(r.n_hospitalized),
             "crude": round(r.risk, 6), "std": None if pd.isna(r.std_risk) else round(r.std_risk, 6)}
            for r in p.itertuples()
        ]
    other_note = ", ".join(
        f"{int(r.year)}: {int(r.n_at_risk):,} at risk, crude risk {r.risk:.1%}"
        for r in other[other["group"] == "All"].itertuples())

    html = map_template.replace("__DATA__", json.dumps(data)) \
                       .replace("__GROUPS__", json.dumps([g for g, _ in groups])) \
                       .replace("__MIN_N__", str(min_n_map)) \
                       .replace("__OTHER__", other_note) \
                       .replace("__RAMP__", json.dumps([[i / (len(blue_ramp) - 1), c] for i, c in enumerate(blue_ramp)]))
    (eda_dir / "risk_map.html").write_text(html)
    print("saved output/eda/risk_map.html")


map_template = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hospitalization Risk Map</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  body { font-family: system-ui, -apple-system, sans-serif; margin: 24px; color: #0b0b0b; background: #fcfcfb; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  p { color: #52514e; font-size: 14px; margin: 4px 0; max-width: 900px; }
  .controls { display: flex; gap: 16px; margin: 16px 0 8px; flex-wrap: wrap; }
  label { font-size: 14px; color: #52514e; }
  select { font-size: 14px; padding: 4px 8px; margin-left: 6px; }
  #map { width: 100%; max-width: 1000px; height: 560px; }
</style>
</head>
<body>
<h1>All-cause hospitalization risk by state, age-standardized</h1>
<p>CMS DE-SynPUF (synthetic Medicare data). People with 0 HMO months, alive on Jan 1.
Color shows age-standardized risk (standard: pooled 2008-2010 at-risk age mix). Hover for crude risk and counts.
Grey: fewer than __MIN_N__ people at risk in the selected group, or an age group with no one in it.</p>
<div class="controls">
  <label>Year <select id="year"><option>2008</option><option>2009</option><option>2010</option></select></label>
  <label>Group <select id="group"></select></label>
</div>
<div id="map"></div>
<p>Not on the map: SSA state code 54 ("Other") - __OTHER__.</p>
<script>
const data = __DATA__;
const groups = __GROUPS__;
const minN = __MIN_N__;
const ramp = __RAMP__;
const groupSel = document.getElementById("group");
groups.forEach(g => groupSel.add(new Option(g, g)));

// one color scale for every year and group, so colors are comparable
let lo = Infinity, hi = -Infinity;
Object.values(data).flat().forEach(r => {
  if (r.std !== null && r.n >= minN) { lo = Math.min(lo, r.std); hi = Math.max(hi, r.std); }
});

const pctFmt = v => v === null ? "n/a" : (100 * v).toFixed(1) + "%";
const hover = r => `<b>${r.state}</b><br>Age-standardized: ${pctFmt(r.std)}<br>Crude: ${pctFmt(r.crude)}` +
                   `<br>Hospitalized: ${r.hosp.toLocaleString()}<br>At risk: ${r.n.toLocaleString()}`;

function draw() {
  const rows = data[`${document.getElementById("year").value}|${groupSel.value}`];
  const shown = rows.filter(r => r.std !== null && r.n >= minN);
  const grey = rows.filter(r => !(r.std !== null && r.n >= minN));
  const traces = [
    { type: "choropleth", locationmode: "USA-states", locations: shown.map(r => r.abbr),
      z: shown.map(r => r.std), zmin: lo, zmax: hi, colorscale: ramp,
      text: shown.map(hover), hoverinfo: "text", marker: { line: { color: "#fcfcfb", width: 1 } },
      colorbar: { title: { text: "Risk" }, tickformat: ".0%" } },
    { type: "choropleth", locationmode: "USA-states", locations: grey.map(r => r.abbr),
      z: grey.map(() => 0), colorscale: [[0, "#d6d5d0"], [1, "#d6d5d0"]], showscale: false,
      text: grey.map(r => hover(r) + "<br><i>Too few people to show</i>"), hoverinfo: "text",
      marker: { line: { color: "#fcfcfb", width: 1 } } },
  ];
  const layout = { geo: { scope: "usa", bgcolor: "rgba(0,0,0,0)" }, margin: { l: 0, r: 0, t: 10, b: 0 },
                   paper_bgcolor: "rgba(0,0,0,0)", font: { family: "system-ui, sans-serif" } };
  Plotly.react("map", traces, layout, { displayModeBar: false, responsive: true });
}
document.getElementById("year").addEventListener("change", draw);
groupSel.addEventListener("change", draw);
draw();
</script>
</body>
</html>
"""


def main():
    eda_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(risk_file)
    print(f"rows in {risk_file.name}: {len(df):,}")

    weights = age_weights(df)
    section("Standard age weights (pooled 2008-2010 at-risk population)")
    show(weights.round(4).to_frame("weight"))

    people, claims = raw_counts()
    chart_flow(df, people)
    chart_year(df, claims)
    chart_age(df)
    chart_sex_age(df)
    chart_race(df, weights)
    chart_group_sizes(df)
    chart_heatmap(df)
    build_map(df, weights)


if __name__ == "__main__":
    main()