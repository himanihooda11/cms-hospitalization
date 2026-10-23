# Bias and error in the hospitalization risk estimates

Risk = people hospitalized / people at risk. Anything that wrongly adds or removes people from either count, or puts them in the wrong group, changes the risk.

This file lists where that can happen in this project, how big it is in this data, and which check catches it. Each check says which script runs it; checks marked suggested are not built.

## Data quality

**1. Fewer claims in 2010**
- 272,920 claims have a 2010 admission date, compared with 551,828 for 2008. Beneficiary counts drop much less (2,326,856 in 2008, 2,255,098 in 2010).
- If 2010 claims are incomplete, the 2010 numerator is too low and 2010 risk (0.1001) is too low compared with 2008 (0.1339) and 2009 (0.1618).
- Check: claims by admission year (printed by `02_build_risk.py`, chart `output/eda/2_risk_by_year.png`). Suggested: claims per beneficiary per year, compared across years.

**2. Claims split over several rows**
- 1,331,533 claims are spread over 1,332,822 rows. 1,100 claims have different admission dates on different rows, and 80 of these fall in two different years.
- Counting every row instead of every claim would add hospitalizations to the wrong year. In this data that difference was 58 person-years.
- Check: rows vs unique `CLM_ID` (printed by `02_build_risk.py`), and claims with more than one admission date **(in 03_validate.py)**. The full recount from raw files **(in 03_validate.py)** first found this difference.

**3. Admissions before 2008**
- 4,318 claims have a 2007 admission date and are not counted. A stay that started in late December 2007 does not count for 2008.
- This can make 2008 risk slightly low.
- Check: claims by admission year, including years outside 2008-2010 (printed by `02_build_risk.py`).

**4. Duplicate or wrong records**
- A person listed twice in the same year would be counted twice in the denominator. A claim linked to a person who is not in any beneficiary file would be lost.
- In this data: 0 duplicate IDs within a year, 0 IDs in more than one sample, 0 claims without a matching beneficiary.
- Check: duplicate `DESYNPUF_ID` per year, IDs across samples, claims without a beneficiary **(in 03_validate.py)**.

**5. Missing or invalid values**
- A missing birth date, admission date or code would drop people or put them in the wrong group.
- In this data: 0 missing birth dates, 0 missing admission dates, all sex, race and state codes valid.
- Check: missing or invalid birth dates, code lists, age range (25 to 101) **(in 03_validate.py)**. Missing admission dates (printed by `02_build_risk.py`).

**6. Wrong source file**
- The 2010 Sample 1 file had to come from a different CMS link with a different name. A wrong file would change the 2010 counts without any error.
- Check: 100% of its IDs are in 2009 Sample 1 and 0% are in 2010 Sample 20 (run in `01_download.py`). Row counts per year match the assignment **(in 03_validate.py)**.

**7. State codes**
- `SP_STATE_CODE` uses SSA codes, not FIPS. Reading them as FIPS would put people in the wrong state. Code 54 (70,305 people at risk over three years) is outside the 1-53 state range and is labeled `Other`.
- Check: all codes are in the expected range **(in 03_validate.py)**. State names come from the CMS SSA code list (`02_build_risk.py`).

**8. Synthetic data**
- DE-SynPUF records are synthetic. Patterns in the output may come from how the data was generated and not from real differences between groups.
- No check can fix this. Results are for testing the pipeline, not for drawing conclusions.

## Processing choices

**9. Excluding people with HMO months**
- People with any HMO coverage are left out: 23.1% of beneficiaries in 2008, 29.2% in 2009, 32.5% in 2010. Their hospital stays may be missing from fee-for-service claims, so keeping them would make risk look too low.
- Leaving them out also changes who is counted, and the share left out grows each year, which affects comparisons across years. In this data, 78,399 (2008), 113,231 (2009) and 83,078 (2010) people with HMO months do have an admission and are not counted.
- Check: number excluded per year (printed by `02_build_risk.py`). Suggested: rerun risk with HMO members included and compare.

**10. People not covered for the whole year**
- Someone who dies in the year, or is covered for only part of it, counts as one full person in the denominator but had less time to be hospitalized. This can make risk slightly low.
- Check (suggested): count people with a death date in the year, by group. Coverage months are not among the columns used here; adding them would allow a person-time version (months at risk) to show how much this matters.

**11. Age on Dec 31**
- Age is year minus birth year. Someone who turns 65 in December is in `65-69` for the whole year. Moving the reference date would move some people between age groups.
- Check: age range and age group counts (printed by `02_build_risk.py`). Suggested: rerun with age on Jan 1 and compare.

**12. One count per person**
- A person with three admissions in a year counts once. This is what risk means, but it does not show how many stays there were.
- Check: compare claims with people hospitalized per year (both printed by `02_build_risk.py`). For 2008: 551,828 claims and 317,940 people with an admission.

**13. Small groups**
- 640 of 6,943 output rows have fewer than 11 people at risk. One person more or less changes their risk a lot, and values of 0 and 1 appear.
- Check: count small groups (printed by `02_build_risk.py`, chart `output/eda/6_group_sizes.png`). Suggested: add confidence intervals or combine small groups before comparing them.

**14. Different age mixes between groups**
- In this data, risk is higher in older age groups (2008: 8.7% at 65-69, 21.4% at 90+). A state or race group with more older people will have higher crude risk for that reason alone.
- Check: compare crude and age-standardized risk (`output/eda/5_race.png`). For race, the two differ by at most 0.6 percentage points in this data (Other, 2008: 9.65% crude, 10.28% standardized). The map uses age-standardized risk.

**15. Combining groups**
- Averaging the risks of several groups gives a group of 5 people the same weight as a group of 5,000.
- Check: combined risk is always total hospitalized / total at risk, and yearly totals match a recount from the raw files **(in 03_validate.py)**.

## Summary of checks

| Check | Catches | Where |
|---|---|---|
| Row counts match the assignment | missing or extra files and rows | 03_validate.py |
| Duplicate IDs, IDs across samples | people counted twice | 03_validate.py |
| Missing or invalid birth dates, code lists, age range | people dropped or in the wrong group | 03_validate.py |
| Claims link to a beneficiary, one person per claim | lost or misassigned hospitalizations | 03_validate.py |
| Full recount of every group from raw files | errors in the build code or rules | 03_validate.py |
| Spot-checks with example IDs | errors in single groups, traceability | 03_validate.py |
| 2010 Sample 1 ID overlap | wrong source file | 01_download.py |
| Exclusions, claims by year, small groups | effect of each processing choice | 02_build_risk.py, 04_eda.py |
| Crude vs age-standardized risk | differences caused by age mix | 04_eda.py |
| Rerun with HMO members, age on Jan 1, person-time | how much each choice changes the result | suggested |