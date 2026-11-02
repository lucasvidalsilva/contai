-- Capturas repetidas do mesmo bruto mantêm observações temporais próprias.
create table tax_ingest.source_artifact_observation (
  observation_id bigint generated always as identity primary key,
  source_key text not null,
  artifact_sha256 text not null,
  captured_at timestamptz not null,
  requested_url text not null,
  final_url text not null,
  http_status smallint not null,
  content_type text not null,
  byte_size bigint not null,
  response_headers jsonb not null default '{}'::jsonb,
  status text not null,
  workflow_run_id text,
  created_at timestamptz not null default now(),
  foreign key (source_key, artifact_sha256)
    references tax_ingest.source_artifact (source_key, artifact_sha256),
  constraint source_artifact_observation_http_status check (http_status between 100 and 599),
  constraint source_artifact_observation_size_positive check (byte_size > 0),
  constraint source_artifact_observation_status_allowed check (status in ('accepted', 'rejected')),
  unique (source_key, artifact_sha256, captured_at)
);

create index source_artifact_observation_captured_at_idx
  on tax_ingest.source_artifact_observation (source_key, captured_at desc);

alter table tax_ingest.source_artifact_observation enable row level security;
revoke all on tax_ingest.source_artifact_observation from public, anon, authenticated;
grant select, insert on tax_ingest.source_artifact_observation to tax_ingest_writer;
grant usage, select on sequence tax_ingest.source_artifact_observation_observation_id_seq to tax_ingest_writer;

create policy source_artifact_observation_writer_read
  on tax_ingest.source_artifact_observation for select to tax_ingest_writer using (true);
create policy source_artifact_observation_writer_insert
  on tax_ingest.source_artifact_observation for insert to tax_ingest_writer with check (true);

-- Backfill primeira captura conhecida para metadados que antecedem esta migration.
insert into tax_ingest.source_artifact_observation (
  source_key, artifact_sha256, captured_at, requested_url, final_url,
  http_status, content_type, byte_size, response_headers, status
)
select source_key, artifact_sha256, captured_at, requested_url, final_url,
       http_status, content_type, byte_size, response_headers, status
from tax_ingest.source_artifact
on conflict (source_key, artifact_sha256, captured_at) do nothing;
