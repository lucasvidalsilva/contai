import assert from "node:assert/strict";
import test from "node:test";

import { GET } from "../api/buscar.js";

const TEST_KEY = "test-only-secret-key";

async function callProxy(t, sourceUrl, { key = TEST_KEY, fetchImpl } = {}) {
  const priorKey = process.env.PROXY_CHAVE;
  const priorFetch = globalThis.fetch;
  process.env.PROXY_CHAVE = TEST_KEY;
  if (fetchImpl) globalThis.fetch = fetchImpl;
  t.after(() => {
    if (priorKey === undefined) delete process.env.PROXY_CHAVE;
    else process.env.PROXY_CHAVE = priorKey;
    globalThis.fetch = priorFetch;
  });

  const requestUrl = new URL("https://proxy.example/api/buscar");
  if (sourceUrl !== undefined) requestUrl.searchParams.set("url", sourceUrl);
  return GET(new Request(requestUrl, { headers: key ? { "x-chave": key } : {} }));
}

test("requires the configured secret before fetching", async (t) => {
  let fetchCalls = 0;
  const response = await callProxy(t, "https://www.confaz.fazenda.gov.br/sitemap.xml.gz", {
    key: "wrong-key",
    fetchImpl: async () => {
      fetchCalls += 1;
      return new Response("unexpected");
    },
  });

  assert.equal(response.status, 401);
  assert.equal(fetchCalls, 0);
});

test("rejects non-CONFAZ targets before fetching", async (t) => {
  let fetchCalls = 0;
  const response = await callProxy(t, "https://example.com/file", {
    fetchImpl: async () => {
      fetchCalls += 1;
      return new Response("unexpected");
    },
  });

  assert.equal(response.status, 403);
  assert.equal(fetchCalls, 0);
});

test("rejects non-HTTPS and credential-bearing source URLs", async (t) => {
  const httpResponse = await callProxy(t, "http://www.confaz.fazenda.gov.br/sitemap.xml.gz");
  const credentialResponse = await callProxy(t, "https://user:pass@www.confaz.fazenda.gov.br/sitemap.xml.gz");

  assert.equal(httpResponse.status, 403);
  assert.equal(credentialResponse.status, 403);
});

test("fetches the allowlisted URL and returns only source content headers", async (t) => {
  let requestedUrl;
  let requestedOptions;
  const response = await callProxy(t, "https://www.confaz.fazenda.gov.br/sitemap.xml.gz", {
    fetchImpl: async (url, options) => {
      requestedUrl = url.href;
      requestedOptions = options;
      return new Response("official-data", {
        status: 200,
        headers: { "content-type": "application/octet-stream", "set-cookie": "must-not-escape" },
      });
    },
  });

  assert.equal(response.status, 200);
  assert.equal(await response.text(), "official-data");
  assert.equal(response.headers.get("content-type"), "application/octet-stream");
  assert.equal(response.headers.get("set-cookie"), null);
  assert.equal(requestedUrl, "https://www.confaz.fazenda.gov.br/sitemap.xml.gz");
  assert.equal(requestedOptions.method, "GET");
  assert.equal(requestedOptions.redirect, "manual");
  assert.equal(requestedOptions.headers["x-chave"], undefined);
});

test("does not follow upstream redirects", async (t) => {
  const response = await callProxy(t, "https://www.confaz.fazenda.gov.br/sitemap.xml.gz", {
    fetchImpl: async () => new Response(null, { status: 302, headers: { location: "https://attacker.example/" } }),
  });

  assert.equal(response.status, 502);
  assert.equal(response.headers.get("location"), null);
});

test("rejects oversized source bodies", async (t) => {
  const response = await callProxy(t, "https://www.confaz.fazenda.gov.br/sitemap.xml.gz", {
    fetchImpl: async () =>
      new Response("small", {
        status: 200,
        headers: { "content-length": String(4 * 1024 * 1024 + 1) },
      }),
  });

  assert.equal(response.status, 502);
});
