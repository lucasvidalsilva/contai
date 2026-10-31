-- Extende o catalogo governado para TIPI sem alterar as publicacoes existentes.
alter table tax_ingest.dataset_release
  drop constraint dataset_release_domain_allowed,
  add constraint dataset_release_domain_allowed check (domain in ('ncm', 'tipi')),
  alter column source_as_of drop not null;

alter table tax_public.dataset_release
  drop constraint public_dataset_release_domain_allowed,
  add constraint public_dataset_release_domain_allowed check (domain in ('ncm', 'tipi')),
  alter column source_as_of drop not null;

alter table tax_public.dataset_current
  drop constraint public_dataset_current_domain_allowed,
  add constraint public_dataset_current_domain_allowed check (domain in ('ncm', 'tipi'));

create table tax_ingest.tipi_entry (
  release_id text not null references tax_ingest.dataset_release (release_id),
  ncm_code text not null,
  ex_key text not null,
  ex_code text,
  description text not null,
  ipi_rate text,
  primary key (release_id, ncm_code, ex_key),
  constraint tipi_entry_ncm_format check (ncm_code ~ '^[0-9]{4}\.[0-9]{2}\.[0-9]{2}$'),
  constraint tipi_entry_ex_key_match check (ex_key = coalesce(ex_code, '')),
  constraint tipi_entry_ex_format check (ex_code is null or ex_code ~ '^[0-9]+$'),
  constraint tipi_entry_rate_format check (ipi_rate is null or ipi_rate = 'NT' or ipi_rate ~ '^[0-9]+(\.[0-9]+)?$')
);

create index tipi_entry_code_idx on tax_ingest.tipi_entry (ncm_code, ex_key);

create table tax_public.tipi_entry (
  release_id text not null references tax_public.dataset_release (release_id),
  ncm_code text not null,
  ex_key text not null,
  ex_code text,
  description text not null,
  ipi_rate text,
  primary key (release_id, ncm_code, ex_key),
  constraint public_tipi_entry_ncm_format check (ncm_code ~ '^[0-9]{4}\.[0-9]{2}\.[0-9]{2}$'),
  constraint public_tipi_entry_ex_key_match check (ex_key = coalesce(ex_code, '')),
  constraint public_tipi_entry_ex_format check (ex_code is null or ex_code ~ '^[0-9]+$'),
  constraint public_tipi_entry_rate_format check (ipi_rate is null or ipi_rate = 'NT' or ipi_rate ~ '^[0-9]+(\.[0-9]+)?$')
);

create index public_tipi_entry_code_idx on tax_public.tipi_entry (ncm_code, ex_key);
alter table tax_public.tipi_entry enable row level security;

create policy tipi_entry_public_read
  on tax_public.tipi_entry for select to anon, authenticated using (true);
create policy tipi_entry_writer_read
  on tax_public.tipi_entry for select to tax_ingest_writer using (true);
create policy tipi_entry_writer_insert
  on tax_public.tipi_entry for insert to tax_ingest_writer with check (true);

create view tax_public.tipi_current
with (security_invoker = true, security_barrier = true)
as
select entry.release_id, entry.ncm_code, entry.ex_code, entry.description, entry.ipi_rate
from tax_public.tipi_entry as entry
join tax_public.dataset_current as current_release
  on current_release.domain = 'tipi'
 and current_release.release_id = entry.release_id;

grant select, insert on tax_ingest.tipi_entry to tax_ingest_writer;
grant select on tax_public.tipi_entry, tax_public.tipi_current to anon, authenticated;
grant select, insert on tax_public.tipi_entry to tax_ingest_writer;
grant select on tax_public.tipi_current to tax_ingest_writer;
