# Task 3: validation checks for output/hospitalization_risk.csv
#
# 1. Inputs     : all 80 files present, row counts match the assignment
# 2. Raw data   : duplicate IDs, valid codes, claim IDs belong to one person
# 3. Output     : no duplicate strata, no blanks, risk = n_hospitalized / n_at_risk
# 4. Recount    : every stratum is recounted from the raw csvs with plain Python
#                 (not DuckDB, not the Task 2 code) and compared to the output
# 5. Spot-check : a few strata shown in detail, with example IDs and source files
#
# Prints PASS/FAIL for each check, saves output/validation_report.txt,
# and exits with an error if any check fails.
#
# Usage: python scripts/03_validate.py

import csv
import random
import sys
from collections import defaultdict
from pathlib import Path

import duckdb

root = Path(__file__).resolve().parents[1]
csv_dir = root / "files" / "csv"
output_file = root / "output" / "hospitalization_risk.csv"
report_file = root / "output" / "validation_report.txt"

years = [2008, 2009, 2010]
samples = range(1, 21)

# from the assignment's data description table
expected_bene_rows = {2008: 2326856, 2009: 2291320, 2010: 2255098}
expected_claim_rows = 547800 + 504941 + 280081

# same rules as Task 2, written again here on purpose
age_start, age_step, age_top = 65, 5, 90

# spot-checks: one picked by hand (year, state_code, sex_code, race_code, age_group),
# plus a few picked at random with a fixed seed so the run is repeatable
hand_picked = [(2009, 31, 2, 1, "75-79")]  # 2009, New Jersey, Female, White, 75-79
n_random = 3
seed = 42

report = []
results = []


def log(text=""):
    print(text)
    report.append(text)


