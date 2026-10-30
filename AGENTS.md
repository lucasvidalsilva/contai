# AGENTS.md — contAI

> Instruções operacionais para agentes de desenvolvimento (Codex e equivalentes).
> Escopo atual: **Etapa 01 — Pipeline tributária**. As etapas 02–04 permanecem planejadas, não autorizadas para implementação.

## 1. Missão e fonte de verdade

O **contAI** é uma ferramenta de apoio à conferência fiscal de NF-e em lote, com verificações determinísticas, evidências verificáveis e processamento local de documentos de clientes. Sua base tributária será construída de forma independente, utilizando Python, GitHub Actions e Supabase PostgreSQL.

Antes de agir, leia nesta ordem:
1. `README.md` — visão de produto, princípios e escopo.
2. `AGENTS.md` — regras de execução e autonomia.
3. `docs/01-pipeline-tributaria.md` — plano e critérios da etapa atual (quando existir).

Se houver conflito: **segurança e integridade de dados > decisão explícita do responsável > escopo aprovado da etapa > README > convenções locais**. Não altere a visão do produto silenciosamente; registre o conflito e solicite decisão.

Não alegue que o produto está operacional quando não estiver. Documente o estado real de cada componente.

## 2. Autonomia: execute o trabalho, escale decisões

**Autorizado sem aprovação adicional, dentro do escopo vigente:**
- Inspecionar código, documentação, testes, dependências e fontes públicas.
- Fazer plano curto de execução e dividir trabalho em mudanças pequenas e verificáveis.
- Criar, modificar e reorganizar arquivos do projeto conforme o plano aprovado.
- Implementar extratores, transformações, testes, fixtures, consultas, migrações versionadas e workflows de CI.
- Rodar testes, lint, formatação, type-check e validações locais; corrigir falhas.
- Criar commits locais pequenos, objetivos e coerentes, registrando evidências de teste.
- Refatorar para reduzir duplicação e melhorar robustez, sem expandir o escopo ou introduzir abstrações sem demanda.

**Exige aprovação explícita antes de executar:**
- Escolhas que alterem significativamente a arquitetura, linguagem, banco, provedor, infraestrutura, contrato de dados ou estratégia de implantação.
- Incluir fontes ou conjuntos de dados com termos de uso, acesso, licenciamento ou legitimidade incertos.
- Provisionar recursos pagos, assumir custos recorrentes, contratar serviços ou mudar níveis de plano.
- Implantar ou alterar recursos de produção, permissões, políticas RLS, roles, secrets, acesso público ou exposição de APIs; executar migrações remotas e cargas em ambientes compartilhados/produção.
- Apagar dados, reescrever histórico Git, realizar force push, excluir branches remotas ou executar operações irreversíveis.
- Copiar código substancial de terceiros, mudar licença, distribuir material protegido ou contornar bloqueios de acesso a fontes.
- Avançar para a etapa 02, 03 ou 04, adicionar IA/RAG/MCP ao produto ou ampliar a cobertura tributária além do plano aprovado.
- Fazer push para o remoto, abrir PR ou publicar releases, caso o responsável não tenha autorizado explicitamente essas ações para a sessão.

Ao encontrar uma decisão crítica, **não interrompa tudo**: continue tarefas seguras e independentes. Ao final, apresente opções, impactos, recomendação e a decisão exata necessária. Não interprete silêncio como aprovação.

## 3. Fluxo de trabalho

1. **Entenda** o objetivo, o estado atual do repositório e a documentação da etapa.
2. **Planeje** brevemente: objetivo, arquivos previstos, riscos e verificações. Evite planejamento interminável.
3. **Implemente** o menor incremento que funcione de ponta a ponta, usando dados de teste e interfaces estáveis.
4. **Verifique** comportamento, dados, segurança e regressões. Execute os testes pertinentes; não declare sucesso sem evidências.
5. **Documente** decisões e limitações onde o leitor realmente as procuraria; atualize a documentação existente em vez de multiplicar arquivos.
6. **Registre** em commit pequeno quando o conjunto estiver coerente; descreva mudanças e validações executadas.
7. **Informe** de forma concisa: entregue, testes, pendências, riscos e próxima atividade.

