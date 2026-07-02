# Archived scripts

One-off / historical scripts kept for reference but **not part of the active
pipeline**. The live nightly run is orchestrated by [`run_pipeline.py`](../../run_pipeline.py)
and uses only `export_sheet_keys.py → scrape_linkedin_posts.py → publish_to_sheets.py`.

These were manual, single-use runs (specific cities, founder's-office pushes,
MNC-specific scrapes) and sheet-maintenance utilities. They are excluded from
linting and CI.
