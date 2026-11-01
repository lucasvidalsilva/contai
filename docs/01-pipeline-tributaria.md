# Etapa 01 — Pipeline tributária

> **contAI · Especificação de execução v2.0 · 30/10/2026**  
> **Status:** NCM capturada, validada, versionada e publicada no Supabase dev; TIPI e IBS/CBS têm captura, staging privado, publicação transacional e testes PGlite implementados localmente. IBS/CBS usa captura manual da página pública. CEST tem captura bruta e extração local de linhas candidatas, com situação jurídica não resolvida. Migrations TIPI/IBS-CBS ainda não foram aplicadas no Supabase remoto nem publicadas lá. Fontes normativas seguem pendentes ou bloqueadas.
> **Escopo autorizado:** exclusivamente a plataforma de dados tributários. Motor fiscal, desktop, landing page, IA e MCP permanecem fora desta etapa.

## 1. Objetivo

Construir uma base tributária brasileira **rastreável, versionada, reproduzível e consultável** a partir de fontes oficiais, com pipelines em **Python**, automação em **GitHub Actions** e persistência em **Supabase PostgreSQL**.

A plataforma de dados deve permitir responder:

- Qual era o conteúdo de uma tabela ou norma em determinada versão e, quando houver informação suficiente, **na data de vigência da operação**?
- De qual órgão e URL veio cada informação, quando foi capturada e qual artefato/hash a sustenta?
- O que mudou desde a última captura válida?
- O que foi publicado com sucesso, o que falhou e o que aguarda revisão?
- Como um cliente autorizado consulta somente datasets aprovados, sem acesso a credenciais de escrita?

**Não é objetivo desta etapa decidir automaticamente se uma operação fiscal está correta.** Capturar e estruturar legislação não equivale a interpretá-la juridicamente nem autoriza ativação automática de regras fiscais.

## 2. Fontes de contexto, referência open source e limites

Fontes de verdade do trabalho, nesta ordem: `README.md`, `AGENTS.md`, este documento e evidências obtidas nas **fontes governamentais oficiais**. A análise de implementações open source serve para descobrir fontes, comportamentos e casos de borda; as URLs, os formatos e os números citados por terceiros devem ser confirmados na origem. Não copiar código substancial de terceiros sem cumprir sua licença; atribuições obrigatórias podem constar de arquivo próprio, não necessariamente do README público.

### Referência obrigatória de investigação técnica

