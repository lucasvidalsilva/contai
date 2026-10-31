-- Marco C: persistencia privada e publicacao governada da NCM.
-- Nenhuma credencial ou role de login e criada por esta migracao.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'tax_ingest_writer') then
    execute 'create role tax_ingest_writer nologin noinherit nosuperuser nocreatedb nocreaterole noreplication';
  end if;
end
$$;

create schema tax_ingest;
create schema tax_public;

revoke all on schema tax_ingest from public, anon, authenticated;
revoke all on schema tax_public from public, anon, authenticated;

create table tax_ingest.source_registry (
  source_key text primary key,
  agency text not null,
  dataset_name text not null,
  canonical_url text not null,
  source_format text not null,
  contract_version text not null,
  parser_version text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint source_registry_key_format check (source_key ~ '^[a-z][a-z0-9_-]{1,63}$'),
  constraint source_registry_url_format check (canonical_url ~ '^https://')
);

create table tax_ingest.source_artifact (
  source_key text not null references tax_ingest.source_registry (source_key),
  artifact_sha256 text not null,
  requested_url text not null,
  final_url text not null,
  captured_at timestamptz not null,
  http_status smallint not null,
  content_type text not null,
  byte_size bigint not null,
  raw_path text not null,
  response_headers jsonb not null default '{}'::jsonb,
  status text not null,
  created_at timestamptz not null default now(),
  primary key (source_key, artifact_sha256),
  constraint source_artifact_sha256_format check (artifact_sha256 ~ '^[0-9a-f]{64}$'),
  constraint source_artifact_http_status_range check (http_status between 100 and 599),
  constraint source_artifact_byte_size_positive check (byte_size > 0),
  constraint source_artifact_status_allowed check (status in ('accepted', 'rejected'))
);

create index source_artifact_captured_at_idx
  on tax_ingest.source_artifact (source_key, captured_at desc);

create table tax_ingest.ingestion_run (
  run_id bigint generated always as identity primary key,
  source_key text not null,
  artifact_sha256 text not null,
  release_id text,
  started_at timestamptz not null,
  completed_at timestamptz not null,
  status text not null,
  error_message text,
  created_at timestamptz not null default now(),
  constraint ingestion_run_artifact_fk
    foreign key (source_key, artifact_sha256)
    references tax_ingest.source_artifact (source_key, artifact_sha256),
  constraint ingestion_run_release_sha256_format
    check (release_id is null or release_id ~ '^[0-9a-f]{64}$'),
  constraint ingestion_run_time_order check (completed_at >= started_at),
  constraint ingestion_run_status_allowed check (status in ('succeeded', 'failed')),
  constraint ingestion_run_error_correspondence check (
    (status = 'failed' and error_message is not null)
    or (status = 'succeeded' and error_message is null)
  )
);

create index ingestion_run_artifact_idx
  on tax_ingest.ingestion_run (source_key, artifact_sha256);
create index ingestion_run_release_idx
  on tax_ingest.ingestion_run (release_id)
  where release_id is not null;

