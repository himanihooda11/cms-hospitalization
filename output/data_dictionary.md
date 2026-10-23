# Data dictionary: `hospitalization_risk`

Files: `output/hospitalization_risk.csv` and `output/hospitalization_risk.parquet` (same content).
Built by: `scripts/02_build_risk.py`. Checked by: `scripts/03_validate.py`.

## Overview

| | |
|---|---|
| One row | One year × state × sex × race × age group |
| Rows | 6,943 |
| Years | 2008, 2009, 2010 |
| Source | CMS DE-SynPUF (synthetic Medicare data), samples 1-20 |
| Measure | All-cause inpatient hospitalization risk: share of people at risk with at least one inpatient admission in the year |

## Columns

| Column | Type | Description | Example |
|---|---|---|---|
| `year` | integer | Calendar year. Taken from the beneficiary file name (not a column in the raw files) | 2008 |
| `state_code` | integer | `SP_STATE_CODE` from the beneficiary file. SSA state code, not FIPS | 1 |
| `state` | text | State name for `state_code` (see State codes) | Alabama |
| `sex_code` | integer | `BENE_SEX_IDENT_CD` | 1 |
| `sex` | text | Label for `sex_code` | Male |
| `race_code` | integer | `BENE_RACE_CD` | 1 |
| `race` | text | Label for `race_code` | White |
| `age_group` | text | Age group, age on Dec 31 of `year` | <65 |
| `n_at_risk` | integer | Denominator: people at risk in the group (see Definitions) | 2287 |
| `n_hospitalized` | integer | Numerator: people at risk with at least one inpatient admission in `year` | 357 |
| `risk` | decimal | `n_hospitalized / n_at_risk`, not rounded | 0.15609969392216877 |

## Codes

**Sex (`sex_code`)**

| Code | Label |
|---|---|
| 1 | Male |
| 2 | Female |

**Race (`race_code`)**. There is no code 4 in the data.

| Code | Label |
|---|---|
| 1 | White |
| 2 | Black |
| 3 | Other |
| 5 | Hispanic |

**Age group (`age_group`)**. Fixed before looking at results: under 65 as one group (Medicare eligibility starts at 65 for most people), then 5-year bands, with 90 and older as the last group.

`<65`, `65-69`, `70-74`, `75-79`, `80-84`, `85-89`, `90+`

**State (`state_code`)**. SSA codes 1-53 are mapped to names using the CMS state code list. Code 54 is outside the 1-53 state range and is labeled `Other`. Codes 40 (Puerto Rico) and 48 (Virgin Islands) do not appear in the data.

| Code | State | Code | State | Code | State |
|---|---|---|---|---|---|
| 1 | Alabama | 19 | Louisiana | 37 | Oklahoma |
| 2 | Alaska | 20 | Maine | 38 | Oregon |
| 3 | Arizona | 21 | Maryland | 39 | Pennsylvania |
| 4 | Arkansas | 22 | Massachusetts | 41 | Rhode Island |
| 5 | California | 23 | Michigan | 42 | South Carolina |
| 6 | Colorado | 24 | Minnesota | 43 | South Dakota |
| 7 | Connecticut | 25 | Mississippi | 44 | Tennessee |
| 8 | Delaware | 26 | Missouri | 45 | Texas |
| 9 | District of Columbia | 27 | Montana | 46 | Utah |
| 10 | Florida | 28 | Nebraska | 47 | Vermont |
| 11 | Georgia | 29 | Nevada | 49 | Virginia |
| 12 | Hawaii | 30 | New Hampshire | 50 | Washington |
| 13 | Idaho | 31 | New Jersey | 51 | West Virginia |
| 14 | Illinois | 32 | New Mexico | 52 | Wisconsin |
| 15 | Indiana | 33 | New York | 53 | Wyoming |
| 16 | Iowa | 34 | North Carolina | 54 | Other |
| 17 | Kansas | 35 | North Dakota | | |
| 18 | Kentucky | 36 | Ohio | | |

## Definitions

