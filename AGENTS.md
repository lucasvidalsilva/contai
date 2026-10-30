# AGENTS.md — contAI

Instruções de engenharia para agentes que atuam neste repositório. Este arquivo define **como trabalhar**; não substitui a especificação de cada etapa.

## 1. Contexto e prioridades

- **Produto:** `README.md` — visão, público, limites e arquitetura proposta.
- **Trabalho ativo:** `docs/01-pipeline-tributaria.md` — requisitos e critérios de aceite da etapa 01.
- **Etapas seguintes:** motor fiscal, aplicativo Tauri e landing page. Não implementá-las sem autorização explícita.
- **Ordem de precedência:** instrução explícita do usuário > restrições de segurança e integridade > este arquivo > documentação da etapa > convenções inferidas do código. Quando houver conflito material, explicitar e pedir decisão; não reinterpretar silenciosamente.

Objetivo imediato: entregar uma **pipeline tributária em Python** que capture fontes oficiais, normalize, valide, versione e publique dados consultáveis no **Supabase PostgreSQL**. Priorize uma primeira fonte funcionando de ponta a ponta antes de expandir a cobertura.

## 2. Procedimento em cada tarefa

1. Inspecionar o estado do Git, os arquivos relevantes, os testes existentes e o documento da etapa. Não presumir que arquivos planejados já existem.
2. Identificar a menor entrega verificável; para trabalhos maiores, registrar um plano curto com dependências e riscos.
3. Implementar seguindo as convenções presentes. Criar abstrações somente quando houver necessidade demonstrável.
4. Executar testes, lint e verificações pertinentes; corrigir falhas causadas pela mudança.
5. Atualizar documentação e exemplos que ficaram desatualizados.
6. Fazer commit local de uma unidade coesa, se o ambiente permitir. Informar o que mudou, o que foi executado e o que ficou pendente.

Não interromper trabalho seguro por decisões independentes ainda pendentes. Não apresentar testes não executados como aprovados, nem substituir uma implementação por placeholders sem avisar.

## 3. Autonomia e limites

**Pode executar sem pedir aprovação**, dentro da etapa autorizada: pesquisar fontes públicas, editar arquivos, criar testes e migrações locais, instalar dependências necessárias e justificadas, rodar ferramentas locais, refatorar código diretamente relacionado e criar commits locais.

**Pedir aprovação antes de:**
- Alterar escolhas estruturais acordadas (Python, PostgreSQL/Supabase, GitHub Actions), interfaces públicas ou escopo da etapa.
- Criar custos, provisionar infraestrutura paga ou introduzir serviços externos persistentes.
- Executar migrações/cargas em banco remoto compartilhado ou produção; alterar RLS, grants, papéis, secrets ou acesso público.
- Executar operações destrutivas/irreversíveis, apagar dados persistidos, fazer `git push --force`, reescrever histórico ou excluir recursos remotos.
- Fazer push, abrir PR, publicar release ou iniciar deploy sem uma autorização de publicação para a sessão.
- Contornar bloqueios de fontes, usar credenciais de terceiros ou incorporar código com obrigações de licença não avaliadas.
- Iniciar etapas 02–04 ou ampliar cobertura tributária fora do plano aprovado.

Não pedir autorização para cada edição, comando ou teste já coberto por esta política. Permissões efetivas do ambiente continuam valendo; este arquivo não substitui controles da ferramenta.

## 4. Mapa do repositório

O repositório está em construção. Respeitar a estrutura existente; criar diretórios apenas ao introduzir código real:

- `packages/tax-data/`: extração, parsing, transformação, qualidade e publicação tributária em Python.
- `packages/fiscal-engine/`: motor fiscal — **etapa futura**.
- `apps/desktop/`: aplicativo Tauri — **etapa futura**.
- `apps/website/`: landing page — **etapa futura**.
- `infra/supabase/`: schema SQL e migrações versionadas.
- `.github/workflows/`: testes e execução agendada de pipelines.
- `docs/`: especificação de cada etapa e decisões essenciais.

Se a estrutura real divergir, preferir o código em uso e atualizar este mapa somente após a mudança aprovada.

## 5. Ferramentas e comandos

**Stack aprovada para a etapa 01:** Python 3.12+, `uv`, `pytest`, `ruff`, SQL versionado, GitHub Actions e Supabase PostgreSQL. A configuração exata das ferramentas será definida no `pyproject.toml` durante o bootstrap.

Após o bootstrap, usar preferencialmente:

