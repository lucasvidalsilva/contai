-- Amplia a publicacao governada para o catalogo oficial IBS/CBS.
alter table tax_ingest.dataset_release
  drop constraint dataset_release_domain_allowed,
  add constraint dataset_release_domain_allowed check (domain in ('ncm', 'tipi', 'ibs_cbs'));

alter table tax_public.dataset_release
  drop constraint public_dataset_release_domain_allowed,
  add constraint public_dataset_release_domain_allowed check (domain in ('ncm', 'tipi', 'ibs_cbs'));

alter table tax_public.dataset_current
  drop constraint public_dataset_current_domain_allowed,
  add constraint public_dataset_current_domain_allowed check (domain in ('ncm', 'tipi', 'ibs_cbs'));

create table tax_ingest.ibs_cbs_cst (
  release_id text not null references tax_ingest.dataset_release (release_id),
  cst_code text not null check (cst_code ~ '^[0-9]{3}$'),
  description text not null,
  valid_from timestamp without time zone not null,
  valid_to timestamp without time zone,
  attributes jsonb not null check (jsonb_typeof(attributes) = 'object'),
  primary key (release_id, cst_code),
  check (valid_to is null or valid_to >= valid_from)
);

create table tax_ingest.ibs_cbs_classification (
  release_id text not null references tax_ingest.dataset_release (release_id),
  cclasstrib_code text not null check (cclasstrib_code ~ '^[0-9]{6}$'),
  cst_code text not null,
  description text not null,
  short_description text not null,
  valid_from timestamp without time zone not null,
  valid_to timestamp without time zone,
  legislation_url text,
  attributes jsonb not null check (jsonb_typeof(attributes) = 'object'),
  primary key (release_id, cclasstrib_code),
  foreign key (release_id, cst_code) references tax_ingest.ibs_cbs_cst (release_id, cst_code),
  check (valid_to is null or valid_to >= valid_from)
);

create index ibs_cbs_classification_cst_idx
  on tax_ingest.ibs_cbs_classification (release_id, cst_code, cclasstrib_code);

create table tax_ingest.ibs_cbs_annex_link (
  release_id text not null,
  cclasstrib_code text not null,
  source_record_id bigint not null,
  annex_number integer not null,
  code text not null,
  code_type text not null check (code_type in ('NCM', 'NBS')),
  permission text,
  condition text,
  exception text,
  observation text,
  valid_from timestamp without time zone not null,
  valid_to timestamp without time zone,
  annex_item_number integer,
  item_description text,
  annex_description text,
  attributes jsonb not null check (jsonb_typeof(attributes) = 'object'),
  primary key (release_id, cclasstrib_code, source_record_id),
  foreign key (release_id, cclasstrib_code)
    references tax_ingest.ibs_cbs_classification (release_id, cclasstrib_code),
  check (code ~ '^[0-9]+$'),
  check (valid_to is null or valid_to >= valid_from)
);

create index ibs_cbs_annex_code_idx
  on tax_ingest.ibs_cbs_annex_link (release_id, code_type, code, cclasstrib_code);

create table tax_public.ibs_cbs_cst (
  release_id text not null references tax_public.dataset_release (release_id),
  cst_code text not null check (cst_code ~ '^[0-9]{3}$'),
  description text not null,
  valid_from timestamp without time zone not null,
  valid_to timestamp without time zone,
  attributes jsonb not null check (jsonb_typeof(attributes) = 'object'),
  primary key (release_id, cst_code),
  check (valid_to is null or valid_to >= valid_from)
);

create table tax_public.ibs_cbs_classification (
  release_id text not null references tax_public.dataset_release (release_id),
  cclasstrib_code text not null check (cclasstrib_code ~ '^[0-9]{6}$'),
  cst_code text not null,
  description text not null,
  short_description text not null,
  valid_from timestamp without time zone not null,
  valid_to timestamp without time zone,
  legislation_url text,
  attributes jsonb not null check (jsonb_typeof(attributes) = 'object'),
  primary key (release_id, cclasstrib_code),
  foreign key (release_id, cst_code) references tax_public.ibs_cbs_cst (release_id, cst_code),
  check (valid_to is null or valid_to >= valid_from)
);

