# Review: `review/.../buggy_api.py`

## Block the PR

1. **Pagination skips the first page — `get_songs`, lines 33–37.**
   `start = page * size` makes page 1 start at index `size`, so the first
   page is skipped; later pages are shifted and the final page may be empty.
   Use `(page - 1) * size` for one-based pagination and test first, middle,
   final, and out-of-range pages.

2. **Sorting is performed only on the selected page — `get_songs`, lines 37–39.**
   Results are sliced before sorting, so each page is locally ordered rather
   than being a page of the globally sorted dataset. Sort the complete
   collection first, then slice it.

3. **The loader does not match the supplied normalized output — `load_songs`,
   lines 21–29.**
   It opens `songs.json` relative to the process working directory, whereas
   this project produces `normalized_output/normalized_songs.csv`; the API
   fails with `FileNotFoundError` when run against the provided deliverable.
   Accept/configure the data path, load the actual output format, and report
   startup/data errors clearly.

## High priority

4. **Sort input is unvalidated and can turn a request into a server error —
   `get_songs`, lines 33–39.**
   An unknown `sort_by` raises `KeyError`; mixed types or null values may also
   fail comparisons. Validate `sort_by` against an allowlist, validate
   `order`, and define null/type handling before sorting.

5. **Pagination parameters have no bounds — `get_songs`, line 33.**
   Negative or zero `page`/`size` values are accepted and produce misleading
   slices or empty responses. Enforce `page >= 1` and a bounded positive size
   (for example, 1–100) and return a client error for invalid values.

6. **Title lookup silently misses normalized matches and cannot represent
   ambiguity — `get_song_by_title`, lines 43–49.**
   Matching is exact and case-sensitive, so casing and whitespace differences
   fail; duplicate titles return only the first song. Normalize case and
   whitespace and return all matches (or require a unique song ID).

7. **A not-found lookup returns HTTP 200 — `get_song_by_title`, line 49.**
   Clients can interpret `{"error": "not found"}` as a successful response.
   Raise an HTTP 404, or define a consistent empty-result response with an
   explicit contract.

8. **Ratings are neither constrained nor reliably associated with a song —
   `rate_song`, lines 52–62.**
   Any integer is accepted instead of only 1–5; ratings are keyed by title, so
   duplicate titles collide and the loop updates every matching song. Validate
   the range, identify the song by ID, and define whether ratings are
   per-user or global.

9. **Rating writes report success even when no song matched — `rate_song`,
   lines 56–62.**
   The rating is stored and returned before confirming the title exists.
   Resolve the target song first and return 404 if it is absent; persist only
   a valid rating for an existing song.

10. **Ratings disappear on process restart and differ between workers —
    `ratings = {}`, lines 52–62.**
    The module-level dictionary is process-local memory, not durable storage;
    a restart loses ratings and multiple API workers can disagree. Use a
    persistent store with a unique key based on the chosen rating identity.

11. **Duration statistics fail for empty or malformed data — `duration_stats`,
    lines 66–72.**
    Empty input divides by zero; missing, null, or non-numeric durations raise
    errors while summing. Validate/skip or explicitly reject invalid durations
    and handle the empty dataset in the response contract.

## Lower priority

12. **The default-argument cache is hidden shared mutable state — `load_songs`,
    lines 21–29.**
    `_cache=[]` is created once and reused across calls; it can retain stale
    data and an empty file causes repeated reads because the cache remains
    falsey. Use an explicit cached loader with a documented refresh policy,
    and avoid a mutable default argument.

13. **The cached list is mutated by the rating route — `rate_song`, lines
    56–62.**
    Updating `song["rating"]` changes the shared in-memory catalog, mixing user
    ratings into source data and making results dependent on process lifetime.
    Keep catalog records immutable and store ratings separately.

## Merge recommendation

**Request changes.** The current pagination and sorting return incorrect
results, the data loader does not run with the supplied normalized output, and
the rating endpoint accepts invalid or unresolved writes while claiming
success. The duration-statistics and cache behavior also need explicit
edge-case coverage before approval.
