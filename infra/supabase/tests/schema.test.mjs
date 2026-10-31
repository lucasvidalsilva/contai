import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

import { PGlite } from "@electric-sql/pglite";

const migrationsDirectory = new URL("../migrations/", import.meta.url);
const configUrl = new URL("../config.toml", import.meta.url);

async function migrationSql() {
  const migrations = (await readdir(migrationsDirectory)).filter((name) => name.endsWith(".sql")).sort();
  assert.ok(migrations.length > 0, "ao menos uma migracao deve existir");
  const contents = await Promise.all(migrations.map((name) => readFile(new URL(name, migrationsDirectory), "utf8")));
  return contents.join("\n");
}

async function expectDenied(action) {
  await assert.rejects(action, /permission denied|row-level security/i);
}

test("migração cria fronteira privada e leitura pública governada", async () => {
  const config = await readFile(configUrl, "utf8");
  assert.match(config, /schemas = \["tax_public", "graphql_public"\]/);
  assert.match(config, /auto_expose_new_tables = false/);

  const db = new PGlite();
  await db.exec("create role anon nologin; create role authenticated nologin; create role service_role nologin;");
  await db.exec(await migrationSql());

  await db.exec("set role tax_ingest_writer; reset role");

  const schemas = await db.query(
    "select schema_name from information_schema.schemata where schema_name in ('tax_ingest', 'tax_public') order by 1",
  );
  assert.deepEqual(schemas.rows, [{ schema_name: "tax_ingest" }, { schema_name: "tax_public" }]);

  const rls = await db.query(`
    select c.relname
    from pg_class as c
    join pg_namespace as n on n.oid = c.relnamespace
    where n.nspname = 'tax_public' and c.relkind = 'r' and c.relrowsecurity
    order by c.relname
  `);
  assert.deepEqual(rls.rows, [
    { relname: "dataset_current" },
    { relname: "dataset_release" },
    { relname: "ncm_entry" },
    { relname: "tipi_entry" },
  ]);

  const views = await db.query(`
    select c.reloptions
    from pg_class as c
    join pg_namespace as n on n.oid = c.relnamespace
    where n.nspname = 'tax_public' and c.relname in ('ncm_current', 'tipi_current')
    order by c.relname
  `);
  assert.equal(views.rows.length, 2);
  assert.ok(views.rows.every((view) => view.reloptions.includes("security_invoker=true")));

  await db.exec("set role tax_ingest_writer");
  await db.exec(`
    insert into tax_public.dataset_release (
      release_id, domain, contract_version, source_act, source_as_of,
      artifact_sha256, snapshot_sha256, entry_count, leaf_count, published_at
    ) values (
      repeat('a', 64), 'ncm', 'ncm-v1', 'ato de teste', date '2026-10-30',
      repeat('b', 64), repeat('c', 64), 1, 0, now()
    );
    insert into tax_public.ncm_entry (
      release_id, code, code_digits, description, level, parent_code,
      valid_from, valid_to, initial_act_type, initial_act_number, initial_act_year, source_row_id
    ) values (
      repeat('a', 64), '01', '01', 'Animais vivos.', 'chapter', null,
      date '2022-04-01', null, 'Res Camex', '272', '2021', 'Codigo:01'
    );
    insert into tax_public.dataset_current (domain, release_id, updated_at)
    values ('ncm', repeat('a', 64), now());

    insert into tax_public.dataset_release (
      release_id, domain, contract_version, source_act, source_as_of,
      artifact_sha256, snapshot_sha256, entry_count, leaf_count, published_at
    ) values (
      repeat('d', 64), 'tipi', 'tipi-v1', 'Decreto teste', null,
      repeat('e', 64), repeat('f', 64), 1, 0, now()
    );
    insert into tax_public.tipi_entry (release_id, ncm_code, ex_key, ex_code, description, ipi_rate)
    values (repeat('d', 64), '0101.21.00', '', null, 'Reprodutores de raça pura', 'NT');
    insert into tax_public.dataset_current (domain, release_id, updated_at)
    values ('tipi', repeat('d', 64), now());
  `);
  await expectDenied(() => db.exec("delete from tax_public.dataset_current where domain = 'ncm'"));

  await db.exec("reset role; set role anon");
  const current = await db.query("select code, description from tax_public.ncm_current");
  assert.deepEqual(current.rows, [{ code: "01", description: "Animais vivos." }]);
  const currentTipi = await db.query("select ncm_code, ex_code, ipi_rate from tax_public.tipi_current");
  assert.deepEqual(currentTipi.rows, [{ ncm_code: "0101.21.00", ex_code: null, ipi_rate: "NT" }]);
  await expectDenied(() => db.query("select * from tax_ingest.source_registry"));
  await expectDenied(() =>
    db.exec("insert into tax_public.dataset_current (domain, release_id, updated_at) values ('ncm', repeat('a', 64), now())"),
  );

  await db.close();
});