create table tax_public.ibs_cbs_annex_link (
  release_id text not null,
  cclasstrib_code text not null,
  source_record_id bigint not null,
  annex_number integer not null,
  code text not null,
  code_type text not null check (code_type in ('NCM', 'NBS')),
  permission text,
  condition text,
  exception text,
  observation text,
  valid_from timestamp without time zone not null,
  valid_to timestamp without time zone,
  annex_item_number integer,
  item_description text,
  annex_description text,
  attributes jsonb not null check (jsonb_typeof(attributes) = 'object'),
  primary key (release_id, cclasstrib_code, source_record_id),
  foreign key (release_id, cclasstrib_code)
    references tax_public.ibs_cbs_classification (release_id, cclasstrib_code),
  check (code ~ '^[0-9]+$'),
  check (valid_to is null or valid_to >= valid_from)
);

create index public_ibs_cbs_classification_cst_idx
  on tax_public.ibs_cbs_classification (release_id, cst_code, cclasstrib_code);
create index public_ibs_cbs_annex_code_idx
  on tax_public.ibs_cbs_annex_link (release_id, code_type, code, cclasstrib_code);

alter table tax_public.ibs_cbs_cst enable row level security;
alter table tax_public.ibs_cbs_classification enable row level security;
alter table tax_public.ibs_cbs_annex_link enable row level security;

create policy ibs_cbs_cst_public_read on tax_public.ibs_cbs_cst
  for select to anon, authenticated using (true);
create policy ibs_cbs_cst_writer_read on tax_public.ibs_cbs_cst
  for select to tax_ingest_writer using (true);
create policy ibs_cbs_cst_writer_insert on tax_public.ibs_cbs_cst
  for insert to tax_ingest_writer with check (true);

create policy ibs_cbs_classification_public_read on tax_public.ibs_cbs_classification
  for select to anon, authenticated using (true);
create policy ibs_cbs_classification_writer_read on tax_public.ibs_cbs_classification
  for select to tax_ingest_writer using (true);
create policy ibs_cbs_classification_writer_insert on tax_public.ibs_cbs_classification
  for insert to tax_ingest_writer with check (true);

create policy ibs_cbs_annex_public_read on tax_public.ibs_cbs_annex_link
  for select to anon, authenticated using (true);
create policy ibs_cbs_annex_writer_read on tax_public.ibs_cbs_annex_link
  for select to tax_ingest_writer using (true);
create policy ibs_cbs_annex_writer_insert on tax_public.ibs_cbs_annex_link
  for insert to tax_ingest_writer with check (true);

create view tax_public.ibs_cbs_cst_current
with (security_invoker = true, security_barrier = true)
as
select cst.release_id, cst.cst_code, cst.description, cst.valid_from, cst.valid_to, cst.attributes
from tax_public.ibs_cbs_cst as cst
join tax_public.dataset_current as current_release
  on current_release.domain = 'ibs_cbs'
 and current_release.release_id = cst.release_id;

create view tax_public.ibs_cbs_classification_current
with (security_invoker = true, security_barrier = true)
as
select classification.release_id, classification.cclasstrib_code, classification.cst_code,
       classification.description, classification.short_description, classification.valid_from,
       classification.valid_to, classification.legislation_url, classification.attributes
from tax_public.ibs_cbs_classification as classification
join tax_public.dataset_current as current_release
  on current_release.domain = 'ibs_cbs'
 and current_release.release_id = classification.release_id;

create view tax_public.ibs_cbs_annex_current
with (security_invoker = true, security_barrier = true)
as
select link.*
from tax_public.ibs_cbs_annex_link as link
join tax_public.dataset_current as current_release
  on current_release.domain = 'ibs_cbs'
 and current_release.release_id = link.release_id;

grant select, insert on tax_ingest.ibs_cbs_cst, tax_ingest.ibs_cbs_classification,
  tax_ingest.ibs_cbs_annex_link to tax_ingest_writer;
grant select on tax_public.ibs_cbs_cst, tax_public.ibs_cbs_classification,
  tax_public.ibs_cbs_annex_link, tax_public.ibs_cbs_cst_current,
  tax_public.ibs_cbs_classification_current, tax_public.ibs_cbs_annex_current to anon, authenticated;
grant select, insert on tax_public.ibs_cbs_cst, tax_public.ibs_cbs_classification,
  tax_public.ibs_cbs_annex_link to tax_ingest_writer;
grant select on tax_public.ibs_cbs_cst_current, tax_public.ibs_cbs_classification_current,
  tax_public.ibs_cbs_annex_current to tax_ingest_writer;