def check(name, ok, detail=""):
    results.append((name, ok))
    log(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


def bene_file(year, s):
    return csv_dir / f"DE1_0_{year}_Beneficiary_Summary_File_Sample_{s}.csv"


def claim_file(s):
    return csv_dir / f"DE1_0_2008_to_2010_Inpatient_Claims_Sample_{s}.csv"


def age_group(age):
    if age < age_start:
        return f"<{age_start}"
    if age >= age_top:
        return f"{age_top}+"
    low = age_start + (age - age_start) // age_step * age_step
    return f"{low}-{low + age_step - 1}"


def check_inputs():
    log("\n=== 1. Input files ===")
    missing = [f.name for y in years for s in samples if not (f := bene_file(y, s)).exists()]
    missing += [f.name for s in samples if not (f := claim_file(s)).exists()]
    check("all 60 beneficiary + 20 inpatient files present", not missing, f"missing: {missing}" if missing else "80 files")
    if missing:
        log("cannot continue without all files")
        finish()


def check_raw(con):
    # Uses DuckDB on the raw csvs directly, not the Task 2 tables.
    log("\n=== 2. Raw data ===")
    con.execute(f"""
        CREATE TABLE bene AS
        SELECT CAST(regexp_extract(filename, '_(\\d{{4}})_Beneficiary', 1) AS INTEGER) AS year,
               CAST(regexp_extract(filename, 'Sample_(\\d+)', 1) AS INTEGER) AS sample,
               DESYNPUF_ID, BENE_BIRTH_DT, BENE_SEX_IDENT_CD, BENE_RACE_CD, SP_STATE_CODE
        FROM read_csv('{csv_dir}/DE1_0_*_Beneficiary_Summary_File_*.csv', all_varchar = true, filename = true)
    """)
    con.execute(f"""
        CREATE TABLE claims AS
        SELECT CLM_ID, DESYNPUF_ID, CLM_ADMSN_DT
        FROM read_csv('{csv_dir}/DE1_0_2008_to_2010_Inpatient_Claims_*.csv', all_varchar = true)
    """)

    for year, n_exp in expected_bene_rows.items():
        n = con.execute("SELECT count(*) FROM bene WHERE year = ?", [year]).fetchone()[0]
        check(f"{year} beneficiary rows match assignment", n == n_exp, f"{n:,} vs {n_exp:,}")

    n = con.execute("SELECT count(*) FROM claims").fetchone()[0]
    check("inpatient rows match assignment", n == expected_claim_rows, f"{n:,} vs {expected_claim_rows:,}")

    n = con.execute("""
        SELECT count(*) FROM (SELECT year, DESYNPUF_ID FROM bene GROUP BY ALL HAVING count(*) > 1)
    """).fetchone()[0]
    check("no duplicate DESYNPUF_ID within a year", n == 0, f"{n} duplicates")

    n = con.execute("""
        SELECT count(*) FROM (SELECT DESYNPUF_ID FROM bene GROUP BY 1 HAVING count(DISTINCT sample) > 1)
    """).fetchone()[0]
    check("no DESYNPUF_ID in more than one sample", n == 0, f"{n} IDs")

    n = con.execute("SELECT count(*) FROM bene WHERE BENE_SEX_IDENT_CD NOT IN ('1', '2')").fetchone()[0]
    check("sex codes are 1 or 2", n == 0, f"{n} other")

    n = con.execute("SELECT count(*) FROM bene WHERE BENE_RACE_CD NOT IN ('1', '2', '3', '5')").fetchone()[0]
    check("race codes are 1, 2, 3 or 5", n == 0, f"{n} other")

    n = con.execute("""
        SELECT count(*) FROM bene WHERE TRY_CAST(SP_STATE_CODE AS INTEGER) NOT BETWEEN 1 AND 54
                                    OR TRY_CAST(SP_STATE_CODE AS INTEGER) IS NULL
    """).fetchone()[0]
    check("state codes are 1-54", n == 0, f"{n} other")

    n = con.execute("SELECT count(*) FROM bene WHERE try_strptime(BENE_BIRTH_DT, '%Y%m%d') IS NULL").fetchone()[0]
    check("every beneficiary has a valid birth date", n == 0, f"{n} missing/invalid")

    lo, hi = con.execute("""
        SELECT min(year - CAST(left(BENE_BIRTH_DT, 4) AS INTEGER)),
               max(year - CAST(left(BENE_BIRTH_DT, 4) AS INTEGER)) FROM bene
    """).fetchone()
    check("ages are in a sensible range (18-110)", 18 <= lo and hi <= 110, f"{lo} to {hi}")

    n = con.execute("""
        SELECT count(*) FROM (SELECT CLM_ID FROM claims GROUP BY 1 HAVING count(DISTINCT DESYNPUF_ID) > 1)
    """).fetchone()[0]
    check("each CLM_ID belongs to one person", n == 0, f"{n} claims")

    n = con.execute("""
        SELECT count(*) FROM claims c
        WHERE NOT EXISTS (SELECT 1 FROM bene b WHERE b.DESYNPUF_ID = c.DESYNPUF_ID)
    """).fetchone()[0]
    check("every claim's DESYNPUF_ID is in a beneficiary file", n == 0, f"{n} claims")


def check_output(con):
    log("\n=== 3. Output table ===")
    con.execute(f"CREATE TABLE out AS SELECT * FROM read_csv('{output_file}', header = true)")
    log(f"rows in output: {con.execute('SELECT count(*) FROM out').fetchone()[0]:,}")

    n = con.execute("""
        SELECT count(*) FROM (SELECT year, state_code, sex_code, race_code, age_group
                              FROM out GROUP BY ALL HAVING count(*) > 1)
    """).fetchone()[0]
    check("one row per year-state-sex-race-age group", n == 0, f"{n} duplicated")

    cols = [r[0] for r in con.execute("DESCRIBE out").fetchall()]
    any_null = " OR ".join(f'"{c}" IS NULL' for c in cols)
    n = con.execute(f"SELECT count(*) FROM out WHERE {any_null}").fetchone()[0]
    check("no empty values", n == 0, f"{n} rows")

    n = con.execute("SELECT count(*) FROM out WHERE n_hospitalized > n_at_risk OR n_at_risk <= 0").fetchone()[0]
    check("0 < n_at_risk and n_hospitalized <= n_at_risk", n == 0, f"{n} rows")

    n = con.execute("SELECT count(*) FROM out WHERE risk < 0 OR risk > 1").fetchone()[0]
    check("risk between 0 and 1", n == 0, f"{n} rows")

    # tiny tolerance only for float rounding when the csv is written and read back
    n = con.execute("SELECT count(*) FROM out WHERE abs(risk - n_hospitalized / n_at_risk) > 1e-12").fetchone()[0]
    check("risk = n_hospitalized / n_at_risk", n == 0, f"{n} rows")

    groups = {r[0] for r in con.execute("SELECT DISTINCT age_group FROM out").fetchall()}
    expected = {age_group(a) for a in range(18, 111)}
    check("age groups are the prespecified ones", groups == expected, ", ".join(sorted(groups)))


def recount_from_raw():
    # Independent recount with the csv module, same definitions as Task 2:
    # hospitalized = (person, year) with an admission in 2008-2010, one admission
    #                date per claim (a claim split over rows uses its earliest date)
    # at risk      = in that year's file, alive on Jan 1, 0 HMO months
    log("\n=== 4. Recount from raw csvs (plain Python) ===")

    claims = {}                  # CLM_ID -> (DESYNPUF_ID, earliest admission date)
    dates_seen = defaultdict(set)  # CLM_ID -> all admission dates on its rows
    for s in samples:
        with open(claim_file(s), newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            i_clm, i_id, i_adm = (header.index(c) for c in ["CLM_ID", "DESYNPUF_ID", "CLM_ADMSN_DT"])
            for row in reader:
                clm, adm = row[i_clm], row[i_adm].strip()
                dates_seen[clm].add(adm)
                if clm not in claims or (adm and adm < claims[clm][1]):
                    claims[clm] = (row[i_id], adm)

    split = [d for d in dates_seen.values() if len(d) > 1]
    log(f"claims with different admission dates across rows: {len(split):,}"
        f" ({sum(len({x[:4] for x in d}) > 1 for d in split):,} of them span two years;"
        f" each claim counted once at its earliest date)")

    hosp = {(pid, int(adm[:4])) for pid, adm in claims.values() if adm[:4] in ("2008", "2009", "2010")}
    log(f"hospitalized person-years (any eligibility): {len(hosp):,}")

    counts = defaultdict(lambda: [0, 0])  # stratum -> [n_at_risk, n_hospitalized]
    members = defaultdict(list)           # stratum -> [(id, file, hospitalized)], kept for spot-checks
    for year in years:
        for s in samples:
            path = bene_file(year, s)
            with open(path, newline="") as f:
                reader = csv.reader(f)
                header = next(reader)
                idx = {c: header.index(c) for c in ["DESYNPUF_ID", "BENE_BIRTH_DT", "BENE_DEATH_DT",
                                                     "BENE_SEX_IDENT_CD", "BENE_RACE_CD",
                                                     "SP_STATE_CODE", "BENE_HMO_CVRAGE_TOT_MONS"]}
                for row in reader:
                    death = row[idx["BENE_DEATH_DT"]].strip()
                    if death and death < f"{year}0101":
                        continue
                    if int(row[idx["BENE_HMO_CVRAGE_TOT_MONS"]]) != 0:
                        continue
                    pid = row[idx["DESYNPUF_ID"]]
                    age = year - int(row[idx["BENE_BIRTH_DT"]][:4])
                    key = (year, int(row[idx["SP_STATE_CODE"]]), int(row[idx["BENE_SEX_IDENT_CD"]]),
                           int(row[idx["BENE_RACE_CD"]]), age_group(age))
                    was_hosp = (pid, year) in hosp
                    counts[key][0] += 1
                    counts[key][1] += was_hosp
                    members[key].append((pid, path.name, was_hosp))
        log(f"  read {year} beneficiary files")
    return counts, members


def compare_all(con, counts):
    out = {(r[0], r[1], r[2], r[3], r[4]): (r[5], r[6])
           for r in con.execute("""SELECT year, state_code, sex_code, race_code, age_group,
                                          n_at_risk, n_hospitalized FROM out""").fetchall()}

    only_raw = set(counts) - set(out)
    only_out = set(out) - set(counts)
    check("same set of strata in raw recount and output", not only_raw and not only_out,
          f"{len(counts):,} raw, {len(out):,} output")

    diff = [k for k in counts if k in out and tuple(counts[k]) != out[k]]
    check("every stratum: n_at_risk and n_hospitalized match raw recount", not diff, f"{len(diff)} differ")

    for year in years:
        raw_d = sum(v[0] for k, v in counts.items() if k[0] == year)
        raw_n = sum(v[1] for k, v in counts.items() if k[0] == year)
        out_d = sum(v[0] for k, v in out.items() if k[0] == year)
        out_n = sum(v[1] for k, v in out.items() if k[0] == year)
        check(f"{year} totals match raw recount", (raw_d, raw_n) == (out_d, out_n),
              f"at risk {raw_d:,} raw / {out_d:,} output, "
              f"hospitalized {raw_n:,} raw / {out_n:,} output, risk {out_n / out_d:.4f}")
    return out


def spot_check(con, counts, members):
    log("\n=== 5. Spot-checks ===")
    big_enough = sorted(k for k, v in counts.items() if v[0] >= 11)
    picks = [k for k in hand_picked if k in counts]
    picks += random.Random(seed).sample(pool := [k for k in big_enough if k not in picks], min(n_random, len(pool)))

    for key in picks:
        year, state, sex, race, group = key
        row = con.execute("""
            SELECT state, sex, race, n_at_risk, n_hospitalized, risk FROM out
            WHERE year = ? AND state_code = ? AND sex_code = ? AND race_code = ? AND age_group = ?
        """, list(key)).fetchone()
        raw_d, raw_n = counts[key]
        log(f"\n{year} | {row[0]} ({state}) | {row[1]} | {row[2]} | {group}")
        log(f"  denominator  raw {raw_d:>7,}   output {row[3]:>7,}")
        log(f"  numerator    raw {raw_n:>7,}   output {row[4]:>7,}")
        log(f"  risk         raw {raw_n / raw_d:.6f}   output {row[5]:.6f}")
        check(f"spot-check {year}/{state}/{sex}/{race}/{group}",
              (raw_d, raw_n) == (row[3], row[4]) and abs(raw_n / raw_d - row[5]) < 1e-12)

        examples = [m for m in members[key] if m[2]][:3] + [m for m in members[key] if not m[2]][:2]
        log("  example IDs (look these up in the raw files):")
        for pid, fname, was_hosp in examples:
            log(f"    {pid}  {fname}  {'hospitalized' if was_hosp else 'not hospitalized'}")


def finish():
    n_fail = sum(not ok for _, ok in results)
    log(f"\n=== Summary: {len(results) - n_fail} passed, {n_fail} failed ===")
    for name, ok in results:
        if not ok:
            log(f"  FAILED: {name}")
    report_file.parent.mkdir(exist_ok=True)
    report_file.write_text("\n".join(report) + "\n")
    print(f"\nreport saved to {report_file}")
    sys.exit(1 if n_fail else 0)


def main():
    con = duckdb.connect()
    check_inputs()
    check_raw(con)
    check_output(con)
    counts, members = recount_from_raw()
    compare_all(con, counts)
    spot_check(con, counts, members)
    finish()


if __name__ == "__main__":
    main()