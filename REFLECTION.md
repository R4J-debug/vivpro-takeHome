# Reflection

1. **What is the single weakest part of your submission, and why did you leave
   it that way?**
   The weakest part is that ratings are not implemented. They are optional in
   the brief, while the required normalization, API, dashboard, and tests were
   prioritized. A real rating feature needs persistent storage and a decision
   about who is rating (a global song rating or per-user ratings); an
   in-memory dictionary would appear to work but lose data on restart.

2. **Where did AI save you the most time, and where did it cost you time or
   nearly lead you wrong?**
   AI accelerated the API, React dashboard, and test scaffolding. Its output
   still needed verification: the task's listed table counts and some anomaly
   locations did not match the supplied JSON, so the data was inspected
   directly. Testing also caught a normalization-report counting error and
   prompted a change to preserve raw numeric types in the validation report.

3. **What in the data surprised you? What did you decide not to fix, and why?**
   The source files have 16 and 13 rows, respectively, and four IDs overlap.
   Most overlapping attributes agree, but `Never Gonna Give You Up` has
   danceability values of `0.727` and `0.74`; Table 1 is the configured
   tie-breaker. Three duration values are implausibly small for milliseconds,
   but their intended units cannot be proved from these files alone, so they
   were flagged rather than converted. Invalid optional measurements were
   nulled and reported instead of dropping otherwise usable songs.

4. **If this went to production Monday and real users hit it, what breaks
   first?**
   The API reads and caches a generated CSV and has no authentication,
   persistent user ratings, or deployment/monitoring setup. A changed dataset
   would require regeneration and a process reload; multiple API instances
   would have no coordinated refresh or shared state. Production use would
   need a managed data store and refresh process, health/error monitoring,
   deployment configuration, and an explicit policy for stale or rejected
   data.

5. **(Lead/architect candidates only) What would make this production-grade?**
   Treat each source delivery as a versioned ingestion batch; validate its
   schema and quality thresholds before publishing an immutable normalized
   snapshot. Persist source provenance, validation findings, and conflicts;
   require review for unresolved conflicts and unit anomalies. Add integration
   tests for ingestion and API behavior, structured logs and metrics for batch
   health and request errors, and a repeatable deployment with health checks,
   configuration, and rollback to the last good snapshot. For a v1, I would
   keep a read-only catalog and approved data refreshes; I would defer
   user-specific ratings and broader operational complexity until their
   ownership and product requirements are clear.
