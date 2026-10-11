# M2 constitution: evidence storage, connectors and snapshots

Inherits [../CONSTITUTION.md](../CONSTITUTION.md). The articles below add to it and never relax it.

1. **Bytes first.**
   - The original payload goes to the content-addressed `ObjectStore` before any record points
     at it.
   - Records reference hashes; reads verify hashes.
2. **Exact spans only.** A quotation is cut from normalized text by offsets (`make_span` /
   `find_span`). Nothing is paraphrased into a span.
3. **Eligibility follows proof, not labels.**
   - Availability comes from a provider-verified timestamp (for example, SEC acceptance
     datetime) or falls back to `first_capture`.
   - A filing *date* or an XBRL `filed` *date* alone is not proof of availability time.
4. **Point-in-time XBRL (A8).**
   - Facts are selected as of the cutoff from the per-accession history.
   - The SEC `frames` API is never called, because it returns the last-filed, possibly
     restated, value.
   - A restatement filed after the cutoff never wins.
5. **Connectors never infer.**
   - A connector fetches, preserves, parses and labels.
   - It does not decide what a number means, whether guidance was "cut", or whether demand is
     "weak".
6. **Honest source errors.**
   - Unreachable, refused, throttled or malformed means `SOURCE_FAILED`.
   - Reachable and empty means `NO_DATA`.
   - An HTTP 200 carrying a refusal message is `SOURCE_FAILED`.
7. **Allowlist and politeness.**
   - Hosts are allowlisted (`ALLOWED_HOSTS`).
   - SEC requires a descriptive User-Agent with contact details.
   - Space requests to the same source by at least 1 s and respect the daily budgets in
     settings.
8. **Snapshots are immutable.** Later ingestion never alters an existing snapshot or its hash.
   Changing the cutoff changes eligibility, and the rule that decides it is the same one.
9. **The default suite stays offline.** Every connector takes an injected `Transport`; tests use
   recorded fixtures under `tests/fixtures/connectors/`.
10. **Instrumented I/O (A11, A14).** From M2-T06 on, each connector call is one
    `connector.fetch` span. It carries the source ID, URL host, status, outcome, byte size,
    payload hash and duration. Bodies and query strings are never recorded.
