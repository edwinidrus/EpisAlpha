-- EpisAlpha schema version 2 (M4-T01): job lease and cancellation. Additive only.
--
-- A run is executed by exactly one worker. The lease row is the claim: inserting it is atomic,
-- so a second claim on the same run fails on the primary key. A stale lease is never taken
-- over silently; recovery (M4-T03) removes it explicitly and starts a new attempt.
CREATE TABLE run_lease (
    run_id     TEXT PRIMARY KEY REFERENCES run(run_id) ON DELETE CASCADE,
    worker_id  TEXT NOT NULL,
    claimed_at TEXT NOT NULL
) STRICT;

-- A cancellation request is persisted, so the runner's watchdog sees it even when the browser
-- that asked has gone away.
CREATE TABLE run_cancel (
    run_id       TEXT PRIMARY KEY REFERENCES run(run_id) ON DELETE CASCADE,
    requested_at TEXT NOT NULL
) STRICT;
