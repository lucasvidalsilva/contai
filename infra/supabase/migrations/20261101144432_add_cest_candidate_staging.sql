-- Candidatos CEST ficam privados e sem release publicavel ate curadoria juridica.
create table tax_ingest.cest_candidate_set (
  candidate_set_sha256 text primary key,
  source_key text not null references tax_ingest.source_registry (source_key),
  artifact_sha256 text not null,
  parser_id text not null,
  contract_version text not null,
  candidate_count integer not null,
  segment_matched_count integer not null,
  segment_unmatched_count integer not null,
  status text not null default 'candidates_unresolved',
  captured_at timestamptz not null,
  created_at timestamptz not null default now(),
  foreign key (source_key, artifact_sha256)
    references tax_ingest.source_artifact (source_key, artifact_sha256),
  constraint cest_candidate_set_hash_format check (candidate_set_sha256 ~ '^[0-9a-f]{64}$'),
  constraint cest_candidate_set_artifact_hash_format check (artifact_sha256 ~ '^[0-9a-f]{64}$'),
  constraint cest_candidate_set_parser check (parser_id = 'cest-candidate-v5'),
  constraint cest_candidate_set_status check (status = 'candidates_unresolved'),
  constraint cest_candidate_set_counts check (
    candidate_count > 0 and segment_matched_count >= 0 and segment_unmatched_count >= 0
    and segment_matched_count + segment_unmatched_count = candidate_count
  )
);

create table tax_ingest.cest_candidate (
  candidate_set_sha256 text not null references tax_ingest.cest_candidate_set (candidate_set_sha256),
  occurrence_number integer not null,
  source_table_index integer not null,
  source_row_index integer not null,
  item_label text not null,
  cest_code text not null,
  ncm_sh_raw text not null,
  description text not null,
  source_context jsonb not null,
  segment_code text not null,
  segment_name text,
  source_cell_classes jsonb not null,
  source_cell_tags jsonb not null,
  legal_status text not null default 'unresolved',
  primary key (candidate_set_sha256, occurrence_number),
  constraint cest_candidate_occurrence_positive check (occurrence_number > 0),
  constraint cest_candidate_indexes_nonnegative check (source_table_index >= 0 and source_row_index > 0),
  constraint cest_candidate_code_format check (cest_code ~ '^[0-9]{2}\.[0-9]{3}\.[0-9]{2}$'),
  constraint cest_candidate_segment_format check (segment_code ~ '^[0-9]{2}$'),
  constraint cest_candidate_status_unresolved check (legal_status = 'unresolved'),
  constraint cest_candidate_json_arrays check (
    jsonb_typeof(source_context) = 'array'
    and jsonb_typeof(source_cell_classes) = 'array'
    and jsonb_typeof(source_cell_tags) = 'array'
  )
);

create index cest_candidate_code_idx on tax_ingest.cest_candidate (cest_code, candidate_set_sha256);

grant select, insert on tax_ingest.cest_candidate_set, tax_ingest.cest_candidate to tax_ingest_writer;
