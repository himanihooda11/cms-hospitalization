# Runs the pipeline in order: download -> build -> validate -> eda.
# Each rule lists the files it needs (input) and the files it makes (output).
# Snakemake only reruns a step when its outputs are missing or its inputs changed.
#
# Usage (from the project folder):
#   snakemake -n          # dry run: show what would run, without running it
#   snakemake --cores 1   # run everything that is out of date

years = [2008, 2009, 2010]
samples = range(1, 21)

bene_csvs = expand("files/csv/DE1_0_{year}_Beneficiary_Summary_File_Sample_{s}.csv", year=years, s=samples)
claim_csvs = expand("files/csv/DE1_0_2008_to_2010_Inpatient_Claims_Sample_{s}.csv", s=samples)
raw_csvs = bene_csvs + claim_csvs

eda_files = [
    "output/eda/1_flow.png",
    "output/eda/2_risk_by_year.png",
    "output/eda/3_risk_by_age.png",
    "output/eda/4_sex_by_age.png",
    "output/eda/5_race.png",
    "output/eda/6_group_sizes.png",
    "output/eda/7_race_age_heatmap.png",
    "output/eda/risk_map.html",
]


# final targets: the validation report and the eda outputs
rule all:
    input:
        "output/validation_report.txt",
        eda_files


# Task 1: download and unzip the 80 csvs (runs only if any of them is missing)
rule download:
    output:
        raw_csvs
    shell:
        "python scripts/01_download.py"


# Task 2: build the risk table
rule build:
    input:
        raw_csvs,
        "scripts/02_build_risk.py"
    output:
        "output/hospitalization_risk.csv",
        "output/hospitalization_risk.parquet"
    shell:
        "python scripts/02_build_risk.py"


# Task 3: validation; the script exits with an error if any check fails, which stops the pipeline
rule validate:
    input:
        raw_csvs,
        "output/hospitalization_risk.csv",
        "scripts/03_validate.py"
    output:
        "output/validation_report.txt"
    shell:
        "python scripts/03_validate.py"


# Task 4: charts and map, only after validation has passed
rule eda:
    input:
        raw_csvs,
        "output/hospitalization_risk.csv",
        "output/validation_report.txt",
        "scripts/04_eda.py"
    output:
        eda_files
    shell:
        "python scripts/04_eda.py"