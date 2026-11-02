# Proxy CONFAZ do contAI

Função Vercel mínima para permitir que os workflows do GitHub obtenham páginas públicas do CONFAZ quando o runner não consegue conectar diretamente. Não usa banco, storage, dependências npm, nem dados Supabase.

## O que aceita

- Apenas `GET` autenticado pelo header `x-chave`.
- Apenas URLs HTTPS de `www.confaz.fazenda.gov.br`, sem credenciais e sem porta alternativa.
- Apenas conteúdo de até 4 MiB, suficiente para os fluxos CEST e descoberta CONFAZ usados pelo contAI.
- Sem seguir redirecionamentos da fonte e sem repassar headers do chamador à fonte.

A função retorna `401` para chave inválida, `403` para host ou protocolo não permitido, `502` para erro da fonte e `504` se a fonte passar de 50 segundos. Respostas não são armazenadas em cache.

## Deploy na Vercel

1. Na Vercel, selecione **Add New → Project** e importe `lucasvidalsilva/contai` (ou um fork seu, se preferir).
2. Configure **Root Directory** como `infra/confaz-proxy`.
3. Em **Settings → Environment Variables**, adicione `PROXY_CHAVE` com uma chave aleatória forte no ambiente **Production**. Não a coloque no Git.
4. Faça o deploy. O `vercel.json` seleciona a região `gru1` e limita a função a 55 segundos.
5. Copie o domínio de produção exibido pela Vercel e acrescente `/api/buscar`. Esse é o valor de `PROXY_BRASIL_URL`.

Depois, no GitHub do contAI, cadastre em **Settings → Secrets and variables → Actions → Secrets**:

| Secret | Valor |
|---|---|
| `PROXY_BRASIL_URL` | `https://<dominio-de-producao>/api/buscar` |
| `PROXY_BRASIL_CHAVE` | O mesmo valor definido como `PROXY_CHAVE` na Vercel |

A URL de produção precisa aceitar chamadas dos workflows sem login interativo da Vercel; a autenticação da função é feita pelo header secreto `x-chave`.

## Testes locais

Requer Node.js 22; não precisa instalar pacotes:

```sh
npm test
```

Para chamar a função, envie `GET /api/buscar?url=<URL codificada>` com o header `x-chave` igual ao `PROXY_CHAVE` configurado na Vercel.
