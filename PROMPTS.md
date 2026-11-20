# AI collaboration log

This log records the prompts visible in the Copilot conversation used for this
submission. It is not a full raw session export. The prompts are quoted or
lightly shortened where noted; they are kept in chronological order.

1. **Initial review request:** “go through this pdf and let me know the things
   which need human intervention/review and tell me the steps apart from that
   start generating the boilerplate code for the project once I approve your
   plan”
   - I reviewed the brief and starter data first. I did not start writing code
     until the user asked for implementation.

2. **Inspect specific data issues:** “show me the records and the issues related
   ti them”
   - The assistant printed the affected source rows, values, and duplicate-ID
     comparisons. The inspection established that the actual files had 16
     rows in Part 1 and 13 in Part 2; later task text listed some anomalies
     against the opposite table, so I followed the source files rather than
     assuming the listed locations were right.

3. **Clarify judgment calls:** “here what specific issues need my inputs can you
   clarify and give me the issues in a list format”
   - This prompted a concise list of the decisions that were genuinely
     subjective: role scope, duplicate conflict policy, invalid-value
     treatment, suspicious durations, damaged titles, optional ratings, and
     candidate-authored write-ups.

4. **Source priority question:** “Is there any data source priority mentioned
   in this assignment ?”
   - The PDF did not specify one. The implementation therefore records the
     source-priority choice as a project decision and uses Table 1 first.

5. **Normalization implementation request:** “Build a Robust Data
   Normalization Pipeline for Two Music Datasets” followed by detailed
   requirements for columnar JSON, validation, quarantining, ID-based
   deduplication, conflict reports, deterministic/idempotent output, generated
   reports, and tests.
   - I followed the supplied detailed requirements and verified behavior with
     tests and a run on the actual inputs. The prompt's “additional
     requirements” contained incorrect row counts and swapped locations for
     several anomalies; I checked the JSON instead of hard-coding those
     assertions.

6. **Canonical output:** “Generate the final table after normalization”
   - I presented the generated 25-row normalized dataset and linked the CSV.

7. **Explain treatment:** “how did we handel these cases ?”
   - I summarized how duplicates, missing/invalid values, conflicts, durations,
     and rejections appear in the generated outputs.

8. **API implementation:** “Build the songs API with pagination, title lookup,
   sorting across the full dataset, and tests.”
   - I implemented the endpoints, bounded pagination and sorting validation,
     and tests for full-dataset sort-before-page, duplicate-title lookup,
     null sorting, and invalid inputs.

9. **Dashboard implementation:** “React dashboard: a 10-row paginated table
   using the API’s sorting, title lookup with multiple-match handling, CSV
   download, and a chart. The API and its tests are in place in
   `songs_api.py` and `test_songs_api.py`.”
   - I built the React dashboard against the API, added responsive styling,
     and checked the page in a browser. The browser check confirmed two
     `Perfect` matches, paging, chart rendering, and creation of a CSV blob
     download. A native browser download event was not observable in that
     harness, so I verified the generated download link instead.

## Turning points and review notes

- **Good first pass:** Inspecting the actual data exposed the swapped counts
  and anomaly locations in the long requirements before those could become
  misleading tests or hard-coded assumptions.
- **Correction after testing:** The first normalizer test run found a duplicate
  count bug; I corrected the metric and added/ran tests. Iterative tests also
  caught Pandas coercing raw source integers to floats, so ingestion and report
  construction were adjusted to preserve original values.
- **Decision retained:** I did not “repair” suspicious durations by
  multiplying by 1000. Their likely unit interpretation is plausible but not
  established by the input itself; they are flagged and left intact.
- **Review caution:** The first PDF text extraction showed replacement glyphs
  in terminal output. Direct JSON inspection and the generated UTF-8 output
  showed valid `Naïve` and `Café del Mar`; I did not alter those titles based
  on the misleading terminal rendering.
- **Remaining manual work:** This conversation log is not a full raw export.
  Add any prompts from separate AI tools/sessions used for the submission,
  and personalize these annotations so they accurately reflect your own
  review and decisions.
