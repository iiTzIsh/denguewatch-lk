# WER source notes

Source: https://www.epid.gov.lk/weekly-epidemiological-report

## Checked 28 Sep 2026 (by Claude, via web fetch)
- robots.txt: general crawlers allowed (`User-agent: *  Disallow:` empty). Only Googlebot/bingbot/facebookexternalhit are blocked from `/storage/post/pdfs/`.
- Listing text format: `Week 18 2024.04.27 - 2024.05.03 - <title>`
- Years listed on the page: 2006 to 2024.
- 2025 and 2026 were NOT seen on the page -> VERIFY (pagination? moved? not published?).
- Epi weeks run Saturday -> Friday (2024.04.27 = Sat, 2024.05.03 = Fri).
- Week 1 of 2024 = 2023.12.30 - 2024.01.05 -> epi year != calendar year of start date.

## Unverified (check after running wer_links.py)
- PDFs probably live under `/storage/post/pdfs/` (guessed from robots.txt only).

## Fill in after running `python -m src.extract.wer_links`
- Total PDF links found:
- Real URL pattern:
- PDFs per year (paste table):
- Unparsed rows:
