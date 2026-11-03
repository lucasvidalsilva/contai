# Etapa 04 — Landing page

## Objetivo e estado

Apresentar o contAI com clareza e personalidade, explicar o valor do produto sem prometer conformidade integral e
preparar uma presença pública na Vercel. A página usa Next.js, não coleta dados e mantém o CTA **Em breve**.

**Estado:** em andamento. A primeira entrega cobre a landing responsiva, conteúdo, metadados e deploy de preview. A
publicação em domínio próprio e a troca do CTA dependem da disponibilidade aprovada do aplicativo.

## Direção visual

- linguagem editorial de alto contraste, com tipografia serifada nos títulos e sans-serif nos dados;
- composição em osso, carvão e azul-cobalto, sem gradientes, vidro, mascotes ou ilustrações genéricas de IA;
- prévia ilustrativa do produto construída com elementos de interface, sem expor XML ou dados reais;
- ritmo de página baseado em narrativa, não em uma sequência de cards comerciais repetidos;
- referências de `ref_design/` usadas somente para direção; os arquivos não entram no bundle nem no Git.

## Critérios do primeiro corte

- [x] aplicação Next.js independente em `apps/website/`;
- [x] conteúdo coerente com pipeline, motor e aplicativo existentes;
- [x] CTA não interativo **Em breve**, sem formulário ou falsa lista de espera;
- [x] layout responsivo com navegação semântica, foco visível e redução de movimento;
- [x] limite de conformidade e papel da revisão profissional explícitos;
- [x] typecheck, lint e build de produção aprovados;
- [ ] inspeção visual em desktop e viewport móvel;
- [ ] preview publicado na Vercel e vinculado ao pull request.

## Vercel

O projeto deve usar `apps/website` como Root Directory. Next.js é detectado automaticamente e não há variáveis de
ambiente neste corte. O preview da branch é a forma de aprovação; produção e domínio próprio permanecem fora desta
entrega até decisão explícita.
