# Downloads the CMS DE-SynPUF files used in this project and unzips them:
#   - Beneficiary Summary files, 2008-2010, samples 1-20  (60 files)
#   - Inpatient Claims files, 2008-2010, samples 1-20     (20 files)
# Zips go to files/zips/, csvs to files/csv/. Safe to re-run: finished files are skipped.
#
# Usage: python scripts/01_download.py

import csv
import shutil
import time
import zipfile
from pathlib import Path

import requests

root = Path(__file__).resolve().parents[1]
zip_dir = root / "files" / "zips"
csv_dir = root / "files" / "csv"

cms_url = "https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/SynPUFs/Downloads/"
years = [2008, 2009, 2010]
samples = range(1, 21)

# CMS only hosts the 2010 Sample 1 beneficiary file under a Sample_20 name in a
# different folder; the standard URL returns 404. Same workaround as the OHDSI ETL-CMS script.
# check_2010_sample1() below confirms the contents are Sample 1.

url_fixes = {
    "DE1_0_2010_Beneficiary_Summary_File_Sample_1.zip":
        "https://www.cms.gov/Research-Statistics-Data-and-Systems/Statistics-Trends-and-Reports/"
        "SynPUFs/Downloads/DE1_0_2010_Beneficiary_Summary_File_Sample_20.zip",
}

no_retry = {403, 404, 410}  # dead links


def build_file_names():
    """3 beneficiary files + 1 inpatient file per sample = 80 files."""
    names = []
    for s in samples:
        for year in years:
            names.append(f"DE1_0_{year}_Beneficiary_Summary_File_Sample_{s}.zip")
        names.append(f"DE1_0_2008_to_2010_Inpatient_Claims_Sample_{s}.zip")
    return names


def download(session, url, dest, tries=3):
    """Download to a .part file and rename only if it's a valid zip."""
    tmp = dest.with_name(dest.name + ".part")
    for attempt in range(1, tries + 1):
        try:
            with session.get(url, stream=True, timeout=60) as r:
                if r.status_code in no_retry:
                    print(f"  HTTP {r.status_code}: {url}")
                    return False
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        f.write(chunk)
            # a bad link can return an html page with a 200
            if not zipfile.is_zipfile(tmp):
                print(f"  not a zip: {url}")
                tmp.unlink(missing_ok=True)
                return False
            tmp.replace(dest)
            return True
        except requests.RequestException as e:
            tmp.unlink(missing_ok=True)
            print(f"  attempt {attempt} failed: {e}")
            if attempt < tries:
                time.sleep(3 * attempt)
    return False


def extract(zip_path, csv_path):
    """Extract the single csv, named after the zip. Returns an error string or None."""
    # name the csv after the zip, since the file inside doesn't always match
    # (e.g. "... - Copy.csv", or Sample_20 inside the 2010 Sample 1 zip)
    with zipfile.ZipFile(zip_path) as z:
        inner = [m for m in z.namelist() if m.lower().endswith(".csv")]
        if len(inner) != 1:
            return f"{len(inner)} csv files inside, check by hand"
        if Path(inner[0]).stem != zip_path.stem:
            print(f"  note: {zip_path.name} contains {inner[0]}")
        tmp = csv_path.with_name(csv_path.name + ".part")
        with z.open(inner[0]) as src, open(tmp, "wb") as dst:
            shutil.copyfileobj(src, dst)
        tmp.replace(csv_path)
    return None


def read_ids(path):
    with open(path, newline="") as f:
        return {row["DESYNPUF_ID"] for row in csv.DictReader(f)}


def check_2010_sample1():
    """Confirm the renamed 2010 Sample 1 file holds Sample 1 beneficiaries."""
    f = lambda y, s: csv_dir / f"DE1_0_{y}_Beneficiary_Summary_File_Sample_{s}.csv"
    paths = [f(2010, 1), f(2009, 1), f(2010, 20)]
    if not all(p.exists() for p in paths):
        print("\nskipping 2010 Sample 1 check (files missing)")
        return
    ids_2010_s1, ids_2009_s1, ids_2010_s20 = (read_ids(p) for p in paths)
    n = len(ids_2010_s1)
    print("\n2010 Sample 1 check:")
    print(f"  ids in file             : {n:,}")
    print(f"  overlap w/ 2009 Sample 1: {len(ids_2010_s1 & ids_2009_s1) / n:.1%}  (should be high)")
    print(f"  overlap w/ 2010 Sample 20: {len(ids_2010_s1 & ids_2010_s20) / n:.1%}  (should be ~0)")


def main():
    zip_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)

    file_names = build_file_names()
    not_downloaded, not_extracted = [], []

    with requests.Session() as session:
        for name in file_names:
            zip_path = zip_dir / name
            csv_path = csv_dir / (zip_path.stem + ".csv")

            if zip_path.exists() and zipfile.is_zipfile(zip_path):
                print(f"already have {name}")
            else:
                print(f"downloading {name}")
                url = url_fixes.get(name, cms_url + name)
                if not download(session, url, zip_path):
                    print(f"  FAILED: {name}")
                    not_downloaded.append(name)
                    continue

            if csv_path.exists():  # csvs only appear once fully written
                continue
            err = extract(zip_path, csv_path)
            if err:
                print(f"  {name}: {err}")
                not_extracted.append(name)

    # final check against expected names, not a glob count
    missing_zips = [n for n in file_names if not (zip_dir / n).exists()]
    missing_csvs = [n for n in file_names if not (csv_dir / (Path(n).stem + ".csv")).exists()]
    print(f"\nexpected: {len(file_names)}  "
          f"zips: {len(file_names) - len(missing_zips)}  "
          f"csvs: {len(file_names) - len(missing_csvs)}")

    for label, items in [("not downloaded", not_downloaded), ("not unzipped", not_extracted)]:
        if items:
            print(f"{label}:")
            for n in items:
                print("  ", n)
    if not missing_csvs:
        print("all files ready")

    check_2010_sample1()


if __name__ == "__main__":
    main()