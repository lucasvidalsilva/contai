-- O PostgreSQL 17 concede ao criador de uma role SET FALSE por padrao.
-- A pipeline conecta como postgres no ambiente dev e reduz privilegios no
-- inicio de cada transacao com SET LOCAL ROLE tax_ingest_writer.
grant tax_ingest_writer to postgres
with inherit false, set true, admin false;