**Repositório a estudar:** [Matheuscfs/legislacao-tributaria](https://github.com/Matheuscfs/legislacao-tributaria) (licença MIT no momento do levantamento; confirmar no commit efetivamente analisado).

O objetivo é **entender o funcionamento e a cobertura**, não clonar a arquitetura nem transcrever TypeScript para Python. Antes de escrever extratores, inspecionar e registrar no inventário:

| Arquivo/diretório de referência | Pergunta que deve responder |
|---|---|
| [`README.md`](https://github.com/Matheuscfs/legislacao-tributaria/blob/main/README.md) | Quais dados e restrições são declarados? Quais números precisam de validação? |
| [`scripts/capturar.ts`](https://github.com/Matheuscfs/legislacao-tributaria/blob/main/scripts/capturar.ts) | Como fontes e capturas são orquestradas? Como erros e alterações são tratados? |
| [`src/fonte.ts`](https://github.com/Matheuscfs/legislacao-tributaria/blob/main/src/fonte.ts) | Quais problemas de HTTP, charset e integridade aparecem? |
| [`src/ncm.ts`](https://github.com/Matheuscfs/legislacao-tributaria/blob/main/src/ncm.ts) | Qual schema de NCM e qual vigência podem ser recuperados? |
| [`src/ibs-cbs.ts`](https://github.com/Matheuscfs/legislacao-tributaria/blob/main/src/ibs-cbs.ts) | Como CST, cClassTrib e relações NCM/NBS são representados? |
| [`src/cest.ts`](https://github.com/Matheuscfs/legislacao-tributaria/blob/main/src/cest.ts) e [`src/tipi.ts`](https://github.com/Matheuscfs/legislacao-tributaria/blob/main/src/tipi.ts) | Como tratar segmentos, exceções, alíquotas e mudanças? |
| [`src/planalto.ts`](https://github.com/Matheuscfs/legislacao-tributaria/blob/main/src/planalto.ts) e [`src/confaz.ts`](https://github.com/Matheuscfs/legislacao-tributaria/blob/main/src/confaz.ts) | Como preservar redações anteriores, remissões e alterações? |
| [`src/descoberta.ts`](https://github.com/Matheuscfs/legislacao-tributaria/blob/main/src/descoberta.ts) | Como detectar candidatos a novas normas sem publicá-las automaticamente? |
| [`.github/workflows/capturar.yml`](https://github.com/Matheuscfs/legislacao-tributaria/blob/main/.github/workflows/capturar.yml) | Que periodicidade, permissões e dependências externas a automação utiliza? |
| [`LICENSE`](https://github.com/Matheuscfs/legislacao-tributaria/blob/main/LICENSE) | Quais obrigações de licença se aplicam a eventual reutilização? |

Registrar o **SHA do commit de referência**, data da consulta e arquivo estudado. Links acima apontam para `main` e podem mudar: para reproduzibilidade, fixar o SHA no inventário, sem congelar para sempre o monitoramento de fontes oficiais.

**Entregável de pesquisa:** matriz curta `fonte oficial → tratamento na referência → solução Python proposta → evidência → risco → decisão`. Classificar cada insight como `confirmado na origem`, `observado apenas na referência` ou `hipótese`. Não transformar um dado citado no README terceiro em fato sobre a fonte oficial sem verificação.

**Licenciamento:** legislação e tabelas oficiais podem ser estudadas diretamente nas fontes. Se o código, testes, arquivos criativos ou trechos substanciais forem copiados/adaptados da referência, preservar avisos e atribuição exigidos pela licença MIT; não ocultar atribuição obrigatória para atender à preferência de não mencionar a referência no README de marketing. Se a implementação for independente, deixar isso claro no inventário. Não copiar um corpus transformado do outro projeto para simular uma captura oficial própria.

Cobertura desejada, baseada no inventário inicial da referência técnica:

| Domínio | Fontes oficiais a investigar | Estruturas de interesse | Prioridade de implementação |
|---|---|---|---|
| **NCM** | Portal Único Siscomex | Código, descrição, hierarquia, ato, início/fim de vigência | **P0: primeiro fluxo vertical** |
| **IBS/CBS** | SVRS / Conformidade Fácil e documentação fiscal oficial | CST, cClassTrib, condições, percentuais, vínculos NCM/NBS, vigências | P1 |
| **CEST** | CONFAZ, Convênio ICMS 142/2018 e alterações | Código, segmento, descrição, vínculos NCM, atos | P1 |
| **TIPI** | Receita Federal / publicação oficial da TIPI | NCM, EX, descrição, alíquota, exceção, vigência | P1 |
| **Leis federais selecionadas** | Planalto / publicação oficial | Ato, artigo/dispositivo, texto, remissões, versões, vigência verificável | P2 |
| **CONFAZ** | Site oficial: convênios, protocolos, ajustes SINIEF | Tipo/número/ano, ementa, redações, vínculos, efeitos | P2 |
| **Descoberta de novas normas** | Índices oficiais do Planalto e fontes publicáveis | Novos atos candidatos e alterações detectadas | P2 |

**P0/P1/P2 são ordem de entrega, não permissão para ampliar o escopo.** A etapa 01 almeja cobertura dessas famílias, mas cada fonte só será considerada suportada depois de ser verificada, testada e publicada. Não afirmar cobertura completa do Brasil ou de todos os benefícios de ICMS. Fontes estaduais, Sijut, CGSN, NBS completa e demais amplificações são backlog sujeito a decisão futura.

### Inventário inicial a confirmar no código/fonte oficial

O projeto de referência possui extratores de NCM, TIPI, CEST, IBS/CBS, Planalto e CONFAZ; identifica mudanças no CONFAZ via sitemap; preserva redação antiga em normas compiladas; e registra novas leis complementares candidatas à curadoria. São **comportamentos a estudar**, não código a transportar nem garantia de cobertura atual. Investigar particularmente: `charset` divergente em portais antigos, tabelas HTML irregulares, datas de vigência incompletas, anexos, códigos com zeros à esquerda e relações NCM–CEST–cClassTrib que dependem de condições legais.

Registrar no inventário, para cada fonte: órgão responsável; página/documentação oficial; URL de dados; tipo de acesso; formato; periodicidade; política de atualização; limite de requisições; restrição de acesso; licença/condições; campos; chave natural; vigência; tamanho estimado; e testes de disponibilidade. **Não presumir endpoint estável sem verificar.**

## 3. Decisões técnicas

| Área | Decisão |
|---|---|
| Runtime | Python 3.12 ou superior, versão concreta fixada no projeto |
| Gerenciador | `uv`, com lockfile versionado |
| Coleta | Cliente HTTP Python com timeout, limites, backoff e identificação do cliente; parsing por formato |
| Transformação | Python tipado e SQL explícito, sem Spark nem ORM pesado |
| Dados tabulares | PostgreSQL no Supabase; preservar códigos fiscais como `TEXT` |
| Originais | Arquivo imutável de captura com checksum e metadados; escolher armazenamento viável antes da primeira carga completa |
| Versionamento | Conteúdo por hash, versões de dataset e vigência fiscal separadas |
| Automatização | GitHub Actions: CI separado da captura agendada e execução manual |
| Qualidade | `pytest`, `ruff`, verificação de tipos; testes com fixtures offline |
| Migrações | SQL versionado e Supabase CLI; implantação remota mediante aprovação |
| Interface externa | Nenhuma API própria na primeira entrega; publicação somente de visões/datasets aprovados |

**Decisão pendente de aprovação:** armazenamento de originais grandes. Padrão sugerido: Supabase Storage **privado** para blobs brutos (ou alternativa de objetos compatível) e PostgreSQL para metadados, dados normalizados e referências. Não colocar milhares de documentos longos ou binários em tabelas expostas; verificar cotas, custos e políticas antes de provisionar.


### Política de decisão e autonomia durante a etapa

O Codex pode, sem interrupção: pesquisar repositórios públicos e fontes oficiais, criar código local, fixtures, migrações **sem aplicá-las remotamente**, executar testes offline, corrigir falhas, atualizar documentação e efetuar commits locais de alterações próprias. **Não** deve criar projetos cloud, executar migrações ou cargas remotas, alterar políticas de acesso/segredos, habilitar agenda, criar recursos pagos ou fazer push/deploy sem autorização. Caso uma dessas ações bloqueie o marco, entregar artefato local testado e uma pergunta objetiva com proposta, impacto e alternativa.

Para cada marco: (1) inspecionar estado real do repositório; (2) definir saída observável; (3) implementar o menor fluxo vertical verificável; (4) rodar testes e checagens; (5) registrar evidências, pendências e decisão de avanço. Não criar arquivos/pacotes vazios nem frameworks de extensibilidade especulativos.

### Matriz de verificação por domínio

Cada conector somente recebe status `suportado` quando houver: URL oficial e termos de acesso confirmados, artefato original retido quando permitido, schema versionado, casos positivos e negativos de teste, controle de carga idempotente, relatório de diferença, política de publicação e consulta reprodutível. Caso contrário: `em investigação`, `parcial` ou `bloqueado`, com motivo.

## 4. Arquitetura lógica

```mermaid
flowchart TD
  A[Fontes oficiais] --> B[Conectores Python]
  B --> C[Captura bruta + SHA-256 + metadados]
  C --> D[Parsers e normalizadores]
  D --> E[Controles de qualidade]
  E -->|aprovado| F[PostgreSQL: tabelas versionadas]
  E -->|reprovado| Q[Quarentena + relatório]
  F --> G[Publicação atômica de dataset]
  G --> H[Leitura governada / exportação versionada]
  I[GitHub Actions] --> B
  I --> E
```

**Bronze / Silver / Gold são responsabilidades, não três bancos obrigatórios.**

- **Bronze:** bytes originais, URL, status HTTP, `etag`/`last_modified` quando existirem, hash SHA-256, instante de coleta, identificador de execução e status. Evitar dados secretos ou privados.
- **Silver:** registros normalizados, histórico por versão, vínculos e datas de vigência com tipos controlados.
- **Gold:** snapshots de referência aprovados para consulta. Publicar apenas depois de testes de qualidade e consistência; consumidores devem enxergar **a última versão válida**, inclusive durante falhas de ingestão.

### Modelo lógico mínimo (para primeira fonte)

Não implementar todas as tabelas do roadmap antes de validar a NCM. Entidades mínimas:

- `source_registry`: identificador, órgão, nome, URL oficial, formato, política de atualização, situação.
- `ingestion_run`: fonte, início/fim, status, estatísticas, erro sanitizado, versão do coletor.
- `source_artifact`: execução, hash, URI privada, cabeçalhos de controle, data de observação e tamanho.
- `dataset_release`: domínio, versão, data de criação, hash do conjunto, status (`candidate`, `published`, `rejected`), artefato(s), contagens e publicação.
- `ncm_entry`: código como texto, descrição, hierarquia, identificador do ato quando fornecido, `valid_from`, `valid_to`, `release_id`, identificador da linha/origem.
- `quality_result`: execução, verificação, severidade, quantidade, estado e detalhes não sensíveis.

Prever chaves, índices e constraints para unicidade de `(release_id, codigo)` quando cabível, integridade referencial e consultas por código e vigência. **Não substituir relações muitos-para-muitos por uma única coluna de classificação.**

A arquitetura completa de normas poderá exigir `legal_act`, `legal_provision`, `provision_version`, `legal_reference` e vínculos de alteração; **modelar quando chegar ao domínio jurídico**, após analisar fontes e sem inferir vigências a partir de marcas visuais de HTML. Não declarar automaticamente que toda redação antiga está juridicamente revogada só porque aparece riscada.

### Temporalidade obrigatória

Tratar separadamente:

1. **Observação:** quando o contAI capturou a fonte (`captured_at`).
2. **Publicação da origem:** quando o órgão publicou o ato, se informado (`source_published_at`).
3. **Vigência/efeitos:** quando norma ou código produz efeito (`valid_from`, `valid_to`), quando verificável.
4. **Publicação contAI:** versão que a plataforma aprovou para consumo (`released_at`).

Campo desconhecido permanece `NULL` e ganha alerta; não preencher por suposição.

## 5. Estratégia de coleta e atualização

1. **Discover:** consultar catálogo/manifesto da fonte; validar URL, disponibilidade e limites.
2. **Fetch:** baixar com tempo limite, retentativas com jitter e limites totais; respeitar `429` e `Retry-After` quando presentes.
3. **Detect change:** comparar ETag/Last-Modified **quando confiáveis** e, principalmente, hash do conteúdo original/normalizado; ausência de alteração não cria versão.
4. **Archive:** persistir original imutável e metadados; falha de arquivamento impede avançar se comprometer reprodutibilidade.
5. **Parse/normalize:** padronizar codificação, tipos, datas, strings e referências, preservando texto original e exceções relevantes.
6. **Validate:** executar checks de esquema, domínios, unicidade, integridade, contagens e consistência de intervalos.
7. **Stage:** gravar candidato isolado, sem modificar a versão publicada.
8. **Publish:** transação que ativa a nova versão somente com verificações aprovadas.
9. **Observe:** emitir resumo de execução, mudanças, qualidade, falhas e providências.

**Carga inicial:** backfill controlado e paginado, com checkpoint por fonte e limites de tráfego. **Carga diária:** apenas o que mudou. Uma mudança de formato, número suspeito de registros ou falha de autenticação bloqueia publicação; não apaga dados previamente válidos.

Para o CONFAZ, verificar a disponibilidade e semântica de `lastmod` do sitemap. O projeto estudado relata restrição geográfica de acesso; **não implementar proxy ou contornar controles automaticamente**. Caso a captura do runner GitHub falhe por região, registrar evidência e solicitar decisão entre execução autorizada em infraestrutura brasileira, acesso oficial alternativo ou adiamento do conector.

## 6. Segurança e governança no Supabase

- Manter **ingestão, artefatos e logs em schemas/armazenamento privados**; não expor todo `public` como catálogo bruto.
- Credenciais privilegiadas de escrita somente em runners/servidores confiáveis; nunca em frontend, cliente desktop, README, artefatos de CI ou `.env` commitado.
- Consumidores de leitura só enxergam datasets explicitamente publicados. Definir e testar `GRANT`, RLS quando o schema estiver exposto e políticas por função/escopo; **autenticação não equivale a autorização**.
- Preferir visões de leitura com direitos do invocador quando compatíveis, ou API intermediária se a governança exigir. Não assumir que views respeitam RLS automaticamente.
- Separar ambiente de desenvolvimento/teste do banco compartilhado de produção. Testes de CI não alteram produção.
- Configurar segredos no ambiente adequado após aprovação. Não provisionar planos pagos, recursos remotos, políticas, chaves ou migrações de produção sem autorização explícita.
- Validar superfície de exposição e limites de exportação; proteger scripts da ingestão contra injeção SQL, URLs controladas por terceiros e alterações de dependências.
- Na etapa 01, **não coletar nem armazenar NF-e de clientes**; somente dados tributários públicos.

## 7. GitHub Actions

Manter workflows separados:

- **CI (`ci.yml`):** `uv sync --frozen`, `ruff check`, formatação, tipagem, `pytest` e verificação de migrações/fixtures sem acesso a serviços externos. Permissão `contents: read`.
- **Captura (`capture.yml`, `capture-tipi.yml`, `capture-ibs-cbs.yml`):** NCM com `workflow_dispatch` e agenda diária após a atualização oficial; TIPI e IBS/CBS com execução manual. IBS/CBS faz apenas um GET por execução, sem agenda ou retry. Concurrency por fonte; sem secrets; execução com tempo máximo; logs sanitizados; resumo do lote; artefatos Actions retidos por 14 dias. Publicação externa só após configuração aprovada.

Evitar workflow que faz `git commit` de todo o corpus a cada execução; o histórico principal ficará no armazenamento de dados e no catálogo de versões. Manter no Git **código, migrações, fixtures pequenas, contratos e documentação**, não volumes brutos massivos.

## 8. Organização sugerida dos arquivos da etapa

```text
contai/
├── README.md
├── AGENTS.md
├── docs/
│   └── 01-pipeline-tributaria.md
├── packages/
│   └── tax-data/
│       ├── pyproject.toml
│       ├── uv.lock
│       ├── src/contai_tax_data/
│       │   ├── sources/
│       │   ├── extract/
│       │   ├── transform/
│       │   ├── quality/
│       │   ├── storage/
│       │   └── cli.py
│       └── tests/
│           ├── fixtures/
│           ├── unit/
│           └── integration/
├── infra/
│   └── supabase/
│       └── migrations/
└── .github/
    └── workflows/
        ├── ci.yml
        └── capture.yml
```

A árvore é orientação, não ordem para criar arquivos vazios. Ajustar ao comportamento real do código. Não criar `apps/desktop`, `apps/website`, FastAPI ou pacotes futuros nesta etapa.

## 9. Plano incremental de execução

### Marco A — inventário e especificação do primeiro contrato

- Ler os extratores e a documentação da referência técnica, **sem copiar código**.
- Acessar as fontes oficiais e confirmar URLs, formatos, campos, políticas e vigência.
- Montar matriz de cobertura com evidências e indicar restrições técnicas/legais.
- Escolher a **NCM** como primeiro dataset; fixar schema, chave natural, checks de qualidade e contrato de consulta.
- Registrar decisões pendentes e riscos neste documento, sem criar ADRs separados.

**Aceite:** inventário verificável de NCM e demais famílias prioritárias, SHA da referência investigada, matriz comparativa, primeira especificação de campos e fonte oficial reproduzível. O inventário deve registrar problemas de acesso e casos de teste antes da implementação.

### Marco B — fluxo vertical NCM, local e testado

- Inicializar `uv` e estrutura mínima de pacote Python.
- Implementar downloader e decodificação, normalizador e verificador NCM.
- Salvar artefato bruto e manifesto local; produzir registros normalizados.
- Validar campos obrigatórios, códigos, datas, unicidade, contagens e mudança de fonte.
- Criar fixtures sem acesso externo e testes de timeout, mudança real, reexecução e regressão.

**Aceite:** uma execução local íntegra gera snapshot NCM reproduzível; segunda execução idêntica não gera nova versão.

### Marco C — PostgreSQL e publicação governada

- Escrever migrações SQL versionadas para as entidades mínimas.
- Aplicar e testar em **ambiente isolado**, mediante aprovação quando remoto.
- Implementar staging e publicação atômica; índices e consultas por código e vigência.
- Validar privilégios de leitura/escrita, RLS se aplicável, e impossibilidade de leitura do bruto por cliente comum.
- Reexecutar o mesmo lote e testar falha no meio da carga sem quebrar a versão publicada.

**Aceite:** carga idempotente e histórico verificável em PostgreSQL de teste; segurança testada; consulta funcional e versionada.

### Marco D — CI e atualização controlada

- Configurar CI offline e captura manual, observabilidade e relatórios.
- Habilitar agenda apenas após testes suficientes e autorização para acesso remoto.
- Simular mudança de tabela e falha de captura; confirmar a permanência da última release válida.

**Aceite:** workflows confiáveis com testes, status, identificação de falhas e sem vazamento de segredos.

### Marco E — expansão por domínio

Seguir a ordem **IBS/CBS → CEST → TIPI → leis federais → CONFAZ/descoberta**. Para cada domínio repetir inventário, extração, parsing, modelo, qualidade, versionamento, consulta, testes e publicação. Prioridades podem ser revistas com justificativa, mas **não publicar um conector não validado**. Para normas, priorizar fidelidade de texto, estrutura de dispositivos e remissões antes de pesquisa semântica.

**Aceite:** matriz de cobertura atualizada, testes por fonte, snapshots aprovados e limitações explicitadas.

## 10. Critérios globais de qualidade (Definition of Done)

A etapa 01 só pode ser declarada concluída quando:

- [ ] Fontes incluídas no escopo possuem procedência oficial verificável e registro de limitações.
- [ ] Inventário técnico compara explicitamente o projeto de referência com as fontes oficiais, incluindo SHA de referência e decisão implementar/adaptar/descartar por comportamento.
- [ ] Cada domínio declarado como suportado tem extrator, parser, normalização e testes.
- [ ] Existe recuperação/reprocessamento de versão a partir do artefato original (quando disponível e autorizado).
- [ ] Cargas são idempotentes, detectam mudanças e preservam histórico.
- [ ] Vigência jurídica e data de captura não são confundidas.
- [ ] Dados suspeitos ficam em quarentena; falhas não substituem releases válidas.
- [ ] Catálogo e SQL de consultas principais têm testes e índices pertinentes.
- [ ] Permissões de leitura e escrita são demonstradas com teste de acesso negativo.
- [ ] CI executa testes offline sem secrets de produção.
- [ ] Workflow de captura tem execução/monitoramento confiáveis para as fontes ativadas.
- [ ] Há documentação para rodar carga inicial, incremental, testes e recuperação de falhas.
- [ ] README reflete as funcionalidades efetivamente concluídas, sem promessas indevidas.

**Regra de relato:** uma etapa parcial deve ser descrita como parcial, com os domínios efetivamente suportados. O marco D com NCM não implica que toda a etapa 01 foi concluída.

## 11. Riscos e decisões que precisam de aprovação

| Questão | Recomendação | Gatilho para aprovação |
|---|---|---|
| Supabase | Começar por ambiente de desenvolvimento isolado | Criar projeto, executar migrações/cargas remotas, mudar grants/RLS |
| Armazenamento de originais | Objeto privado + hash referenciado no catálogo | Escolha de provedor, cotas ou custos |
| CONFAZ fora do Brasil | Testar acesso legítimo; documentar falhas | Runner brasileiro, proxy ou serviço externo |
| Cópia de terceiro | Implementação própria e testes de comportamento | Qualquer reutilização substancial de código sujeito a licença |
| Regras legais | Publicar dados, não conclusões jurídicas automáticas | Ativação de regras normativas para o motor fiscal |
| Exposição da base | Só datasets aprovados; acesso por menor privilégio | Abertura de endpoint público, tokens de usuário ou mudanças de RLS |

Não pedir confirmação para cada função, teste, diretório ou commit local. **Perguntar somente pelo ponto crítico e continuar o que for seguro em paralelo.**

## 12. Resultado do Marco A e preparação local do Marco B

Levantamento realizado em **30/10/2026**. URLs e contagens abaixo são evidências datadas, não promessa de estabilidade. A classificação `confirmado na origem` significa que a página, documentação ou artefato oficial foi consultado; `observado apenas na referência` não é tratado como contrato oficial; `hipótese` exige nova verificação antes de implementar.

### 12.1 Referência técnica fixada

- Repositório: [`Matheuscfs/legislacao-tributaria`](https://github.com/Matheuscfs/legislacao-tributaria).
- Commit estudado: [`94a27084e158ef4c62a317822b3d2d2b517858ad`](https://github.com/Matheuscfs/legislacao-tributaria/tree/94a27084e158ef4c62a317822b3d2d2b517858ad), de `2026-10-30T15:34:28Z`.
- Licença nesse commit: MIT, copyright 2026 Matheus Fachim.
- Arquivos lidos: `README.md`, `LICENSE`, `scripts/capturar.ts`, `src/fonte.ts`, `src/ncm.ts`, `src/ibs-cbs.ts`, `src/cest.ts`, `src/tipi.ts`, `src/planalto.ts`, `src/confaz.ts`, `src/descoberta.ts`, `.github/workflows/capturar.yml` e os quatro arquivos de testes.
- Uso no contAI: estudo de comportamento e descoberta de casos de borda. A implementação Python foi escrita de forma independente; nenhum código, teste ou corpus transformado da referência foi copiado.

### 12.2 Matriz comparativa

| Fonte oficial | Tratamento observado na referência | Solução Python do contAI | Evidência e classificação | Risco | Decisão |
|---|---|---|---|---|---|
| NCM — Portal Único Siscomex | Baixa o JSON vigente, remove do resultado a data diária, converte `31/12/9999` em fim aberto, ordena e compara CSV. | Contrato JSON estrito, bruto imutável por SHA-256, normalização tipada, hierarquia pelo ancestral existente, release por hash semântico e JSONL local. | Endpoint, manual, campos e limitação ao vigente: **confirmados na origem**. Estratégia da referência: **observada apenas na referência**. | Cabeçalho `Vigente em` muda sem mudança tributária; download não traz histórico passado/futuro. | **Publicado no Supabase dev**; publicação automatizada continua desativada. |
| IBS/CBS — SVRS/Conformidade Fácil | Página pública oferece CSV/Excel/JSON; HTML inclui `dadosOriginais` com CST, cClassTrib e vínculos de anexos NCM/NBS. | Contrato independente `ibs-cbs-v1`, uma requisição manual da página pública, parser estrito, normalização, hash semântico, diff, quarentena, staging e publicação transacional. Sem vigência inferida. | Página e JSON incorporado: **confirmados por captura oficial em 31/10/2026**. API oficial separada exige TLS 1.2 + certificado ICP-Brasil; não utilizada. | Notas e efeitos legais não viram regra fiscal; vigências permanecem nos campos oficiais da origem. | **Fluxo implementado e testado em PGlite**; migration não aplicada no Supabase remoto nem release publicada lá. |
| CEST — CONFAZ, Convênio ICMS 142/18 | Captura HTML imutável; extrai candidatos, contexto literal e referência de segmento definida pelo prefixo oficial do CEST. | `confaz-cest-raw-v1` + `cest-candidate-v5`; sem deduplicação, estágio ou publicação. | Associação do segmento segue a definição expressa no convênio e a tabela do Anexo I; candidatos continuam sem vigência validada. | `legal_status=unresolved`; contexto/anexo, tags e associação de segmento não resolvem revogação, atos ou aplicabilidade. | **Captura, extração e associação estrutural executadas localmente**; normalização jurídica segue pendente. |
| TIPI — Receita Federal | Lê XLSX, filtra linhas de produto e usa `(NCM, EX)`; toma o último ato da capa como atualização. | Parser independente XLSX `tipi-v1`, staging privado, publicação transacional versionada e consulta `tipi_current`; nenhuma vigência inferida. | Página, XLSX, cabeçalhos e amostra de 31/10/2026: **confirmados na origem**. Heurística do último ato: **observada apenas na referência**. | Notas de seção/capítulo e efeitos dos atos não são estruturados por linha; uma alíquota está vazia no snapshot atual e é preservada como nula. | **Implementação local concluída e testada em PGlite**; migração TIPI ainda não aplicada no projeto Supabase remoto. |
| Leis federais — Planalto | Captura bruta manual da LC 214/2025 compilada com hash e observações HTTP imutáveis; sem extrair dispositivos. | Contrato inicial `planalto-law-raw-v1`; conservar HTML e não inferir revogação, redação histórica ou vigência. | URL individual oficial acessível; endpoint de índice geral continua instável/bloqueado. | Texto compilado inclui alterações por atos posteriores; não equivale a uma série histórica oficial por dispositivo. | **Captura bruta local implementada**; parsing, vínculo entre versões e publicação seguem pendentes. |
| CONFAZ — convênios, protocolos e ajustes | Descobre páginas por sitemap/`lastmod`, converte HTML e relata bloqueio geográfico em runners externos. | Validar semântica de `lastmod`, limitar concorrência e volume; não usar proxy sem aprovação. | Sitemap e página do Convênio 142 acessíveis no teste: **confirmados na origem**. Bloqueio fora do Brasil: **observado apenas na referência**. | Restrição geográfica pode impedir GitHub Actions; `lastmod` pode não equivaler a mudança normativa. | **Não implementar neste marco**; manter `em investigação`. |
| Descoberta de novas normas — índices do Planalto | Lê o quadro de leis complementares e classifica ementas candidatas; abre issue para curadoria. | Descoberta apenas cria candidato, nunca publicação automática; ampliar fontes somente após acesso oficial estável. | Quadro oficial existe, mas bloqueou/expirou nos testes automatizados: **confirmado na origem com problema de acesso**. Classificador de ementa: **observado apenas na referência**. | Falsos positivos/negativos e bloqueio anti-automação. | **Bloqueado para automação atual**; não contornar controles. |

### 12.3 Inventário verificável de fontes

| Domínio e situação | Órgão, página e URL de dados | Acesso, formato e atualização | Condições e restrições | Campos, chave e temporalidade | Tamanho e teste de disponibilidade |
|---|---|---|---|---|---|
| **NCM — publicada no dev** | RFB/Ceclam, [página de download](https://www.gov.br/receitafederal/pt-br/assuntos/aduana-e-comercio-exterior/classificacao-fiscal-de-mercadorias/download-ncm-nomenclatura-comum-do-mercosul), [manual do Classif](https://www.gov.br/siscomex/pt-br/arquivos-e-imagens/2021/07/ClassifManualdoUsuariov5.0.pdf), [JSON](https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json). | HTTPS GET público, sem captcha no link direto; redireciona para `?perfil=PUBLICO`; JSON UTF-8. A página de integração informa atualização diária à meia-noite. | Sem limite de requisições ou licença específica do dataset identificados. Usar baixa frequência, cache e termos gerais dos portais; não presumir SLA. | Raiz: `Data_Ultima_Atualizacao_NCM`, `Ato`, `Nomenclaturas`. Linha: código, descrição, início/fim, tipo/número/ano do ato inicial. Chave `(release_id, code)`; `31/12/9999` vira `NULL`. O arquivo cobre somente o vigente; histórico é consulta separada no Classif. | Em `2026-10-30T23:31:50Z`: HTTP 200, `application/json`, 3.149.450 bytes, SHA-256 `dfae9ea93ddaa01512009739341c38a01dd7a1d2c3e2fdf089f46dbe970d2fb5`, 15.157 linhas, 10.516 subitens, 96 capítulos, sem códigos duplicados. |
| **IBS/CBS — captura local manual** | SVRS/ENCAT, [tabela pública](https://dfe-portal.svrs.rs.gov.br/CFF/ClassificacaoTributaria), [serviços](https://dfe-portal.svrs.rs.gov.br/CFF/Serviços), API autenticada `https://cff.svrs.rs.gov.br/api/v1/consultas/classTrib`. | A página oficial responde HTML UTF-8 e oferece CSV/Excel/JSON; captura extrai o JSON incorporado `dadosOriginais`. | Captura pública observada em 31/10/2026: HTTP 200; API separada exige TLS 1.2, autenticação mútua e certificado ICP-Brasil. O fluxo é manual, uma requisição por execução e sem agenda. | 18 CST, 173 cClassTrib e 4.728 vínculos de anexos. Códigos como texto; datas oficiais separadas da captura. | Artefato bruto SHA-256 `5e1825e961461d18124ab3d7dd7f1b084688a53bd6afdc69311dd65378f6ccc9`; release local `e858a554bb21a386c9e65f4330d83ef562b77a3bb8067934158a86451d6d9e59`. |
| **CEST — captura + candidatos locais** | CONFAZ, [Convênio ICMS 142/18 compilado](https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18). | GET único via `capture-cest`; HTML UTF-8 arquivado por SHA-256. `extract-cest-candidates` reprocessa o bruto local e escreve JSONL/manifesto versionados pelo hash do artefato e contrato. | Sem limite/licença específica identificados. Não usar proxy. Candidatos são evidência estrutural, não certificam completude nem vigência jurídica. | Preserva item, CEST, NCM/SH, descrição, contexto literal, classes/tags e fonte. Associa os dois primeiros dígitos à tabela oficial de segmentos; status continua `unresolved`. Duplicatas entre redações/anexos são preservadas. | Captura HTTP 200, 933.142 bytes, SHA-256 `7c2bdc9db1ceb11faaa56b2582e77e5a1bcb66e51cd62b6de0f155a78359c45a`. Extração: 1.569 linhas, 1.044 CEST distintos, 27 contextos literais e 25 pares de segmento código/nome; 1.569 associados e zero sem correspondência nesta amostra. |
| **TIPI — parcial-local** | Receita Federal, [página TIPI](https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/legislacao/tipi-tabela-de-incidencia-do-imposto-sobre-produtos-industrializados), [XLSX](https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/legislacao/documentos-e-arquivos/tipi.xlsx/%40%40download/file). | HTTPS GET público; XLSX com aba `Tabela Completa`, cabeçalhos NCM/EX/descrição/alíquota. Alterações por atos; sem agenda fixa. | Link oficial retornou HTTP 200 em 31/10/2026. Captura manual/CLI e Actions por `workflow_dispatch`; sem secrets ou publicação externa. | Linha: `(NCM, EX)`, descrição e alíquota (`NT`, percentual decimal ou nulo se vazio). Release por hash normalizado + lista de atos da capa; nenhuma vigência inferida por linha. | Snapshot de 31/10/2026: HTTP 200, 673.645 bytes, SHA-256 `d1551fbaafb4039dcb74f97bb5abc1aec69f6760da9bd3f94a90bd40b33a2e9a`, 11.103 linhas classificadas e 582 EX. |
| **LC 214/2025 — captura bruta implementada** | Presidência da República/Planalto, [texto compilado oficial](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm). | CLI e workflow manual fazem um GET por execução; quando acessível, HTML é arquivado por SHA-256 com observações HTTP; sem extração. | Página oficial consultável via navegador em 31/10/2026. Captura bruta não representa histórico integral nem aconselhamento jurídico. | Ato `LC 214/2025`; contrato guarda HTML e metadados, sem entidades de artigos/redações ou datas de vigência. | Execução local do CLI falhou duas vezes com `RemoteDisconnected` (incluindo fora do sandbox); não há artefato/hash local validado ainda. |
| **CONFAZ/descoberta — em investigação** | CONFAZ, [sitemap](https://www.confaz.fazenda.gov.br/sitemap.xml.gz) e páginas de convênios/protocolos/ajustes. | Sitemap GZip + HTML; `lastmod` é candidato a detecção incremental. Atualização por publicação de atos. | Nenhum limite publicado; carga deve ser paginada/limitada. Possível restrição geográfica observada na referência. | URL, seção, ano, ato, ementa, conteúdo e `lastmod`. Chave de descoberta por URL; chave jurídica por tipo/número/ano após validação. Efeitos permanecem textuais até curadoria. | Sitemap: HTTP 200, `application/octet-stream`, 325.836 bytes. No SHA de referência: 11.057 atos — estimativa, não cobertura oficial garantida. |
| **Novas normas — bloqueado para automação** | Planalto, `https://www.planalto.gov.br/ccivil_03/leis/lcp/quadro_lcp.htm`. | Quadro HTML, atualização por nova lei complementar. | Requisição web retornou “Acesso Negado” e a tentativa local expirou após 30 s. Não contornar. | Número, data, URL e ementa; chave `(tipo, numero, ano)`. Marca “tributária” seria apenas triagem para revisão humana. | Sem corpo válido no teste de 30/10/2026; referência continha 238 linhas no snapshot, número apenas indicativo. |

### 12.4 Captura CEST e extração de candidatos (`confaz-cest-raw-v1`, `cest-candidate-v5`)

`capture-cest` faz um único GET à página oficial do Convênio ICMS 142/18. Exige HTTP 2xx, `text/html` e UTF-8; arquiva o corpo sem alteração em `artifacts/sha256/<prefix>/<sha256>.html`. Cada observação é gravada separadamente com URL solicitada/final, horário de captura, status, tamanho e cabeçalhos seguros; `state/cest-latest-capture.json` aponta para a observação mais recente. A captura repetida do mesmo corpo não duplica o artefato nem a observação do mesmo instante.

`extract-cest-candidates <arquivo.html>` reprocessa o bruto já arquivado, reconhece a linha de cabeçalho `ITEM | CEST | NCM/SH | DESCRIÇÃO` e emite JSONL com índice da tabela/linha, rótulo de item, CEST preservado como texto, NCM/SH, descrição, títulos de contexto literal e classes/tags de cada célula. Os títulos provêm de parágrafos marcados como subtítulos no HTML e são preservados em ordem, sem convertê-los em chave jurídica. Também lê a tabela `ITEM | NOME DO SEGMENTO | CÓDIGO DO SEGMENTO` do Anexo I e associa o prefixo de dois dígitos do CEST ao nome que tiver o mesmo código; essa estrutura é explicitamente definida pelo convênio, mas não implica vigência ou aplicabilidade. Prefixos sem correspondência permanecem sem nome sem descartar o candidato; nomes conflitantes para o mesmo código rejeitam a extração para revisão. O extrator exige UTF-8, cabeçalho conhecido, código CEST no formato textual esperado e campos não vazios; a extração é identificada pelo SHA-256 do bruto e pelo parser `cest-candidate-v5`. Cada versão do parser tem diretório próprio para permitir reprocessamento sem sobrescrever resultados anteriores. Reexecuções não duplicam o arquivo nem o manifesto.

`diff-cest-candidates <anterior.jsonl> <atual.jsonl>` compara ocorrências pela combinação exata de item, CEST, NCM/SH, descrição, contexto, classes/tags e estado de revisão; movimentação de linha não conta como alteração. O relatório distingue ocorrências adicionadas/removidas/inalteradas e fixa os hashes de ambos os artefatos e snapshots. É um diff estrutural, não uma conclusão de inclusão, exclusão ou vigência legal.

Cada linha tem `legal_status=unresolved`. A captura observada gerou 1.569 linhas candidatas e 1.044 códigos distintos; repetições não são eliminadas porque podem pertencer a anexos ou redações diferentes. A linha extraída não prova que a regra está ativa nem determina alcance. Este artefato **não é release normalizada** e não pode alimentar consulta fiscal ou publicação até correlacionar anexos, atos modificadores, redações e vigência com evidências oficiais e fixtures revisadas. A automação GitHub Actions continua manual (`workflow_dispatch`), conserva o bruto por 14 dias e não tem credenciais de banco.

### 12.5 Captura bruta da LC 214/2025 (`planalto-law-raw-v1`)

`capture-lc214` consulta a URL oficial individual do Planalto uma vez por execução. Exige resposta HTTP 2xx e `text/html`; preserva os bytes originais, sem decodificar, reformatar ou converter para Markdown. O artefato é endereçado por SHA-256 e cada observação registra autoridade, identificação do ato, horário, URLs, status, tamanho e cabeçalhos seguros. A captura é manual no CLI e em workflow `workflow_dispatch`; não escreve no Supabase. Embora a página responda à consulta do navegador, o CLI foi encerrado pelo servidor com `RemoteDisconnected` em duas tentativas de execução (sandbox e elevada), então a captura real segue sem validação neste ambiente.

O endpoint oferece texto compilado e pode incorporar alterações de leis posteriores. O contrato não trata o HTML como histórico completo, não extrai artigos nem presume vigência a partir do estilo ou de notas. Para avançar ao parsing será necessário modelar atos alteradores, redações por dispositivo e efeitos temporais, validando-os contra publicações oficiais; até lá, somente o original capturado é consultável como evidência documental.

### 12.6 Contrato inicial da NCM (`ncm-v1`)

O contrato de entrada é estrito para detectar mudança silenciosa de schema. O JSON deve ser UTF-8, conter exatamente as três chaves de raiz e, em cada linha, exatamente os sete campos confirmados. Campos novos, ausentes, tipo inesperado, JSON malformado ou `Content-Type` diferente de `application/json` arquivam o bruto em quarentena e não alteram a release corrente.

| Campo normalizado | Tipo | Nulo | Regra |
|---|---|---:|---|
| `code` | texto | não | Preserva pontuação e zeros à esquerda; formatos oficiais de 2, 4, 5, 6, 7 ou 8 dígitos. |
| `code_digits` | texto | não | Somente dígitos, para busca e ordenação; não converter para número. |
| `description` | texto | não | Espaços normalizados; hífens hierárquicos preservados. |
| `level` | enum | não | `chapter`, `position`, `subposition_1`, `subposition_2`, `item` ou `subitem`. |
| `parent_code` | texto | sim | Ancestral mais longo presente no mesmo snapshot; capítulo tem `NULL`. Não inventar níveis omitidos. |
| `valid_from` | data | não | `Data_Inicio` oficial convertida de `DD/MM/AAAA`. |
| `valid_to` | data | sim | `31/12/9999` significa fim aberto e vira `NULL`; demais datas são preservadas. |
| `initial_act_type` | texto | não | Tipo do ato inicial informado na linha. |
| `initial_act_number` | texto | não | Somente dígitos e preservado como texto. |
| `initial_act_year` | texto | não | Quatro dígitos e preservado como texto. |
| `source_row_id` | texto | não | `Codigo:<code>` dentro do artefato oficial. |

Metadados da release: `contract_version`, `source_schema_version`, `source_act`, `source_as_of`, `artifact_sha256`, `snapshot_sha256`, contagens e `release_id`. `captured_at`, `source_as_of`, vigência da linha e futura publicação contAI são tempos distintos. `source_as_of` não participa do `release_id`, pois o portal muda “Vigente em” diariamente sem necessariamente mudar os registros; `source_act` e todo conteúdo normalizado participam.

**Chaves e consulta:** a chave natural persistida será `(release_id, code)`. A consulta local usa o `ncm.jsonl` da release apontada por `state/ncm-current.json`; a futura consulta PostgreSQL receberá `code_digits`, `release_id` opcional e `valid_on` opcional. Até haver backfill histórico oficial, `valid_on` só filtra o conteúdo das releases capturadas e **não** prova cobertura histórica anterior.

**Qualidade antes da release:** schema e UTF-8; formatos de código; unicidade de `code` e `code_digits`; descrição e ato obrigatórios; datas válidas e não invertidas; integridade da hierarquia; 14.000–25.000 entradas; pelo menos 9.000 subitens e 90 capítulos. Mudança fora desses limites fica em quarentena para revisão.

### 12.5 Contrato local TIPI (`tipi-v1`)

Entrada estrita: XLSX oficial da Receita Federal, aba com cabeçalho `NCM`, `EX`, `DESCRIÇÃO` e `ALÍQUOTA (%)`. Linhas de capítulo/subposição sem código NCM de oito dígitos são preservadas no bruto, mas não entram no dataset de itens.

| Campo normalizado | Tipo | Nulo | Regra |
|---|---|---:|---|
| `ncm_code` | texto | não | Código pontuado `NNNN.NN.NN`; zeros à esquerda são preservados. |
| `ex_code` | texto | sim | Código de exceção em texto; remove apenas o prefixo `Ex`, preservando zeros à esquerda. |
| `description` | texto | não | Espaços consecutivos normalizados; texto da célula preservado sem inferir notas ou hierarquia. |
| `ipi_rate` | texto | sim | `NT` preservado; número convertido para decimal canônico; célula vazia permanece `NULL`. Não converte alíquota em regra aplicável. |

A chave do snapshot é `(ncm_code, ex_code)`. O `release_id` considera o hash do JSONL normalizado e o texto da capa com os atos/base legal. `captured_at`, hash do XLSX, ato(s) e conteúdo são metadados distintos. A planilha não informa vigência individual uniforme; o contrato **não atribui vigência** às linhas e não representa histórico anterior.

Qualidade: cabeçalho esperado; XLSX válido; unicidade NCM/EX; descrição obrigatória; entre 8.000 e 14.000 itens; ao menos 500 linhas EX; no máximo 10 alíquotas vazias. No snapshot oficial de `2026-10-31`: 11.103 itens, 582 linhas EX e uma alíquota vazia preservada. O bruto e os snapshots ficam em `var/tax-data/tipi/`; os comandos `stage-tipi` e `publish-tipi` carregam e publicam uma release no PostgreSQL configurado. O staging revalida hashes, contrato, contagens e qualidade antes de gravar; a troca do ponteiro público ocorre na mesma transação da publicação. A migração `20261031120000_add_tipi_dataset.sql` está apenas no repositório: **não foi aplicada remotamente**.

### 12.6 Contrato inicial IBS/CBS (`ibs-cbs-v1`)

O fluxo usa a página pública da SVRS/Conformidade Fácil, não a API que exige certificado. A resposta HTML precisa ser UTF-8 e conter exatamente o bloco JSON `dadosOriginais` no formato observado; a estrutura de CST, cClassTrib e anexos é validada por conjuntos estritos de campos. Campo novo/ausente, tipo inesperado, duplicidade de códigos ou bloco ausente/malformado põe o artefato em quarentena e preserva a release corrente.

| Registro | Chave preservada | Dados normalizados |
|---|---|---|
| CST | `Cst` (texto de 3 dígitos) | Descrição, indicadores e datas oficiais de publicação/início/fim de vigência. |
| cClassTrib | `CodClassTrib` (texto de 6 dígitos) | CST pai, descrição, reduções, indicadores por documento fiscal, tipo de alíquota, texto/URL legal e datas oficiais. |
| vínculo de anexo | `(CodClassTrib, CodIntProdServ)` | `CodNcmNbs` como texto, tipo NCM/NBS, número do anexo/item, permissões, condições, exceções, observações e vigência. O identificador interno da SVRS é mantido como proveniência da linha. |

`CtrDthInc` e a navegação redundante são descartados da camada normalizada; o HTML original permanece arquivado por SHA-256. O `release_id` deriva do snapshot canônico normalizado, separado do hash do HTML e do instante de captura. Não se deduz `source_as_of`; as datas legais permanecem ligadas às respectivas linhas. A validação observada em 31/10/2026 encontrou 18 CST, 173 classificações e 4.728 vínculos. A regra atual de volume aceita 1–40 CST, 100–500 classificações e até 50.000 vínculos; mudança fora disso exige revisão. A migration `20261031130000_add_ibs_cbs_dataset.sql`, o staging privado e a publicação atômica foram testados localmente com PGlite; não foram aplicados no Supabase remoto.

Execução manual, sem retry ou agenda:

```powershell
uv --cache-dir .uv-cache run --project packages/tax-data contai-tax-data capture-ibs-cbs --output var/tax-data --timeout 60
```

### 12.7 Fluxo local implementado e plano curto

Artefatos implementados em `packages/tax-data/`, com banco remoto somente no ambiente de desenvolvimento isolado:

1. **Concluído — bootstrap:** Python 3.12.15 fixado, `uv.lock`, pacote mínimo e CLI `contai-tax-data capture-ncm`.
2. **Concluído — captura:** URL fixa oficial, identificação do cliente, timeout, tentativas totais, backoff exponencial com jitter e respeito a `Retry-After`.
3. **Concluído — bronze/silver local:** bruto imutável por SHA-256, manifesto com cabeçalhos permitidos, normalização `ncm-v1`, quarentena e JSONL reproduzível.
4. **Concluído — idempotência:** artefato idêntico não duplica; mudança apenas no “Vigente em” arquiva novo bruto sem release; mudança semântica cria release e diff.
5. **Concluído — testes offline:** fixture pequena derivada da captura oficial e testes de parsing, schema, malformed, indisponibilidade/timeout, retry, vigência, duplicidade, regressão, quarentena, mudança e reexecução.
6. **Concluído localmente — Marco C:** migração, staging privado, controles de qualidade, publicação transacional, consulta pública versionada, grants/RLS e testes de acesso e rollback.
7. **Concluído — Supabase dev:** migrations e configuração da Data API aplicadas após `dry-run`; NCM validada, staged e publicada; consultas SQL, RLS, grants, acesso HTTP, idempotência e advisors verificados.
8. **Concluído parcialmente — Marco D:** CI offline em pull requests e pushes para `main`; captura NCM manual/diária e TIPI manual, com resumo e artefatos retidos por 14 dias. Capturas não escrevem no banco; publicação continua uma ação explícita.
9. **Concluído localmente — TIPI:** captura oficial XLSX, contrato `tipi-v1`, normalização de NCM/EX/descrição/alíquota, arquivo bruto e releases locais imutáveis, diff, quarentena, migração SQL, staging privado, publicação transacional, consulta pública e testes locais de idempotência, autorização e rollback. A migração não foi aplicada no Supabase remoto.
10. **Concluído localmente — IBS/CBS:** página pública oficial confirmada; extração estrita de CST/cClassTrib/anexos, bruto imutável local, hash semântico, diff, quarentena, migration, staging privado, publicação transacional, consultas correntes e testes PGlite. Captura manual sem retry ou agenda; migration não aplicada no Supabase remoto e API mTLS não utilizada.

Comandos locais padronizados:

```powershell
uv --cache-dir .uv-cache sync --locked --project packages/tax-data
uv --cache-dir .uv-cache run --project packages/tax-data pytest
uv --cache-dir .uv-cache run --project packages/tax-data ruff check packages/tax-data
uv --cache-dir .uv-cache run --project packages/tax-data ruff format --check packages/tax-data
uv --cache-dir .uv-cache run --project packages/tax-data mypy packages/tax-data/src
uv --cache-dir .uv-cache run --project packages/tax-data contai-tax-data capture-ncm --output var/tax-data
uv --cache-dir .uv-cache run --project packages/tax-data contai-tax-data capture-tipi --output var/tax-data
uv --cache-dir .uv-cache run --project packages/tax-data contai-tax-data stage-tipi --output var/tax-data --release-id <release_id>
uv --cache-dir .uv-cache run --project packages/tax-data contai-tax-data publish-tipi <release_id>
uv --cache-dir .uv-cache run --project packages/tax-data contai-tax-data capture-ibs-cbs --output var/tax-data --timeout 60
uv --cache-dir .uv-cache run --project packages/tax-data contai-tax-data stage-ibs-cbs --output var/tax-data --release-id <release_id>
uv --cache-dir .uv-cache run --project packages/tax-data contai-tax-data publish-ibs-cbs <release_id>
npm ci --cache .npm-cache
npm run test:db-schema
npm run test:db-integration
```

Os comandos `stage-tipi`, `publish-tipi`, `stage-ibs-cbs` e `publish-ibs-cbs` exigem conexão PostgreSQL explícita e as migrations correspondentes aplicadas no banco de destino. Migrations e publicações remotas continuam pendentes de aprovação.

O diretório `var/` é local e ignorado pelo Git. O armazenamento definitivo dos originais permanece pendente; workflows guardam artefatos de execução por 14 dias no GitHub Actions. Capturas não acessam Supabase, não alteram a release publicada e não usam secrets.

### 12.8 Implementação do Marco C

A migração em `infra/supabase/migrations/` cria duas fronteiras:

- `tax_ingest`: catálogo da fonte, artefatos, execuções, candidatos, resultados de qualidade e registros NCM. O schema não integra a lista da Data API e só concede escrita à role `tax_ingest_writer`, criada sem login, senha ou herança automática.
- `tax_public`: histórico aprovado, ponteiro da release corrente, registros publicados e a view `ncm_current`. As tabelas têm RLS; `anon` e `authenticated` recebem somente `SELECT`; a view usa `security_invoker=true`.

A configuração expõe explicitamente `tax_public`, mantém `auto_expose_new_tables = false` e não abre `tax_ingest`. As migrations `20261031015129` e `20261031040249` foram aplicadas somente no projeto `contai-dev`: a segunda permite que `postgres` execute `SET ROLE tax_ingest_writer`, com `INHERIT FALSE` e `ADMIN FALSE`. Esse uso da credencial administrativa é restrito ao desenvolvimento; CI e produção deverão receber login dedicado antes de qualquer ativação.

O módulo `contai_tax_data.postgres` reprocessa o JSON bruto, confere hashes, snapshot, identidade semântica e contagens antes do staging. A promoção adquire advisory lock transacional, exige todos os checks aprovados, copia a release para `tax_public`, confere a contagem e troca `dataset_current` na mesma transação. Repetições são idempotentes; uma falha antes da troca do ponteiro preserva integralmente a release anterior.

Os testes offline usam PostgreSQL 17 compilado para WebAssembly por PGlite e o protocolo PostgreSQL real para o `psycopg`. Eles aplicam todas as migrations, exercitam duas cargas iguais, duas publicações iguais, leitura como `anon`, negação do schema privado e uma falha injetada após a cópia pública para comprovar rollback. No Supabase dev, foram verificados PostgreSQL 17.11, TLS, `SET ROLE`, RLS, `security_invoker`, grants, histórico de migrations, ausência de drift, advisors, leitura HTTP 200 de `tax_public` e rejeição HTTP 406 de `tax_ingest`. Auth e Storage não foram exercitados porque não participam deste fluxo.

A captura oficial arquivada em 30/10/2026 foi staged e publicada no Supabase dev: 15.157 registros e 10.516 subitens. Reexecução de staging e publicação são idempotentes; o corpus oficial continua em `var/`, fora do Git.

Uso manual, somente depois de migrar um banco de desenvolvimento e configurar a associação da credencial de ingestão à role sem login:

```powershell
Copy-Item .env.example .env
# Preencher SUPABASE_PROJECT_REF e CONTAI_DATABASE_URL no .env.
uv --cache-dir .uv-cache run --env-file .env --project packages/tax-data contai-tax-data stage-ncm --output var/tax-data
uv --cache-dir .uv-cache run --env-file .env --project packages/tax-data contai-tax-data publish-ncm <release_id>
```

Usar a conexão `Session pooler` para a pipeline em redes IPv4; a CLI força `sslmode=require`. Migrações continuam sob a Supabase CLI vinculada ao projeto e passam primeiro por `db push --dry-run`; a aplicação efetiva exige autorização. Não registrar a URL de conexão em Git, argumentos de linha de comando ou logs. A captura e o staging não publicam automaticamente; `publish-ncm` é uma ação explícita e separada.

---

**Princípio:** dados fiscais úteis precisam ser **atuais, verificáveis, historicamente explicáveis e seguros**. Captura automática sem procedência e testes não é uma base confiável.
