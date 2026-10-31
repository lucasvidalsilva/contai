import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { parseDocument } from "yaml";

async function readWorkflow(name) {
  const source = await readFile(new URL(`../workflows/${name}`, import.meta.url), "utf8");
  const document = parseDocument(source, { uniqueKeys: true });
  assert.deepEqual(document.errors, [], `${name} deve ser YAML válido`);
  const value = document.toJS();
  assert.equal(typeof value.on, "object", `${name} deve declarar gatilhos`);
  assert.deepEqual(value.permissions, { contents: "read" }, `${name} deve usar permissões mínimas`);
  return value;
}

test("CI executa em pull requests e push para main sem secrets", async () => {
  const workflow = await readWorkflow("ci.yml");

  assert.ok(Object.hasOwn(workflow.on, "pull_request"));
  assert.deepEqual(workflow.on.push.branches, ["main"]);
  assert.ok(workflow.jobs["tax-data"].steps.some((step) => step.run?.includes("pytest")));
  assert.ok(workflow.jobs["tax-data"].steps.some((step) => step.run?.includes("test:db-integration")));
  assert.ok(workflow.jobs["tax-data"].steps.some((step) => step.run?.includes("test:workflows")));
});

test("captura NCM é agendada e manual, sem acesso de publicação", async () => {
  const workflow = await readWorkflow("capture.yml");

  assert.deepEqual(Object.keys(workflow.on).sort(), ["schedule", "workflow_dispatch"].sort());
  assert.deepEqual(workflow.on.schedule, [{ cron: "30 8 * * *" }]);
  assert.ok(workflow.jobs["capture-ncm"].steps.some((step) => step.run?.includes("capture-ncm")));
  assert.ok(workflow.jobs["capture-ncm"].steps.some((step) => step.uses?.startsWith("actions/upload-artifact@")));
  assert.ok(!workflow.jobs["capture-ncm"].steps.some((step) => step.run?.includes("publish-ncm")));
});

test("captura TIPI é manual, gera artefato e não publica no banco", async () => {
  const workflow = await readWorkflow("capture-tipi.yml");

  assert.deepEqual(Object.keys(workflow.on), ["workflow_dispatch"]);
  assert.ok(workflow.jobs["capture-tipi"].steps.some((step) => step.run?.includes("capture-tipi")));
  assert.ok(workflow.jobs["capture-tipi"].steps.some((step) => step.uses?.startsWith("actions/upload-artifact@")));
  assert.ok(!workflow.jobs["capture-tipi"].steps.some((step) => step.run?.includes("publish-tipi")));
});

test("captura IBS/CBS é manual, faz uma requisição e não publica no banco", async () => {
  const workflow = await readWorkflow("capture-ibs-cbs.yml");

  assert.deepEqual(Object.keys(workflow.on), ["workflow_dispatch"]);
  const capture = workflow.jobs["capture-ibs-cbs"].steps.find((step) => step.run?.includes("capture-ibs-cbs"));
  assert.ok(capture);
  assert.equal(capture.env.CAPTURE_TIMEOUT, "${{ inputs.timeout || '60' }}");
  assert.ok(workflow.jobs["capture-ibs-cbs"].steps.some((step) => step.uses?.startsWith("actions/upload-artifact@")));
  assert.ok(!workflow.jobs["capture-ibs-cbs"].steps.some((step) => step.run?.includes("publish-ibs-cbs")));
  assert.ok(!workflow.jobs["capture-ibs-cbs"].steps.some((step) => step.env?.SUPABASE_URL));
});