- **At risk (denominator):** person is in that year's beneficiary file, is alive on Jan 1 of the year (`BENE_DEATH_DT` blank or on/after Jan 1), and has 0 months of HMO coverage that year (`BENE_HMO_CVRAGE_TOT_MONS = 0`). People who die during the year are kept for that year.
- **Hospitalized (numerator):** person is at risk and has at least one inpatient claim with `CLM_ADMSN_DT` in that year. Each `CLM_ID` is counted once; a claim split over several rows uses its earliest admission date. A person counts once per year, however many admissions they have.
- **Age:** `year` minus birth year (age on Dec 31 of the year).
- **Risk:** `n_hospitalized / n_at_risk`. Risk for combined groups (e.g. a whole state) is total `n_hospitalized` / total `n_at_risk`, not the average of group risks.

## Counts

**Beneficiaries**

| | 2008 | 2009 | 2010 |
|---|---|---|---|
| Rows in beneficiary files | 2,326,856 | 2,291,320 | 2,255,098 |
| Excluded: HMO months > 0 | 537,601 | 668,796 | 732,810 |
| Excluded: died before Jan 1 | 0 | 0 | 0 |
| Excluded: missing birth date | 0 | 0 | 0 |
| At risk (`n_at_risk` total) | 1,789,255 | 1,622,524 | 1,522,288 |

**Hospitalizations**

| | 2008 | 2009 | 2010 |
|---|---|---|---|
| People with an admission in the year (all) | 317,940 | 375,814 | 235,418 |
| Of these, not at risk (HMO months > 0) | 78,399 | 113,231 | 83,078 |
| Hospitalized (`n_hospitalized` total) | 239,541 | 262,583 | 152,340 |
| Risk (all groups combined) | 0.1339 | 0.1618 | 0.1001 |

**Inpatient claims**

| | |
|---|---|
| Rows in inpatient files | 1,332,822 |
| Unique `CLM_ID` | 1,331,533 |
| Claims with different admission dates across rows | 1,100 (80 of them in two different years) |
| Missing `CLM_ADMSN_DT` | 0 |
| Claims by admission year | 2007: 4,318 (not used) · 2008: 551,828 · 2009: 502,467 · 2010: 272,920 |

**People at risk by age group (2008-2010 combined)**

| <65 | 65-69 | 70-74 | 75-79 | 80-84 | 85-89 | 90+ |
|---|---|---|---|---|---|---|
| 759,832 | 1,013,114 | 986,574 | 794,397 | 641,617 | 428,069 | 310,464 |

## Limitations

- **Synthetic data.** DE-SynPUF is synthetic; it has limited inferential research value and is meant for developing and testing tools (assignment background).
- **2010 claims.** There are 272,920 claims with a 2010 admission date, compared with 551,828 for 2008. 2010 risk values should be read with this in mind.
- **Small groups.** 640 of 6,943 rows have fewer than 11 people at risk. Risk in these rows is unstable (values of 0 and 1 occur). CMS cell-size rules for real data suppress counts under 11.
- **HMO exclusion.** People with any HMO months are not in the denominator (23.1% in 2008, 29.2% in 2009, 32.5% in 2010), so the output describes people with fee-for-service coverage only.
- **2007 admissions.** 4,318 claims with a 2007 admission date are outside 2008-2010 and not counted.

## Source files

Downloaded from the CMS DE-SynPUF page on October 22, 2026 by `scripts/01_download.py`.

| Files | Count | Columns used |
|---|---|---|
| `DE1_0_{2008,2009,2010}_Beneficiary_Summary_File_Sample_{1-20}.csv` | 60 | `DESYNPUF_ID`, `BENE_BIRTH_DT`, `BENE_DEATH_DT`, `BENE_SEX_IDENT_CD`, `BENE_RACE_CD`, `SP_STATE_CODE`, `BENE_HMO_CVRAGE_TOT_MONS` (YEAR from file name) |
| `DE1_0_2008_to_2010_Inpatient_Claims_Sample_{1-20}.csv` | 20 | `CLM_ID`, `DESYNPUF_ID`, `CLM_ADMSN_DT` |

The 2010 Sample 1 beneficiary file returns 404 at the standard URL. It was downloaded from an alternate CMS link (file named `..._Sample_20.zip`) and saved as Sample 1. Its contents were checked: 100% of its IDs are in 2009 Sample 1 and 0% are in 2010 Sample 20.
