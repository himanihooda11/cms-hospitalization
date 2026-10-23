# CMS DE-SynPUF: yearly state-level hospitalization risk

This repository downloads the CMS DE-SynPUF synthetic Medicare files (Beneficiary Summary 2008-2010 and Inpatient Claims, samples 1-20), builds yearly state-level all-cause hospitalization risk stratified by sex, race and age group, validates the output against the raw files, and produces exploratory charts and an interactive state map.

## Pipeline

| Step | Script | Output |
|---|---|---|
| 1. Download | `scripts/01_download.py` | 60 beneficiary + 20 inpatient csvs in `files/csv/` (not tracked in git) |
| 2. Build | `scripts/02_build_risk.py` | `output/hospitalization_risk.csv` and `.parquet` |
| 3. Validate | `scripts/03_validate.py` | `output/validation_report.txt` |
| 4. EDA | `scripts/04_eda.py` | 7 charts and `risk_map.html` in `output/eda/` |

`Snakefile` runs the four steps in order. EDA runs only after validation passes.

## Definitions

- **At risk (denominator):** in that year's beneficiary file, alive on Jan 1 of the year, 0 months of HMO coverage.
- **Hospitalized (numerator):** at risk and at least one inpatient admission (`CLM_ADMSN_DT`) in the year. Each claim is counted once, at its earliest admission date.
- **Age group:** age on Dec 31 of the year: `<65`, `65-69`, `70-74`, `75-79`, `80-84`, `85-89`, `90+`.
- **Risk:** hospitalized / at risk.

Columns, codes, counts and limitations are in [`output/data_dictionary.md`](output/data_dictionary.md).

## Results

Output: one row per year × state × sex × race × age group (6,943 rows), with `n_at_risk`, `n_hospitalized` and `risk`.

| Year | At risk | Hospitalized | Risk |
|---|---|---|---|
| 2008 | 1,789,255 | 239,541 | 0.1339 |
| 2009 | 1,622,524 | 262,583 | 0.1618 |
| 2010 | 1,522,288 | 152,340 | 0.1001 |

2010 has 272,920 inpatient claims with a 2010 admission date, compared with 551,828 for 2008.

**Validation:** 29 checks pass, including row counts against the assignment, duplicate IDs, valid codes, a full recount of every stratum from the raw csvs with separate code (all 6,943 match), and four spot-checks with example IDs and source files. See [`output/validation_report.txt`](output/validation_report.txt).

**EDA:** charts in [`output/eda/`](output/eda/). The interactive map (`output/eda/risk_map.html`) shows age-standardized risk by state, with year and group dropdowns; download it and open it in a browser.

## Repository structure

```
├── Snakefile                 # runs the pipeline
├── requirements.txt          # Python packages
├── scripts/
│   ├── 01_download.py
│   ├── 02_build_risk.py
│   ├── 03_validate.py
│   └── 04_eda.py
├── output/
│   ├── hospitalization_risk.csv
│   ├── hospitalization_risk.parquet
│   ├── validation_report.txt
│   ├── data_dictionary.md
│   └── eda/
├── ai_interactions/          # AI tool prompts and transcripts
└── files/                    # raw downloads (created by step 1, ignored by git)
```

## Computing environment

Developed and run on:

- macOS 26.6.2, Apple Silicon (arm64)
- Python 3.13.15

Python packages (pinned in `requirements.txt`):

| Package | Version | Used for |
|---|---|---|
| requests | 2.34.2 | downloading the CMS files |
| duckdb | 2.0.0 | loading and aggregating the csvs (build, validation, EDA counts) |
| pandas | 3.1.0 | EDA tables |
| matplotlib | 3.11.2 | EDA charts |
| snakemake | 9.27.1 | running the pipeline |

The validation recount uses only the Python standard library (`csv`). The map loads Plotly.js from a CDN, so it needs an internet connection to display.

## How to run

```
git clone https://github.com/himanihooda11/cms-hospitalization
cd cms-hospitalization
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run everything with Snakemake:

```
snakemake -n                              # dry run: show what would run
snakemake --cores 1 --scheduler greedy    # run what is out of date
```

`--scheduler greedy` avoids a solver binary bundled with Snakemake that does not run on Apple Silicon Macs. It does not change the results.

Or run the scripts one by one, in order:

```
python scripts/01_download.py
python scripts/02_build_risk.py
python scripts/03_validate.py
python scripts/04_eda.py
```

`03_validate.py` exits with an error if any check fails.

## Notes

- **2010 Sample 1 download:** the standard CMS URL for the 2010 Sample 1 beneficiary file returns 404. The script downloads it from an alternate CMS link (named `..._Sample_20.zip`, same workaround as the OHDSI ETL-CMS script) and saves it as Sample 1. Its contents were checked: 100% of its IDs are in 2009 Sample 1 and 0% are in 2010 Sample 20.
- **State codes** are SSA codes, not FIPS. Code 54 is labeled `Other`; it has no map location and is listed under the map.
- **Synthetic data:** DE-SynPUF has limited inferential research value and is meant for developing and testing tools.

## Development workflow

Each task was done on its own branch, linked to a GitHub issue, and merged into `main` through a pull request:

| Task | Branch |
|---|---|
| Task 1: download | `task1-download` |
| Task 2: hospitalization risk | `task2-risk` |
| Task 3: validation | `task3-validate` |
| Task 4: data dictionary | `task4-data-dictionary` |
| Task 4: EDA and map | `task4-eda` |
| Task 4: Snakemake | `task4-snakemake` |
| Task 5: README | `task5-readme` |