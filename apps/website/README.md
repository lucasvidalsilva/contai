# contAI Website

Landing page da etapa 04, construída com Next.js e App Router. A página apresenta o produto sem formulário ou coleta
de dados; o CTA permanece como **Em breve** até a distribuição do aplicativo ser aprovada.

## Desenvolvimento

```powershell
npm ci
npm run dev
```

Execute os comandos dentro de `apps/website/`.

## Verificações

```powershell
npm run check
npm run lint
npm run format:check
npm run build
```

Na Vercel, configure `apps/website` como Root Directory. O framework e a saída do Next.js são detectados
automaticamente; nenhuma variável de ambiente é necessária neste corte.