create table tax_ingest.dataset_release (
  release_id text primary key,
  source_key text not null,
  artifact_sha256 text not null,
  domain text not null,
  contract_version text not null,
  source_schema_version text not null,
  source_act text not null,
  source_as_of date not null,
  snapshot_sha256 text not null,
  entry_count integer not null,
  leaf_count integer not null,
  status text not null default 'candidate',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null,
  published_at timestamptz,
  constraint dataset_release_artifact_fk
    foreign key (source_key, artifact_sha256)
    references tax_ingest.source_artifact (source_key, artifact_sha256),
  constraint dataset_release_id_sha256_format check (release_id ~ '^[0-9a-f]{64}$'),
  constraint dataset_release_snapshot_sha256_format check (snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  constraint dataset_release_domain_allowed check (domain = 'ncm'),
  constraint dataset_release_entry_count_positive check (entry_count > 0),
  constraint dataset_release_leaf_count_range check (leaf_count between 0 and entry_count),
  constraint dataset_release_status_allowed check (status in ('candidate', 'approved', 'rejected')),
  constraint dataset_release_published_correspondence check (
    (status = 'approved' and published_at is not null)
    or (status <> 'approved' and published_at is null)
  )
);

create index dataset_release_artifact_idx
  on tax_ingest.dataset_release (source_key, artifact_sha256);
create index dataset_release_domain_created_idx
  on tax_ingest.dataset_release (domain, created_at desc);

create table tax_ingest.quality_result (
  quality_result_id bigint generated always as identity primary key,
  release_id text not null references tax_ingest.dataset_release (release_id),
  check_name text not null,
  passed boolean not null,
  observed jsonb not null,
  evaluated_at timestamptz not null default now(),
  unique (release_id, check_name),
  constraint quality_result_check_name_format check (check_name ~ '^[a-z][a-z0-9_]{1,63}$')
);

create table tax_ingest.ncm_entry (
  release_id text not null references tax_ingest.dataset_release (release_id),
  code text not null,
  code_digits text not null,
  description text not null,
  level text not null,
  parent_code text,
  valid_from date not null,
  valid_to date,
  initial_act_type text not null,
  initial_act_number text not null,
  initial_act_year text not null,
  source_row_id text not null,
  primary key (release_id, code),
  unique (release_id, code_digits),
  constraint ncm_entry_parent_fk
    foreign key (release_id, parent_code)
    references tax_ingest.ncm_entry (release_id, code),
  constraint ncm_entry_code_format check (code_digits ~ '^[0-9]{2}([0-9]{2}([0-9]([0-9]([0-9]([0-9])?)?)?)?)?$'),
  constraint ncm_entry_level_allowed check (
    level in ('chapter', 'position', 'subposition_1', 'subposition_2', 'item', 'subitem')
  ),
  constraint ncm_entry_validity_order check (valid_to is null or valid_to >= valid_from),
  constraint ncm_entry_initial_act_number_format check (initial_act_number ~ '^[0-9]+$'),
  constraint ncm_entry_initial_act_year_format check (initial_act_year ~ '^[0-9]{4}$'),
  constraint ncm_entry_source_row_id_match check (source_row_id = 'Codigo:' || code)
);

create index ncm_entry_parent_idx
  on tax_ingest.ncm_entry (release_id, parent_code)
  where parent_code is not null;
create index ncm_entry_validity_idx
  on tax_ingest.ncm_entry (release_id, valid_from, valid_to);

create table tax_public.dataset_release (
  release_id text primary key,
  domain text not null,
  contract_version text not null,
  source_act text not null,
  source_as_of date not null,
  artifact_sha256 text not null,
  snapshot_sha256 text not null,
  entry_count integer not null,
  leaf_count integer not null,
  published_at timestamptz not null,
  constraint public_dataset_release_id_sha256_format check (release_id ~ '^[0-9a-f]{64}$'),
  constraint public_dataset_release_artifact_sha256_format check (artifact_sha256 ~ '^[0-9a-f]{64}$'),
  constraint public_dataset_release_snapshot_sha256_format check (snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  constraint public_dataset_release_domain_allowed check (domain = 'ncm'),
  constraint public_dataset_release_counts check (entry_count > 0 and leaf_count between 0 and entry_count)
);

create index public_dataset_release_domain_published_idx
  on tax_public.dataset_release (domain, published_at desc);

create table tax_public.dataset_current (
  domain text primary key,
  release_id text not null references tax_public.dataset_release (release_id),
  updated_at timestamptz not null,
  constraint public_dataset_current_domain_allowed check (domain = 'ncm')
);

create index public_dataset_current_release_idx
  on tax_public.dataset_current (release_id);

create table tax_public.ncm_entry (
  release_id text not null references tax_public.dataset_release (release_id),
  code text not null,
  code_digits text not null,
  description text not null,
  level text not null,
  parent_code text,
  valid_from date not null,
  valid_to date,
  initial_act_type text not null,
  initial_act_number text not null,
  initial_act_year text not null,
  source_row_id text not null,
  primary key (release_id, code),
  unique (release_id, code_digits),
  constraint public_ncm_entry_parent_fk
    foreign key (release_id, parent_code)
    references tax_public.ncm_entry (release_id, code),
  constraint public_ncm_entry_validity_order check (valid_to is null or valid_to >= valid_from)
);

create index public_ncm_entry_parent_idx
  on tax_public.ncm_entry (release_id, parent_code)
  where parent_code is not null;
create index public_ncm_entry_validity_idx
  on tax_public.ncm_entry (release_id, valid_from, valid_to);

alter table tax_public.dataset_release enable row level security;
alter table tax_public.dataset_current enable row level security;
alter table tax_public.ncm_entry enable row level security;

create policy dataset_release_public_read
  on tax_public.dataset_release for select to anon, authenticated using (true);
create policy dataset_release_writer_read
  on tax_public.dataset_release for select to tax_ingest_writer using (true);
create policy dataset_release_writer_insert
  on tax_public.dataset_release for insert to tax_ingest_writer with check (true);

create policy dataset_current_public_read
  on tax_public.dataset_current for select to anon, authenticated using (true);
create policy dataset_current_writer_read
  on tax_public.dataset_current for select to tax_ingest_writer using (true);
create policy dataset_current_writer_insert
  on tax_public.dataset_current for insert to tax_ingest_writer with check (true);
create policy dataset_current_writer_update
  on tax_public.dataset_current for update to tax_ingest_writer using (true) with check (true);

create policy ncm_entry_public_read
  on tax_public.ncm_entry for select to anon, authenticated using (true);
create policy ncm_entry_writer_read
  on tax_public.ncm_entry for select to tax_ingest_writer using (true);
create policy ncm_entry_writer_insert
  on tax_public.ncm_entry for insert to tax_ingest_writer with check (true);

create view tax_public.ncm_current
with (security_invoker = true, security_barrier = true)
as
select
  entry.release_id,
  entry.code,
  entry.code_digits,
  entry.description,
  entry.level,
  entry.parent_code,
  entry.valid_from,
  entry.valid_to,
  entry.initial_act_type,
  entry.initial_act_number,
  entry.initial_act_year,
  entry.source_row_id
from tax_public.ncm_entry as entry
join tax_public.dataset_current as current_release
  on current_release.domain = 'ncm'
 and current_release.release_id = entry.release_id;

grant usage on schema tax_ingest to tax_ingest_writer;
grant select, insert, update on tax_ingest.source_registry to tax_ingest_writer;
grant select, insert on tax_ingest.source_artifact to tax_ingest_writer;
grant select, insert on tax_ingest.ingestion_run to tax_ingest_writer;
grant select, insert, update on tax_ingest.dataset_release to tax_ingest_writer;
grant select, insert, update on tax_ingest.quality_result to tax_ingest_writer;
grant select, insert on tax_ingest.ncm_entry to tax_ingest_writer;
grant usage, select on all sequences in schema tax_ingest to tax_ingest_writer;

grant usage on schema tax_public to anon, authenticated, tax_ingest_writer;
grant select on tax_public.dataset_release, tax_public.dataset_current, tax_public.ncm_entry, tax_public.ncm_current
  to anon, authenticated;
grant select, insert on tax_public.dataset_release, tax_public.ncm_entry to tax_ingest_writer;
grant select, insert, update on tax_public.dataset_current to tax_ingest_writer;
grant select on tax_public.ncm_current to tax_ingest_writer;
