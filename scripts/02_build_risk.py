# Task 2: yearly state-level all-cause hospitalization risk,
# stratified by sex, race and age group.
#
# Reads the csvs in files/csv/ with DuckDB and writes
#   output/hospitalization_risk.csv
#   output/hospitalization_risk.parquet
# with one row per year / state / sex / race / age group.
#
# Definitions
#   at risk      : in that year's beneficiary file, alive on Jan 1 of the year,
#                  0 months of HMO coverage that year
#   hospitalized : at least one inpatient admission (CLM_ADMSN_DT) in that year
#   risk         : hospitalized / at risk
#
# Usage: python scripts/02_build_risk.py

from pathlib import Path

import duckdb

root = Path(__file__).resolve().parents[1]
csv_dir = root / "files" / "csv"
out_dir = root / "output"

# Age groups are fixed here, before looking at results: <65, 65-69, ..., 85-89, 90+
age_start = 65  # Medicare eligibility age; everyone younger is one group (disability)
age_step = 5
age_top = 90    # 90 and older is the last group

bene_files = str(csv_dir / "DE1_0_*_Beneficiary_Summary_File_Sample_*.csv")
claim_files = str(csv_dir / "DE1_0_2008_to_2010_Inpatient_Claims_Sample_*.csv")

# SSA state codes used in SP_STATE_CODE (not FIPS). Source: CMS BENE_STATE_CD codebook.
# Any other code (e.g. 54) is labeled "Other".
state_names = {
    1: "Alabama", 2: "Alaska", 3: "Arizona", 4: "Arkansas", 5: "California",
    6: "Colorado", 7: "Connecticut", 8: "Delaware", 9: "District of Columbia",
    10: "Florida", 11: "Georgia", 12: "Hawaii", 13: "Idaho", 14: "Illinois",
    15: "Indiana", 16: "Iowa", 17: "Kansas", 18: "Kentucky", 19: "Louisiana",
    20: "Maine", 21: "Maryland", 22: "Massachusetts", 23: "Michigan",
    24: "Minnesota", 25: "Mississippi", 26: "Missouri", 27: "Montana",
    28: "Nebraska", 29: "Nevada", 30: "New Hampshire", 31: "New Jersey",
    32: "New Mexico", 33: "New York", 34: "North Carolina", 35: "North Dakota",
    36: "Ohio", 37: "Oklahoma", 38: "Oregon", 39: "Pennsylvania",
    40: "Puerto Rico", 41: "Rhode Island", 42: "South Carolina",
    43: "South Dakota", 44: "Tennessee", 45: "Texas", 46: "Utah",
    47: "Vermont", 48: "Virgin Islands", 49: "Virginia", 50: "Washington",
    51: "West Virginia", 52: "Wisconsin", 53: "Wyoming",
}


def section(title):
    print(f"\n=== {title} ===")


def load_beneficiaries(con):
    # Stack the 60 beneficiary files into one table, keeping only the needed columns.
    # Everything is read as text first, then cast, so all files are parsed the same way.
    # YEAR is not in the files, it comes from the file name.
    con.execute(f"""
        CREATE TABLE bene AS
        SELECT
            CAST(regexp_extract(filename, 'DE1_0_(\\d{{4}})_Beneficiary', 1) AS INTEGER) AS YEAR,
            DESYNPUF_ID,
            CAST(try_strptime(BENE_BIRTH_DT, '%Y%m%d') AS DATE) AS BENE_BIRTH_DT,
            CAST(try_strptime(BENE_DEATH_DT, '%Y%m%d') AS DATE) AS BENE_DEATH_DT,
            CAST(BENE_SEX_IDENT_CD AS INTEGER) AS BENE_SEX_IDENT_CD,
            CAST(BENE_RACE_CD AS INTEGER) AS BENE_RACE_CD,
            CAST(SP_STATE_CODE AS INTEGER) AS SP_STATE_CODE,
            CAST(BENE_HMO_CVRAGE_TOT_MONS AS INTEGER) AS BENE_HMO_CVRAGE_TOT_MONS
        FROM read_csv('{bene_files}', all_varchar = true, filename = true)
    """)

    section("Beneficiary rows per year (compare with assignment: 2,326,856 / 2,291,320 / 2,255,098)")
    con.sql("""
        SELECT YEAR,
               count(*) AS n_rows,
               count(DISTINCT DESYNPUF_ID) AS n_unique_ids,
               count(*) - count(DISTINCT DESYNPUF_ID) AS n_duplicate_ids,
               count(*) FILTER (WHERE BENE_BIRTH_DT IS NULL) AS missing_birth_dt
        FROM bene GROUP BY YEAR ORDER BY YEAR
    """).show()

    section("Codes found (sex, race, state)")
    con.sql("SELECT BENE_SEX_IDENT_CD, count(*) AS n FROM bene GROUP BY 1 ORDER BY 1").show()
    con.sql("SELECT BENE_RACE_CD, count(*) AS n FROM bene GROUP BY 1 ORDER BY 1").show()
    con.sql("""
        SELECT min(SP_STATE_CODE) AS min_code, max(SP_STATE_CODE) AS max_code,
               count(DISTINCT SP_STATE_CODE) AS n_codes
        FROM bene
    """).show()


