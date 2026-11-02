# Etapa 02 — Motor fiscal

## Objetivo e primeiro marco

Implementar um pacote Python local que receba XMLs **sintéticos** de NF-e modelo 55 e emita alertas determinísticos, rastreáveis e limitados às verificações implementadas. A ausência de alertas não representa conformidade fiscal. O motor não substitui revisão profissional.

O primeiro marco (fiscal-engine-v1) implementa um subconjunto verificável: parsing seguro e limitado de XML NF-e 4.00, soma de det/prod/vProd contra total/ICMSTot/vProd, formato de NCM com oito dígitos e consulta opcional a um snapshot NCM versionado. A consulta de NCM somente conclui presença/ausência quando issue_date == source_as_of; em qualquer outra data, registra cobertura indisponível sem declarar o código inválido.

## Matriz de escopo e fontes

| Verificação | Referência / evidência oficial | Implementação neste marco | Limite explícito |
| --- | --- | --- | --- |
| Leiaute e pacote de schemas | [Portal Nacional da NF-e — Esquemas XML](https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?AspxAutoDetectCookieSupport=1&tipoConteudo=BMPFMBoln3w%3D). Consultado em 2026-11-02; pacote indicado como em uso: PL 010f, NT 2025.002 v1.50 e NT 2026.007 v1.00, publicado em 2026-08-31. | Aceita raiz NFe ou nfeProc, leiaute infNFe@versao=4.00, modelo 55 e campos necessários às regras deste pacote. | Não baixa nem valida o XSD oficial. A versão do schema é dinâmica e deve ser revisada antes da validação integral. Aceitar esse subconjunto não equivale a aceitar NF-e válida. |
| Regra de total de produtos | [NT 2023.004 v1.10 — regra W16-10, Portal NF-e](https://www.nfe.fazenda.gov.br/Portal/exibirArquivo.aspx?AspxAutoDetectCookieSupport=1&conteudo=eWTd1q6pRMM%3D): relaciona vProd total ao somatório dos itens. | Compara exatamente, em decimal, soma dos valores det/prod/vProd com total/ICMSTot/vProd. | É controle de consistência limitado, não reproduz todas as exceções ou validações de autorização previstas nas Notas Técnicas. |
| Classificação NCM | [Download oficial da NCM — Portal Único Siscomex](https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json); contrato e limitações registrados em [01-pipeline-tributaria.md](01-pipeline-tributaria.md). | Consome uma projeção em memória identificada por release_id, SHA-256 e source_as_of; ausência é alerta consultivo apenas na data de cobertura. | O artefato corrente não é histórico. Não usa valid_from para inferir cobertura que o artefato não assegura. O motor não se conecta ao Supabase nesta entrega. |

O [MOC 7.0 — Anexo I](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=J+I+v4eN00E%3D) é referência geral do leiaute, mas é anterior ao pacote de schemas atual; não é usado como substituto de XSD ou de Notas Técnicas mais recentes.

## Contratos iniciais

- analyze_nfe(xml_bytes, catalog=None) -> AnalysisReport: função pura em packages/fiscal-engine/src/contai_fiscal_engine/engine.py. Não faz rede, I/O, logging do XML ou persistência.
- AnalysisReport: versão do contrato, estado (analyzed / rejected), modelo, data de emissão, release NCM usada e lista ordenada de alertas.
- Alert: rule_id, rule_version, severidade, código estável, mensagem curta, caminho de campo e evidências sem conteúdo integral do documento.
- NcmCatalogSnapshot: conjunto de códigos de oito dígitos e proveniência (release_id, snapshot_sha256, source_as_of). A cobertura declarada é single_date.
- Entrada limitada a 2 MB e 5.000 itens. DOCTYPE, declarações de entidade, XML malformado, modelo diferente de 55, leiaute diferente de 4.00 e campos necessários ausentes são rejeitados.
- IDs fiscais, razão social, endereços, valores integrais do documento e XML bruto não são copiados para o relatório.

## Plano curto de mudanças

1. Criar o pacote contai-fiscal-engine sem dependências de runtime e seus contratos tipados.
2. Implementar parser restrito, controles de segurança e as regras limitadas acima; incluir somente fixture sintética.
3. Cobrir parsing, XML inválido/inseguro, versão/modelo, consistência, catálogo com/sem cobertura e determinismo com testes offline.
4. Incluir pacote nos comandos CI existentes e atualizar o status da etapa no README.
5. Revisar o resultado antes de ampliar regras. Próximas capacidades dependem de fixtures/XSD oficiais versionados e de uma especificação própria; não são incluídas neste marco.

## Testes e aceite do primeiro marco

- Comandos de desenvolvimento: uv run --project packages/tax-data pytest --rootdir packages/tax-data packages/tax-data/tests e uv run --project packages/tax-data pytest --rootdir packages/fiscal-engine packages/fiscal-engine/tests.
- Fixture NF-e 4.00/modelo 55 sintética, sem dados reais.
- Rejeição de XML malformado, com DOCTYPE/entidade, modelo ou leiaute fora do contrato, tamanho excedido e campos essenciais inconsistentes.
- Divergência de total produz alerta com regra e valores comparados; caso consistente não produz esse alerta.
- NCM presente/ausente só é consultado na data coberta; fora dela a única conclusão é ncm_coverage_unavailable.
- Execuções repetidas da mesma entrada e catálogo produzem relatórios idênticos.
- Testes unitários não usam rede, Supabase, .env ou documentos de clientes.

## Fora deste marco

Validação XSD integral, assinatura digital, autorização SEFAZ, ZIP/lotes, duplicidade entre arquivos, CFOP/CST/CSOSN, cálculos ICMS/IPI/PIS/COFINS/IBS/CBS, interpretação de lei, persistência de resultados, interface desktop e carga de documentos ou resultados no Supabase. O motor pode ser conectado depois a dados tributários publicados, mediante contrato explícito de distribuição; não recebe credenciais nem acessa o banco nesta versão.