Priorize **entrega vertical** sobre construir antecipadamente toda a infraestrutura. Não crie placeholders ou scaffolding de etapas futuras sem necessidade concreta.

## 4. Escopo e arquitetura

A sequência aprovada é:

| Etapa | Responsabilidade | Situação |
|---|---|---|
| 01 — Pipeline tributária | Capturar fontes oficiais, normalizar, versionar e publicar dados consultáveis | **Atual** |
| 02 — Motor fiscal | Regras determinísticas de conferência de NF-e, com testes e evidências | Planejada |
| 03 — App desktop | Tauri + React + TypeScript, processamento local | Planejada |
| 04 — Landing page | Next.js, apresentação e distribuição | Planejada |

Para a etapa 01, adote como padrão: **Python 3.12+, `uv`, `pytest`, `ruff`, verificações de tipos pertinentes, GitHub Actions e Supabase PostgreSQL**. Essas escolhas são a base vigente; trocas relevantes exigem aprovação. Prefira SQL versionado e explícito a um ORM pesado. Não introduza FastAPI, filas, Spark, Databricks, microserviços ou serviços pagos sem necessidade demonstrada e aprovação.

Separe responsabilidades de **coleta**, **parsing**, **normalização**, **validação de qualidade**, **persistência** e **publicação**. Mantenha funções pequenas e contratos tipados, sem impor Clean Architecture ou camadas artificiais.

## 5. Engenharia de dados tributários

- **Fonte primária:** obtenha dados de portais públicos oficiais sempre que tecnicamente viável; armazene URL, órgão, instante de coleta, método de obtenção e identificador/hash do conteúdo.
- **Dados brutos:** preserve o conteúdo original ou um artefato verificável, de modo que seja possível reprocessar sem uma nova coleta quando autorizado e tecnicamente viável.
- **Temporalidade:** diferencie `captured_at`/observação, publicação, início/fim de vigência e versão interna. Não infira vigência apenas pela data de download.
- **Histórico:** não sobrescreva silenciosamente versões. Alterações precisam ser detectáveis, auditáveis e reproduzíveis.
- **Idempotência:** reexecutar uma carga sem mudança de origem não deve duplicar registros nem gerar novas versões artificiais.
- **Incrementalidade:** use mecanismos de mudança oficiais (sitemap, metadados, ETag, Last-Modified etc.) quando confiáveis; não sobrecarregue portais com recapturas integrais.
- **Qualidade:** valide tipos, codificações, esquema, unicidade, integridade referencial, contagens esperadas, datas e regras específicas por fonte. Quarentene dados inesperados; não publique silenciosamente lotes inválidos.
- **Rastreabilidade:** uma linha publicada deve poder ser vinculada à origem e à versão do processamento.
- **Sem inferência jurídica automatizada:** coletar uma nova lei **não** autoriza gerar ou ativar automaticamente regras fiscais. Mudanças com efeito normativo exigem curadoria e validação humana.
- **Cobertura explícita:** registre fontes não suportadas, falhas conhecidas e limitações; não prometa cobertura estadual, regimes ou benefícios fiscais sem evidência.

A arquitetura Bronze/Silver/Gold é **conceitual**: implemente só as persistências necessárias, com custo e complexidade proporcionais. PostgreSQL é o catálogo estruturado; arquivos grandes de origem não devem ser armazenados indiscriminadamente em colunas de tabelas públicas.

## 6. Segurança e privacidade

- Na etapa 01, trabalhe **somente com legislação e tabelas públicas**. Não armazene XML de clientes, CPFs, credenciais ou dados fiscais privados no Supabase de referência.
- Nunca commite chaves, tokens, `service_role`, senhas, dumps de produção ou `.env` com segredos. Use GitHub Secrets / variáveis seguras; forneça apenas `.env.example` sem valores reais.
- Princípio do menor privilégio: credenciais de escrita ficam restritas a processos confiáveis; clientes recebem somente interfaces de leitura autorizadas.
- **Supabase:** prefira schemas de ingestão não expostos; aplique RLS a tabelas de schemas acessíveis pela Data API; configure `GRANT`s explícitos e confira políticas. Uma chave pública não substitui autorização.
- Evite expor tabelas brutas como API; publique apenas datasets versionados e aprovados.
- Não aceite certificados inseguros, ignore verificações TLS ou contorne CAPTCHA, bloqueios geográficos e limites técnicos/legais. Se alguma fonte exigir acesso a partir do Brasil, documente a restrição e peça aprovação para uma solução legítima, sem improvisar proxy.
- Pin/lock de dependências, varredura de secrets, permissões mínimas em workflows e revisão de mudanças de fornecedores.
- Registre erros sem dados sensíveis. Falhas de captura não devem substituir o último conjunto publicado e validado.

