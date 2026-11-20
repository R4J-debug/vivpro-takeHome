# Music data normalization

The project normalizes two column-oriented JSON exports into a validated,
ID-keyed songs dataset, retaining provenance and reports for missing, invalid,
suspicious, or conflicting data. A FastAPI service provides paginated,
whole-dataset sorting and case/spacing-insensitive title lookup. The React
dashboard consumes that API with a sortable 10-row table, title search,
current-page CSV export, and a danceability-versus-energy chart. Focused Python
tests cover normalization and API edge cases, and the dashboard has reproducible
build and lint commands.

## Run

Prerequisites: Python 3.10 or later and Node.js 20.19+ (or 22.12+).

From the project root, install the Python dependencies, normalize the supplied
data, and run the backend tests:

```powershell
python -m pip install -r requirements.txt
python normalize_songs.py
python -m unittest discover -s tests -v
```

By default the script locates `songs_part1.json` and `songs_part2.json` under
the project directory and writes results to `normalized_output`. To provide
other files or an output directory:

```powershell
python normalize_songs.py --table1 path\to\table1.json --table2 path\to\table2.json --output-dir path\to\output
```

Durations below 1000 ms are flagged as suspicious by default and are not
converted or discarded. Configure that threshold with
`--suspicious-duration-ms-below`.

## Outputs

- `normalized_songs.csv`: one row per valid, unique song ID. Invalid optional
  attributes are null; source names and row indices are retained.
- `rejected_records.csv`: original records rejected for a missing or invalid
  required ID or title.
- `conflicts.csv`: every differing pair of valid values for a duplicate ID,
  including the chosen value and resolution reason.
- `validation_report.csv`: missing, invalid, suspicious, and text-integrity
  findings, with the original input record for traceability.
- `data_quality_report.json`: record totals, missing/invalid counts, overlaps,
  conflicts, rejections, and normalized record count.

## Tests

```powershell
python -m unittest discover -s tests -v
```

## Songs API

After generating the normalized CSV, start the FastAPI service in its own
terminal from the project root:

```powershell
uvicorn songs_api:app --reload
```

The API reads `normalized_output/normalized_songs.csv` by default. Override
that path with the `SONGS_CSV_PATH` environment variable.

- `GET /songs?page=1&size=10&sort_by=title&order=asc` returns a page. Sorting
  is applied to the full dataset before pagination; `size` is limited to 100.
- `GET /songs/lookup?title=Perfect` returns all case- and whitespace-insensitive
  exact title matches, including multiple songs with the same title.

Sorting accepts normalized song attributes, and nulls sort last in either
direction. Invalid sort columns return HTTP 400; invalid pagination parameters
are rejected by FastAPI.

## React dashboard

Keep the API running in one terminal. In a second terminal, start the Vite
dashboard:

```powershell
Set-Location frontend
npm ci
npm run dev
```

The dashboard uses Vite's `/api` development proxy to reach FastAPI at
`http://127.0.0.1:8000`. The proxy is for local development; for a
cross-origin deployment, set `VITE_API_BASE_URL` before building and configure
the API to allow the dashboard origin through CORS. The table requests 10 rows
at a time; sorting is performed by the API before pagination. CSV downloads
contain the visible page, while the danceability/energy scatter plot loads the
full catalog.

Build and lint the frontend with:

```powershell
Set-Location frontend
npm ci
npm run build
npm run lint
```

The React development server prints its local URL (normally
`http://localhost:5173`). Keep the API and frontend processes running in
separate terminals while using the dashboard.

## Submission checklist

- Run the Python tests and frontend build/lint commands above.
- Verify `normalized_output` has been generated from the supplied source JSON.
- Review `DECISIONS.md`, `PROMPTS.md`, `REFLECTION.md`, and `REVIEW.md`;
  personalize candidate-authored judgments and add any AI prompts from other
  tools or sessions before submitting.
- Create/push this folder to your own GitHub repository and send the repository
  link as requested by the assignment. No Git repository or remote is
  configured in this workspace.