def build_at_risk(con):
    # People at risk each year: alive on Jan 1 of that year and fully fee-for-service
    # (0 HMO months), since HMO members' hospital stays are not in these claims.
    # Age is taken on Dec 31 of the year, which is simply YEAR - birth year.
    # Age groups: <65, then 5-year bands from 65, with everyone 90+ in the last group.
    con.execute(f"""
        CREATE TABLE at_risk AS
        WITH b AS (
            SELECT *, YEAR - year(BENE_BIRTH_DT) AS age
            FROM bene
            WHERE (BENE_DEATH_DT IS NULL OR BENE_DEATH_DT >= make_date(YEAR, 1, 1))
              AND BENE_HMO_CVRAGE_TOT_MONS = 0
              AND BENE_BIRTH_DT IS NOT NULL
        )
        SELECT *,
               CASE
                   WHEN age < {age_start} THEN '<{age_start}'
                   WHEN age >= {age_top} THEN '{age_top}+'
                   ELSE CAST({age_start} + (age - {age_start}) // {age_step} * {age_step} AS VARCHAR)
                        || '-' ||
                        CAST({age_start} + (age - {age_start}) // {age_step} * {age_step} + {age_step} - 1 AS VARCHAR)
               END AS age_group
        FROM b
    """)

    section("Who was excluded and why (a person can fall in more than one column)")
    con.sql("""
        SELECT YEAR,
               count(*) AS in_file,
               count(*) FILTER (WHERE BENE_DEATH_DT < make_date(YEAR, 1, 1)) AS died_before_year,
               count(*) FILTER (WHERE BENE_HMO_CVRAGE_TOT_MONS > 0) AS any_hmo_months,
               count(*) FILTER (WHERE BENE_BIRTH_DT IS NULL) AS no_birth_dt
        FROM bene GROUP BY YEAR ORDER BY YEAR
    """).show()

    section("At risk per year (denominator)")
    con.sql("""
        SELECT YEAR, count(*) AS n_at_risk, min(age) AS min_age, max(age) AS max_age
        FROM at_risk GROUP BY YEAR ORDER BY YEAR
    """).show()
    con.sql("""
        SELECT age_group, count(*) AS n FROM at_risk GROUP BY 1 ORDER BY min(age)
    """).show()


def load_claims(con):
    # Stack the 20 inpatient files. A claim can be split over several rows,
    # so keep one row per CLM_ID (earliest admission date if they differ).
    con.execute(f"""
        CREATE TABLE claims_raw AS
        SELECT CLM_ID,
               DESYNPUF_ID,
               CAST(try_strptime(CLM_ADMSN_DT, '%Y%m%d') AS DATE) AS CLM_ADMSN_DT
        FROM read_csv('{claim_files}', all_varchar = true)
    """)
    con.execute("""
        CREATE TABLE claims AS
        SELECT CLM_ID,
               min(DESYNPUF_ID) AS DESYNPUF_ID,
               min(CLM_ADMSN_DT) AS CLM_ADMSN_DT,
               count(DISTINCT DESYNPUF_ID) AS n_ids
        FROM claims_raw GROUP BY CLM_ID
    """)

    section("Inpatient claims")
    con.sql("""
        SELECT (SELECT count(*) FROM claims_raw) AS raw_rows,
               (SELECT count(*) FROM claims) AS unique_clm_ids,
               (SELECT count(*) FROM claims WHERE n_ids > 1) AS clm_ids_with_2plus_people,
               (SELECT count(*) FROM claims WHERE CLM_ADMSN_DT IS NULL) AS missing_admsn_dt
    """).show()

    section("Claims by admission year (only 2008-2010 are used)")
    con.sql("""
        SELECT year(CLM_ADMSN_DT) AS admsn_year, count(*) AS n_claims
        FROM claims GROUP BY 1 ORDER BY 1
    """).show()


