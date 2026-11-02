-- Mantem o conteudo original junto da proveniencia, somente no schema privado.
create table tax_ingest.source_artifact_payload (
  source_key text not null,
  artifact_sha256 text not null,
  byte_size bigint not null,
  raw_content bytea not null,
  archived_at timestamptz not null default now(),
  primary key (source_key, artifact_sha256),
  foreign key (source_key, artifact_sha256)
    references tax_ingest.source_artifact (source_key, artifact_sha256),
  constraint source_artifact_payload_size_positive check (byte_size > 0),
  constraint source_artifact_payload_size_matches check (octet_length(raw_content) = byte_size)
);

alter table tax_ingest.source_artifact_payload enable row level security;
revoke all on tax_ingest.source_artifact_payload from public, anon, authenticated;
grant select, insert on tax_ingest.source_artifact_payload to tax_ingest_writer;

create policy source_artifact_payload_writer_read
  on tax_ingest.source_artifact_payload for select to tax_ingest_writer using (true);
create policy source_artifact_payload_writer_insert
  on tax_ingest.source_artifact_payload for insert to tax_ingest_writer with check (true);
