import { timingSafeEqual } from "node:crypto";

const SOURCE_HOST = "www.confaz.fazenda.gov.br";
const MAX_URL_LENGTH = 2_048;
const MAX_RESPONSE_BYTES = 4 * 1024 * 1024;
const UPSTREAM_TIMEOUT_MS = 50_000;

function jsonError(status, error) {
  return new Response(JSON.stringify({ error }), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

function hasValidKey(provided, expected) {
  if (typeof provided !== "string" || !provided || typeof expected !== "string" || !expected) return false;
  const providedBytes = Buffer.from(provided);
  const expectedBytes = Buffer.from(expected);
  return providedBytes.length === expectedBytes.length && timingSafeEqual(providedBytes, expectedBytes);
}

function parseSourceUrl(value) {
  if (typeof value !== "string" || value.length === 0 || value.length > MAX_URL_LENGTH) {
    return { error: jsonError(400, "Informe uma URL oficial válida.") };
  }

  let sourceUrl;
  try {
    sourceUrl = new URL(value);
  } catch {
    return { error: jsonError(400, "Informe uma URL oficial válida.") };
  }

  if (
    sourceUrl.protocol !== "https:" ||
    sourceUrl.hostname.toLowerCase() !== SOURCE_HOST ||
    (sourceUrl.port !== "" && sourceUrl.port !== "443") ||
    sourceUrl.username ||
    sourceUrl.password ||
    sourceUrl.hash
  ) {
    return { error: jsonError(403, "A origem solicitada não é permitida.") };
  }

  return { sourceUrl };
}

export async function GET(request) {
  if (request.method !== "GET") {
    return new Response(null, { status: 405, headers: { allow: "GET", "cache-control": "no-store" } });
  }

  const expectedKey = process.env.PROXY_CHAVE;
  if (!expectedKey) return jsonError(503, "O proxy ainda não foi configurado.");
  if (!hasValidKey(request.headers.get("x-chave"), expectedKey)) {
    return jsonError(401, "Credencial inválida.");
  }

  const { sourceUrl, error } = parseSourceUrl(new URL(request.url).searchParams.get("url"));
  if (error) return error;

  let upstream;
  try {
    upstream = await fetch(sourceUrl, {
      method: "GET",
      headers: {
        accept: "*/*",
        "user-agent": "Mozilla/5.0 (compatible; contAI-CONFAZ-proxy/1.0)",
      },
      redirect: "manual",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch (cause) {
    const timedOut = cause instanceof Error && cause.name === "TimeoutError";
    return jsonError(timedOut ? 504 : 502, timedOut ? "Tempo limite da fonte oficial excedido." : "Falha ao acessar a fonte oficial.");
  }

  if (upstream.status >= 300 && upstream.status < 400) {
    return jsonError(502, "Redirecionamento da fonte foi bloqueado.");
  }

  if (!upstream.ok) {
    const retryAfter = upstream.headers.get("retry-after");
    return new Response(null, {
      status: upstream.status,
      headers: {
        "cache-control": "no-store",
        ...(retryAfter ? { "retry-after": retryAfter } : {}),
      },
    });
  }

  const declaredSize = Number(upstream.headers.get("content-length"));
  if (Number.isFinite(declaredSize) && declaredSize > MAX_RESPONSE_BYTES) {
    return jsonError(502, "A resposta da fonte excede o limite de tamanho do proxy.");
  }

  const body = new Uint8Array(await upstream.arrayBuffer());
  if (body.byteLength > MAX_RESPONSE_BYTES) {
    return jsonError(502, "A resposta da fonte excede o limite de tamanho do proxy.");
  }

  return new Response(body.byteLength ? body : null, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/octet-stream",
      "cache-control": "no-store",
    },
  });
}
