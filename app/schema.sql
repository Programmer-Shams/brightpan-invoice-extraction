-- Invoice extraction schema. Lives in its own schema so it never collides with other tables in the database.
create schema if not exists invoice_extraction;
set search_path to invoice_extraction;

-- One row per uploaded document. status doubles as the job queue (claimed with FOR UPDATE SKIP LOCKED).
create table if not exists documents (
    id               uuid primary key default gen_random_uuid(),
    filename         text not null,
    content_type     text not null,
    source           text not null default 'upload',     -- upload | email | eval
    file_bytes       bytea not null,
    sha256           text not null,
    pages            int,
    status           text not null default 'queued' check (status in ('queued', 'processing', 'done', 'failed')),
    attempts         int not null default 0,
    error            text,
    received_at      timestamptz not null default now(),
    started_at       timestamptz,
    finished_at      timestamptz
);
create index if not exists documents_queue on documents (received_at) where status = 'queued';
alter table documents add column if not exists retry_at timestamptz;      -- not before this time (retry backoff)
alter table documents add column if not exists failure_usage jsonb;       -- tokens and cost of calls that failed

-- The extracted, validated record (BUILD_SPEC schema) plus model usage.
create table if not exists extractions (
    document_id      uuid primary key references documents(id) on delete cascade,
    record           jsonb not null,
    vendor_name      text,
    invoice_number   text,
    duplicate_key    text,
    route            text not null check (route in ('auto', 'review')),
    flags            text[] not null default '{}',
    input_mode       text,
    model            text,
    input_tokens     int,
    output_tokens    int,
    cost_usd         numeric(10, 6),
    request_id       text,
    created_at       timestamptz not null default now()
);
alter table extractions add column if not exists outputs_status text;  -- sent | skipped:<why> | failed:<why>
alter table extractions add column if not exists outputs_attempts int not null default 0;
alter table extractions add column if not exists outputs_claimed_at timestamptz;  -- when a sender took the delivery
create index if not exists extractions_duplicate_key on extractions (duplicate_key);

-- Documents waiting for a person. resolution is set by the reviewer.
create table if not exists review_queue (
    document_id      uuid primary key references documents(id) on delete cascade,
    reasons          text[] not null,
    status           text not null default 'open' check (status in ('open', 'approved', 'rejected')),
    reviewer_note    text,
    created_at       timestamptz not null default now(),
    resolved_at      timestamptz
);