```bash
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Estes comandos são **alvo de padronização**, não evidência de que já funcionam. Ao criar o projeto Python, gerar e versionar `uv.lock`, configurar os testes e validar os comandos. Se scripts oficiais forem diferentes, documentar os comandos reais aqui. Nunca executar testes de integração contra produção por padrão.

## 6. Regras de implementação da pipeline

- **Separe responsabilidades:** obtenção da fonte, parsing, normalização, validação, persistência e publicação. Preserve interfaces simples e tipos explícitos; não introduza frameworks ou camadas artificiais.
- **Proveniência:** para cada captura registre órgão, URL, momento da captura, formato, hash SHA-256, identificação do parser e resultado da execução.
- **Tempo:** modele separadamente data de captura, publicação, início/fim de vigência e versão do dataset. Não deduza vigência a partir do download.
- **Imutabilidade e reprocessamento:** preserve originais ou um mecanismo verificável de recuperação; nunca sobrescreva histórico sem rastreabilidade.
- **Idempotência:** reruns com fonte inalterada não criam versões ou registros duplicados. Publicação só ocorre após verificações de qualidade.
- **Incrementalidade:** prefira mecanismos oficiais de detecção de mudanças, com limites de requisições, timeout e retry com backoff; não sobrecarregue fontes públicas.
- **Qualidade:** valide schema, codificação, códigos, datas, unicidade, integridade referencial e volume plausível. Rejeite/quarentene dados inesperados sem invalidar a última publicação aprovada.
- **Regra fiscal não é dado bruto:** atualização automática de lei ou tabela não implica ativação automática de interpretação ou regra fiscal. Mudanças normativas exigem curadoria e testes específicos.
- **Bronze/Silver/Gold:** use como separação lógica; não crie três infraestruturas se uma persistência simples e auditável resolver.

## 7. Segurança, acesso e terceiros

- A etapa 01 manipula **somente dados legais e tributários públicos**. Não inserir XMLs de clientes, CPFs, dados fiscais privados ou credenciais na base de referência.
- Nunca commitar `.env`, tokens, chaves administrativas, dumps confidenciais ou segredos em fixtures/logs. Manter `.env.example` sem credenciais reais.
- Manter ingestão e escrita em schemas/credenciais não expostos. Publicar leitura apenas por interfaces intencionalmente autorizadas; aplicar RLS e privilégios mínimos quando houver acesso pela Data API do Supabase.
- Não embutir `service_role` ou chaves secretas em aplicações cliente. Toda alteração de política remota exige aprovação e verificação.
- Fixar dependências com lockfile; não desabilitar TLS, validação de certificados ou checagens de segurança para fazer integrações funcionarem.
- Estudar repositórios open source é permitido. Ao reutilizar código substancial, cumprir licenças e preservar avisos exigidos; preferir implementação própria a cópia sem análise.

## 8. Testes e definição de pronto

Para cada fonte implementada, cobrir no mínimo: parsing de fixtures reais/sanitizadas; entrada malformada; fonte indisponível; mudança de schema; deduplicação/idempotência; datas/vigências; detecção de alteração; persistência isolada e regressão. Testes unitários não dependem de rede nem de Supabase remoto.

Uma entrega só está pronta quando:
- O comportamento previsto no documento da etapa funciona e é demonstrável.
- Os testes e verificações pertinentes foram executados e passaram, ou as falhas remanescentes estão explicitadas.
- Uma segunda execução com os mesmos dados produz resultado consistente.
- Schema, fontes, configuração e modo de execução estão documentados.
- Não houve exposição de credenciais, ampliação indevida de permissões ou perda silenciosa de dados.

## 9. Git e documentação

- Commits em português com prefixos `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `ci:` ou `chore:`.
- Branches, quando necessárias: `AAAAMMDD-vidal-feat-descricao` ou `AAAAMMDD-vidal-fix-descricao`.
- Não misturar alterações não relacionadas nem reverter trabalho preexistente do usuário.
- Atualizar `README.md` quando o estado público do produto mudar. Detalhes de fontes, modelagem, decisões e critérios pertencem a `docs/01-pipeline-tributaria.md`.
- Não criar ADRs, políticas ou relatórios separados por padrão; registre decisões curtas no documento relevante. Acrescentar novos documentos somente quando resolverem uma necessidade concreta.

## 10. Relato de execução

Ao concluir, apresentar apenas informações operacionais: **alterações realizadas**, **comandos/testes e resultados**, **limitações** e **decisões pendentes**. Se algo exigir aprovação, descrever a ação exata, o motivo e a alternativa segura. Continuar o trabalho autorizado sempre que possível.
