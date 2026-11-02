-- Staging privado de estructura literal de documentos oficiais.
-- Nenhuma vigencia, relacao normativa ou regra fiscal e inferida.

create table tax_ingest.legal_block_set (
  source_key text not null,
  artifact_sha256 text not null,
  contract_version text not null,
  snapshot_sha256 text not null,
  source_url text not null,
  document_kind text not null,
  source_lastmod text,
  captured_at timestamptz not null,
  block_count integer not null,
  interpretation_status text not null default 'not_performed',
  created_at timestamptz not null default now(),
  primary key (source_key, artifact_sha256, contract_version),
  foreign key (source_key, artifact_sha256)
    references tax_ingest.source_artifact (source_key, artifact_sha256),
  constraint legal_block_set_artifact_sha256_format check (artifact_sha256 ~ '^[0-9a-f]{64}$'),
  constraint legal_block_set_snapshot_sha256_format check (snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  constraint legal_block_set_source_url_https check (source_url ~ '^https://'),
  constraint legal_block_set_document_kind check (
    document_kind in ('current', 'original', 'veto', 'promulgation', 'confaz_act')
  ),
  constraint legal_block_set_count_positive check (block_count > 0),
  constraint legal_block_set_interpretation_not_performed check (interpretation_status = 'not_performed')
);

create index legal_block_set_source_captured_idx
  on tax_ingest.legal_block_set (source_key, captured_at desc);

create table tax_ingest.legal_document_block (
  source_key text not null,
  artifact_sha256 text not null,
  contract_version text not null,
  source_block_index integer not null,
  source_tag text not null,
  source_class text,
  marker_kind text,
  marker text,
  block_text text not null,
  primary key (source_key, artifact_sha256, contract_version, source_block_index),
  foreign key (source_key, artifact_sha256, contract_version)
    references tax_ingest.legal_block_set (source_key, artifact_sha256, contract_version),
  constraint legal_document_block_index_nonnegative check (source_block_index >= 0),
  constraint legal_document_block_source_tag check (source_tag in ('p', 'td', 'th')),
  constraint legal_document_block_marker_kind check (
    marker_kind is null or marker_kind in (
      'article', 'paragraph', 'sole_paragraph', 'roman_item', 'letter_item', 'numbered_item', 'text'
    )
  ),
  constraint legal_document_block_marker_requires_kind check (marker_kind is not null or marker is null),
  constraint legal_document_block_text_nonempty check (length(btrim(block_text)) > 0)
);

create index legal_document_block_marker_idx
  on tax_ingest.legal_document_block (source_key, marker_kind, marker, artifact_sha256)
  where marker_kind is not null;

alter table tax_ingest.legal_block_set enable row level security;
alter table tax_ingest.legal_document_block enable row level security;

create policy legal_block_set_writer_read
  on tax_ingest.legal_block_set for select to tax_ingest_writer using (true);
create policy legal_block_set_writer_insert
  on tax_ingest.legal_block_set for insert to tax_ingest_writer with check (true);
create policy legal_document_block_writer_read
  on tax_ingest.legal_document_block for select to tax_ingest_writer using (true);
create policy legal_document_block_writer_insert
  on tax_ingest.legal_document_block for insert to tax_ingest_writer with check (true);

revoke all on tax_ingest.legal_block_set, tax_ingest.legal_document_block
  from public, anon, authenticated;
grant select, insert on tax_ingest.legal_block_set, tax_ingest.legal_document_block
  to tax_ingest_writer;