def build_hospitalized(con):
    # One row per person per year with at least one admission.
    con.execute("""
        CREATE TABLE hosp AS
        SELECT DISTINCT DESYNPUF_ID, year(CLM_ADMSN_DT) AS YEAR
        FROM claims
        WHERE CLM_ADMSN_DT IS NOT NULL
          AND year(CLM_ADMSN_DT) BETWEEN 2008 AND 2010
    """)

    section("Hospitalized person-years and how they match the beneficiary files")
    con.sql("""
        SELECT h.YEAR,
               count(*) AS hospitalized_person_years,
               count(*) FILTER (WHERE b.DESYNPUF_ID IS NULL) AS not_in_bene_file,
               count(*) FILTER (WHERE b.DESYNPUF_ID IS NOT NULL AND a.DESYNPUF_ID IS NULL) AS in_file_but_excluded,
               count(a.DESYNPUF_ID) AS counted_in_numerator
        FROM hosp h
        LEFT JOIN (SELECT DISTINCT YEAR, DESYNPUF_ID FROM bene) b
               ON h.DESYNPUF_ID = b.DESYNPUF_ID AND h.YEAR = b.YEAR
        LEFT JOIN (SELECT DISTINCT YEAR, DESYNPUF_ID FROM at_risk) a
               ON h.DESYNPUF_ID = a.DESYNPUF_ID AND h.YEAR = a.YEAR
        GROUP BY h.YEAR ORDER BY h.YEAR
    """).show()


def build_risk(con):
    # Left join keeps everyone at risk; people with no admission count as not hospitalized.
    con.execute("CREATE TABLE state_names (code INTEGER, state VARCHAR)")
    con.executemany("INSERT INTO state_names VALUES (?, ?)", list(state_names.items()))

    con.execute("""
        CREATE TABLE risk AS
        SELECT a.YEAR AS year,
               a.SP_STATE_CODE AS state_code,
               coalesce(s.state, 'Other') AS state,
               a.BENE_SEX_IDENT_CD AS sex_code,
               CASE a.BENE_SEX_IDENT_CD WHEN 1 THEN 'Male' WHEN 2 THEN 'Female' ELSE 'Unknown' END AS sex,
               a.BENE_RACE_CD AS race_code,
               CASE a.BENE_RACE_CD WHEN 1 THEN 'White' WHEN 2 THEN 'Black'
                                   WHEN 3 THEN 'Other' WHEN 5 THEN 'Hispanic' ELSE 'Unknown' END AS race,
               a.age_group,
               count(*) AS n_at_risk,
               count(h.DESYNPUF_ID) AS n_hospitalized,
               count(h.DESYNPUF_ID) / count(*) AS risk
        FROM at_risk a
        LEFT JOIN hosp h ON a.DESYNPUF_ID = h.DESYNPUF_ID AND a.YEAR = h.YEAR
        LEFT JOIN state_names s ON a.SP_STATE_CODE = s.code
        GROUP BY ALL
        ORDER BY year, state_code, sex_code, race_code, min(a.age)
    """)

    section("Overall risk per year")
    con.sql("""
        SELECT year, sum(n_at_risk) AS n_at_risk, sum(n_hospitalized) AS n_hospitalized,
               round(sum(n_hospitalized) / sum(n_at_risk), 4) AS risk
        FROM risk GROUP BY year ORDER BY year
    """).show()

    section("Output table")
    con.sql("""
        SELECT count(*) AS n_strata,
               count(*) FILTER (WHERE n_at_risk < 11) AS strata_under_11_people,
               sum(n_at_risk) AS total_at_risk,
               min(risk) AS min_risk, max(risk) AS max_risk
        FROM risk
    """).show()
    con.sql("SELECT * FROM risk LIMIT 10").show()


def save(con):
    out_dir.mkdir(exist_ok=True)
    csv_out = out_dir / "hospitalization_risk.csv"
    parquet_out = out_dir / "hospitalization_risk.parquet"
    con.execute(f"COPY risk TO '{csv_out}' (HEADER)")
    con.execute(f"COPY risk TO '{parquet_out}' (FORMAT parquet)")
    print(f"\nsaved {csv_out}")
    print(f"saved {parquet_out}")


def main():
    con = duckdb.connect()
    con.execute(f"SET temp_directory = '{root / 'files' / 'duckdb_tmp'}'")  # spill to disk if memory runs out
    load_beneficiaries(con)
    build_at_risk(con)
    load_claims(con)
    build_hospitalized(con)
    build_risk(con)
    save(con)


if __name__ == "__main__":
    main()