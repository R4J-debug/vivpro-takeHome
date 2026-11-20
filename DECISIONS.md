# Decisions

## Data normalization

- **Row alignment and identity:** Convert each column-oriented JSON export to
  rows using the union of its row-index keys; align the two exports by `id`,
  never by row index or title. `id` is the business key, so same-title songs
  with different IDs remain distinct.
- **Duplicate records:** The supplied exports contain 16 rows in Part 1 and 13
  in Part 2, with four IDs in common (25 unique IDs overall). Identical valid
  attributes are retained once. The additional `valence` field in Part 2 is
  included in the union schema; it remains null for records where no source
  supplies it.
- **Source priority and conflicts:** The assignment does not prescribe a
  source priority. The configured default is Part 1 (`table1`) before Part 2
  (`table2`). A valid value beats a missing or invalid value, regardless of
  source priority. When both values are valid and differ, the higher-priority
  source wins and the two values, chosen source, and reason are written to
  `normalized_output/conflicts.csv`. The supplied data has one such conflict:
  `Never Gonna Give You Up` danceability is `0.727` in Part 1 and `0.74` in
  Part 2, so `0.727` is selected. Values are not averaged.
- **Missing and malformed values:** Nulls, absent keys, empty strings, and
  `"N/A"`/`"null"`-style strings are treated as missing. Numeric strings that
  parse successfully are converted to numbers. Missing optional attributes
  remain null; values are not imputed. Original records and issue reasons are
  retained in `normalized_output/validation_report.csv`.
- **Validation:** Danceability, energy, acousticness, and valence must be in
  `[0, 1]`; mood must be `0` or `1`; tempo must be positive; duration and
  section/segment counts must be positive integers. Invalid optional
  attributes are nulled and reported without discarding the song. Missing or
  invalid required IDs or titles reject a record; none of the supplied records
  were rejected.
- **Suspicious duration values:** Positive durations below 1000 ms are flagged
  as suspicious, not treated as proven unit errors. The values `158`, `270`,
  and `356` remain unchanged in the normalized output until verified against a
  trusted source. The threshold is configurable.
- **Titles:** Trim surrounding whitespace, retain Unicode, and do not infer
  corrected spellings. Title lookup normalizes Unicode compatibility forms,
  whitespace, and case without changing the stored title. This supports
  case/spacing-insensitive matching while preserving distinct records.
- **Output and traceability:** Produce a canonical CSV, rejected-record CSV,
  conflict CSV, row-level validation CSV, and JSON quality summary. Include
  source names and original row indices in the canonical output to support
  auditing. The pipeline can be rerun against the same source files without
  accumulating output duplicates.

## API and dashboard

- **Storage and API:** Serve the generated CSV through FastAPI; cache the
  normalized dataset in process after its first read. This keeps the take-home
  implementation simple and reproducible; it is not intended as a live
  multi-writer data store.
- **Pagination and sorting:** `GET /songs` uses one-based `page`, `size`,
  `sort_by`, and `order` parameters. Sorting is applied to the full dataset
  before slicing the requested page. Nulls sort last, page size is bounded,
  and unsupported sort columns are rejected.
- **Title lookup:** `GET /songs/lookup?title=...` returns all exact matches
  after case-folding and normalizing whitespace (and Unicode compatibility
  forms). A list response makes duplicate titles explicit; for example,
  `Perfect` returns both distinct song IDs rather than choosing arbitrarily.
- **Frontend:** The table requests 10 rows per page and delegates sorting to
  the API so sort order is global. CSV export contains the currently displayed
  page. The scatter plot requests the full catalog and omits songs missing a
  valid danceability or energy value, with that omission stated in the UI.
- **Deliberately deferred:** Persistent star ratings, authentication, a
  production database, deployment, and operational monitoring were not
  included in this implementation. Ratings are an optional (“should have”)
  item in the brief; adding them responsibly would require durable storage and
  clear rating ownership/identity semantics.
