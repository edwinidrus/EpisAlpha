-- EpisAlpha schema version 1 (M2-T01).
--
-- Design rule from the plan: relationship endpoints must be real foreign keys, not unchecked
-- strings. Every graph node is registered in `node` with its kind, and every per-kind table
-- keys off it, so `relation.source_id` and `relation.target_id` can reference `node(node_id)`
-- and SQLite itself refuses a dangling edge.
--
-- Each record table keeps a `payload` column holding the validated contract as JSON, next to
-- the columns worth querying or constraining. The payload is never the only store: ids, kinds,
-- versions and timestamps stay queryable, per the plan's implementation rule.

CREATE TABLE node (
    node_id TEXT PRIMARY KEY,
    kind    TEXT NOT NULL CHECK (kind IN (
        'entity', 'instrument', 'evidence_document', 'evidence_span',
        'claim', 'event', 'hypothesis', 'thesis'
    ))
) STRICT;

CREATE TABLE entity (
    entity_id      TEXT PRIMARY KEY REFERENCES node(node_id) ON DELETE CASCADE,
    canonical_name TEXT NOT NULL,
    payload        TEXT NOT NULL
) STRICT;

CREATE TABLE instrument (
    instrument_id    TEXT PRIMARY KEY REFERENCES node(node_id) ON DELETE CASCADE,
    issuer_entity_id TEXT NOT NULL REFERENCES entity(entity_id),
    currency         TEXT NOT NULL,
    payload          TEXT NOT NULL
) STRICT;

CREATE TABLE evidence_document (
    document_id         TEXT PRIMARY KEY REFERENCES node(node_id) ON DELETE CASCADE,
    source_family_id    TEXT NOT NULL,
    source_uri          TEXT NOT NULL,
    payload_hash        TEXT NOT NULL,
    parsed_text_hash    TEXT NOT NULL,
    parser_version      TEXT NOT NULL,
    availability_basis  TEXT NOT NULL,
    public_available_at TEXT,
    ingested_at         TEXT NOT NULL,
    -- A revision points at the version it supersedes; both rows are retained (temporal rule 6).
    revises_document_id TEXT REFERENCES evidence_document(document_id),
    payload             TEXT NOT NULL,
    CHECK (revises_document_id IS NULL OR revises_document_id <> document_id)
) STRICT;

CREATE INDEX idx_document_family ON evidence_document(source_family_id);

CREATE TABLE evidence_span (
    span_id      TEXT PRIMARY KEY REFERENCES node(node_id) ON DELETE CASCADE,
    document_id  TEXT NOT NULL REFERENCES evidence_document(document_id),
    start_offset INTEGER NOT NULL,
    end_offset   INTEGER NOT NULL,
    exact_quote  TEXT NOT NULL,
    payload      TEXT NOT NULL,
    CHECK (end_offset > start_offset)
) STRICT;

CREATE INDEX idx_span_document ON evidence_span(document_id);

CREATE TABLE claim (
    claim_id               TEXT PRIMARY KEY REFERENCES node(node_id) ON DELETE CASCADE,
    statement              TEXT NOT NULL,
    epistemic_status       TEXT NOT NULL,
    semantic_review_status TEXT NOT NULL,
    created_at             TEXT NOT NULL,
    run_id                 TEXT,
    payload                TEXT NOT NULL
) STRICT;

