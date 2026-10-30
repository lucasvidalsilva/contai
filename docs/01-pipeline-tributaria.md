# Etapa 01 — Pipeline tributária

> **contAI · Especificação de execução v2.0 · 30/10/2026**  
> **Status:** planejamento aprovado quanto à direção; implementação e acesso remoto ainda não iniciados.  
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
- **Captura (`capture.yml`):** `workflow_dispatch` e agendamento, inicialmente restrito a fontes implantadas. Concurrency por fonte; proteção de secrets; execução com tempo máximo; logs sanitizados; resumo do lote. Publicação externa só após configuração aprovada.

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

---

**Princípio:** dados fiscais úteis precisam ser **atuais, verificáveis, historicamente explicáveis e seguros**. Captura automática sem procedência e testes não é uma base confiável.
