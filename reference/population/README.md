# District population (Census 2024)

**Source:** *Census of Population and Housing 2024 – Final Report*, Department of Census and Statistics Sri Lanka, released 10 April 2026, Table 3.2 "Distribution of Population by Province and District, 2024".
https://www.statistics.gov.lk/Resource/en/Population/CPH_2024/CPH2024_Final_Eng.pdf

1. Download the PDF in a browser and save it here as `CPH2024_Final_Eng.pdf`. It's large and git-ignored, so only the small CSV is committed.
2. Run `python -m src.reference.build_population`. It **reads** the numbers from Table 3.2 and only writes `district_population_2024.csv` if:
   - all 25 districts are found
   - they sum to the national total printed in the report (**21,781,800**)
   - Gampaha = **2,436,142** and Mullaitivu = **122,619**, as stated in the report text

Used for **cases per 100,000 people** at district level (dashboard map, Top 10, API). The forecasts stay per health region (RDHS) in case counts, because the census gives districts, not RDHS. Ampara district = Ampara + Kalmunai RDHS.