CREATE TABLE event (
    event_id    TEXT PRIMARY KEY REFERENCES node(node_id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload     TEXT NOT NULL
) STRICT;

CREATE TABLE hypothesis (
    hypothesis_id TEXT PRIMARY KEY REFERENCES node(node_id) ON DELETE CASCADE,
    created_at    TEXT NOT NULL,
    payload       TEXT NOT NULL
) STRICT;

CREATE TABLE thesis (
    thesis_id     TEXT PRIMARY KEY REFERENCES node(node_id) ON DELETE CASCADE,
    run_id        TEXT NOT NULL,
    instrument_id TEXT NOT NULL REFERENCES instrument(instrument_id),
    snapshot_id   TEXT NOT NULL,
    stance        TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    payload       TEXT NOT NULL
) STRICT;

-- Typed edges. Endpoints reference the node registry, so a dangling edge is impossible.
CREATE TABLE relation (
    relation_id      TEXT PRIMARY KEY,
    predicate        TEXT NOT NULL CHECK (predicate IN (
        'ISSUED_BY', 'HAS_SPAN', 'REPORTS', 'ABOUT',
        'SUPPORTS', 'CONTRADICTS', 'DERIVED_FROM'
    )),
    source_id        TEXT NOT NULL REFERENCES node(node_id),
    target_id        TEXT NOT NULL REFERENCES node(node_id),
    epistemic_status TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    run_id           TEXT,
    payload          TEXT NOT NULL,
    CHECK (source_id <> target_id)
) STRICT;

CREATE INDEX idx_relation_source ON relation(source_id, predicate);
CREATE INDEX idx_relation_target ON relation(target_id, predicate);

-- Assessments are versioned, never overwritten: a correction inserts a new row that names the
-- one it supersedes, and the superseded row stays readable.
CREATE TABLE semantic_assessment (
    assessment_id            TEXT PRIMARY KEY,
    subject_id               TEXT NOT NULL REFERENCES node(node_id),
    judgment                 TEXT NOT NULL,
    reviewer_type            TEXT NOT NULL,
    reviewer_identity        TEXT NOT NULL,
    assessed_at              TEXT NOT NULL,
    supersedes_assessment_id TEXT REFERENCES semantic_assessment(assessment_id),
    payload                  TEXT NOT NULL,
    CHECK (supersedes_assessment_id IS NULL OR supersedes_assessment_id <> assessment_id)
) STRICT;

CREATE INDEX idx_assessment_subject ON semantic_assessment(subject_id, assessed_at);

CREATE TABLE snapshot (
    snapshot_id     TEXT PRIMARY KEY,
    snapshot_hash   TEXT NOT NULL,
    research_cutoff TEXT NOT NULL,
    frozen_at       TEXT NOT NULL,
    payload         TEXT NOT NULL
) STRICT;

-- One run per idempotency key. Re-submitting a request finds the existing run instead of
-- starting a second one and spending the model budget twice.
CREATE TABLE run (
    run_id          TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    instrument_id   TEXT NOT NULL,
    state           TEXT NOT NULL,
    snapshot_id     TEXT REFERENCES snapshot(snapshot_id),
    thesis_id       TEXT,
    error_code      TEXT,
    reason          TEXT NOT NULL DEFAULT '',
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    payload         TEXT NOT NULL
) STRICT;

CREATE INDEX idx_run_state ON run(state);

-- Stage checkpoints and usage. An interrupted stage is kept with completed = 0 rather than
-- deleted, so partial work survives a crash and is visibly incomplete.
CREATE TABLE stage_result (
    run_id            TEXT NOT NULL REFERENCES run(run_id) ON DELETE CASCADE,
    attempt           INTEGER NOT NULL,
    stage             TEXT NOT NULL,
    completed         INTEGER NOT NULL CHECK (completed IN (0, 1)),
    exit_reason       TEXT NOT NULL,
    model_requests    INTEGER NOT NULL DEFAULT 0,
    tool_calls        INTEGER NOT NULL DEFAULT 0,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    started_at        TEXT NOT NULL,
    ended_at          TEXT NOT NULL,
    payload           TEXT NOT NULL,
    PRIMARY KEY (run_id, stage, attempt)
) STRICT;

-- Full-text search over quoted passages, kept in step with evidence_span by triggers so a
-- rolled-back transaction cannot leave the index describing rows that do not exist.
CREATE VIRTUAL TABLE evidence_span_fts USING fts5(
    exact_quote,
    span_id UNINDEXED,
    content = 'evidence_span',
    content_rowid = 'rowid'
);

CREATE TRIGGER evidence_span_ai AFTER INSERT ON evidence_span BEGIN
    INSERT INTO evidence_span_fts(rowid, exact_quote, span_id)
    VALUES (new.rowid, new.exact_quote, new.span_id);
END;

CREATE TRIGGER evidence_span_ad AFTER DELETE ON evidence_span BEGIN
    INSERT INTO evidence_span_fts(evidence_span_fts, rowid, exact_quote, span_id)
    VALUES ('delete', old.rowid, old.exact_quote, old.span_id);
END;

CREATE TRIGGER evidence_span_au AFTER UPDATE ON evidence_span BEGIN
    INSERT INTO evidence_span_fts(evidence_span_fts, rowid, exact_quote, span_id)
    VALUES ('delete', old.rowid, old.exact_quote, old.span_id);
    INSERT INTO evidence_span_fts(rowid, exact_quote, span_id)
    VALUES (new.rowid, new.exact_quote, new.span_id);
END;