## 7. Testes e critérios de conclusão

Para cada conector/transformação, cubra ao menos:
- Fixture pequena e reprodutível; parsing da fonte esperada.
- Mudança no formato da fonte; falha explícita e segura.
- Fonte indisponível, timeout e tratamento de retry/backoff com limites.
- Reexecução idempotente, deduplicação e detecção de mudanças reais.
- Datas, versões, unicidade e relação entre dados transformados.
- Persistência local ou ambiente de teste isolado; não depender de produção no CI.

Use `pytest` e `ruff`; execute o conjunto aplicável a cada alteração. Testes de integração remota devem ser opt-in, protegidos por credenciais e sem mutações em produção por padrão. CI deve rodar com privilégios mínimos e não depender de secrets para testes unitários.

**Definition of Done:** código implementado, testes pertinentes passando, comportamento observável, documentação atualizada, nenhum segredo exposto, limitações registradas e saída reproduzível. Se algo não foi testado, informe objetivamente.

## 8. Git, branches e commits

- Commits em **português**, com prefixo convencional: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:` ou `ci:`.
- Branches, quando necessárias: `AAAAMMDD-vidal-feat-descricao` ou `AAAAMMDD-vidal-fix-descricao`. Não crie branches para cada microtarefa sem necessidade.
- Não reescreva commits alheios, não faça force push e não altere a branch principal remotamente sem autorização.
- Evite commits enormes e misturar refatoração com mudança funcional sem justificativa.
- Não modifique arquivos fora da tarefa ou reverta mudanças do usuário apenas para facilitar o trabalho.

## 9. Documentação enxuta

- `README.md`: vitrine pública, visão e estado real do produto; texto conciso, compreensível e atraente, sem afirmar funcionalidades planejadas como prontas.
- `AGENTS.md`: regras de colaboração e engenharia; alterar apenas diante de decisão explícita.
- `docs/01-pipeline-tributaria.md`: escopo, fontes, modelo de dados, execução, checkpoints, validação e riscos da etapa 01.
- `docs/02-motor-fiscal.md`, `docs/03-aplicativo.md` e `docs/04-landing-page.md`: serão detalhados quando cada etapa for iniciada. Não inventar contratos prematuros.
- Registre decisões relevantes diretamente no documento da etapa, incluindo alternativas descartadas e justificativa curta. ADRs separados somente quando realmente necessários.

## 10. Uso de referências open source

É permitido **inspecionar e aprender** com repositórios públicos, sempre confrontando documentação e dados com fontes oficiais. Não faça cópia maciça automática de implementações externas.

Se reutilizar código ou partes substanciais licenciadas, cumpra **integralmente** as obrigações da licença e preserve avisos exigidos, ainda que não haja menção ao repositório no README principal. Nunca remova atribuições legalmente obrigatórias por razões de apresentação. Registre dependências e licenças de terceiros onde apropriado.

A cobertura funcional de um projeto de referência é uma **hipótese a ser validada**, não autorização para coletar indiscriminadamente conteúdos ou replicar fragilidades.

## 11. Comunicação com o responsável

Comunique-se em **português brasileiro**, com objetividade. Não faça elogios genéricos, não apresente planos extensos quando bastar executar e não pergunte permissão para passos já autorizados.

Ao concluir uma atividade, use um resumo curto:
- **Entregue:** mudanças relevantes.
- **Verificado:** testes e resultados reais.
- **Atenções:** riscos e limitações.
- **Decisão necessária:** apenas se houver bloqueio ou alteração crítica.

Se uma atividade falhar, explique o erro e proponha a correção. Não esconda problemas, não simule sucesso e não altere metas para fazer os testes passarem.

**Regra final:** construir o contAI com disciplina de produto e engenharia, não com complexidade decorativa. Primeiro uma pipeline confiável; depois as demais etapas, mediante aprovação.
