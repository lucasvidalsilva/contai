# Etapa 04 — Landing page

## Objetivo e estado

Apresentar o contAI como produto e como entrega de engenharia: partir da rotina fiscal, mostrar o fluxo completo entre
fonte, pipeline, banco, motor e interface, e separar com precisão o que funciona do que ainda está em desenho.

**Estado:** implementação local em validação. A publicação de preview e qualquer alteração em produção continuam
dependendo de autorização explícita.

## Posicionamento

A página prioriza as evidências que o repositório consegue sustentar:

- problema operacional antes da escolha de tecnologia;
- seis fontes oficiais com execução verde no GitHub Actions;
- 34 payloads brutos preservados e verificados no ambiente de desenvolvimento;
- 12.966 blocos legais em staging privado, sem interpretação jurídica automática;
- motor fiscal offline com sete verificações determinísticas e cobertura temporal declarada;
- aplicativo desktop como próxima etapa e conector de IA apenas como contrato ilustrativo.

O conector não é apresentado como funcional. Nomes de consultas, versões fictícias e afirmações de compatibilidade por
plano foram removidos. A simulação demonstra procedência e a recusa de extrapolar um snapshot NCM para uma data sem
cobertura.

## Direção visual

- azul, ink e canvas alinhados à identidade documentada do projeto;
- Bricolage Grotesque nos títulos e IBM Plex Mono em dados e contratos;
- linguagem visual inspirada na conferência do contador: papel pautado, vistos, círculo de lápis e total sublinhado;
- narrativa responsiva com componentes interativos que servem à explicação do produto;
- animações desativadas ou resolvidas imediatamente com `prefers-reduced-motion`;
- sem imagens de clientes, XML real, testemunhos, métricas inventadas ou logos não oficiais.

## Critérios desta entrega

- [x] aplicação Next.js independente em `apps/website/`;
- [x] CTA para o repositório e leitura clara do que já funciona;
- [x] dados e estados coerentes com `docs/01-pipeline-tributaria.md` e `docs/02-motor-fiscal.md`;
- [x] limites de conformidade, cobertura temporal e revisão profissional explícitos;
- [x] conector rotulado como simulação, sem API ou compatibilidade prometida;
- [x] navegação semântica, foco visível e redução de movimento;
- [x] typecheck, lint, formatação e build de produção aprovados após a revisão;
- [ ] inspeção visual com navegador disponível;
- [ ] preview publicado na Vercel e vinculado ao pull request.

## Vercel

O projeto usa `apps/website` como Root Directory. Next.js é detectado automaticamente e não há variáveis de ambiente
obrigatórias. O preview da branch é a forma de aprovação; produção e domínio próprio permanecem fora desta entrega até
decisão explícita.
