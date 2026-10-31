import { spawn } from "node:child_process";
import { readFile, readdir } from "node:fs/promises";

import { PGlite } from "@electric-sql/pglite";
import { PGLiteSocketServer } from "@electric-sql/pglite-socket";

const migrationsDirectory = new URL("../migrations/", import.meta.url);
const migrations = (await readdir(migrationsDirectory)).filter((name) => name.endsWith(".sql")).sort();
if (migrations.length !== 1) {
  throw new Error("o runner deve acompanhar explicitamente a primeira migracao");
}

const db = await PGlite.create();
const server = new PGLiteSocketServer({ db, host: "127.0.0.1", port: 0, maxConnections: 2 });

try {
  await db.exec("create role anon nologin; create role authenticated nologin; create role service_role nologin;");
  await db.exec(await readFile(new URL(migrations[0], migrationsDirectory), "utf8"));
  await server.start();
  const databaseUrl = `postgresql://postgres@${server.getServerConn()}/postgres?sslmode=disable`;

  const command = process.platform === "win32" ? "uv.exe" : "uv";
  const child = spawn(
    command,
    [
      "--cache-dir",
      ".uv-cache",
      "run",
      "--project",
      "packages/tax-data",
      "pytest",
      "packages/tax-data/tests/integration",
    ],
    {
      cwd: process.cwd(),
      env: { ...process.env, CONTAI_TEST_DATABASE_URL: databaseUrl },
      shell: false,
      stdio: "inherit",
    },
  );
  const exitCode = await new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (code) => resolve(code ?? 1));
  });
  if (exitCode !== 0) {
    throw new Error(`testes de integracao falharam com codigo ${exitCode}`);
  }
} finally {
  await server.stop();
  await db.close();
}
