# Etapa 02 — Motor fiscal

## Objetivo e estado atual

Implementar um pacote Python local que receba XMLs **sintéticos** de NF-e modelo 55 e emita alertas determinísticos, rastreáveis e limitados às verificações implementadas. A ausência de alertas não representa conformidade fiscal. O motor não substitui revisão profissional.

O contrato `fiscal-engine-v1` implementa um subconjunto verificável: parsing seguro e limitado de XML NF-e 4.00, conferências I11-10/I11-20 do valor do item, soma W07-10 dos itens participantes do total, formato de NCM com oito dígitos e consulta opcional a um snapshot NCM versionado. A consulta de NCM somente conclui presença/ausência quando `issue_date == source_as_of`; em qualquer outra data, registra cobertura indisponível sem declarar o código inválido.

## Matriz de escopo e fontes

| Verificação | Referência / evidência oficial | Implementação neste marco | Limite explícito |
| --- | --- | --- | --- |
| Leiaute e pacote de schemas | [Portal Nacional da NF-e — Esquemas XML](https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?AspxAutoDetectCookieSupport=1&tipoConteudo=BMPFMBoln3w%3D). Consultado em 2026-11-02; pacote indicado como em uso: PL 010f, NT 2025.002 v1.50 e NT 2026.007 v1.00, publicado em 2026-08-31. | Aceita raiz NFe ou nfeProc, leiaute infNFe@versao=4.00, modelo 55 e campos necessários às regras deste pacote. | Não baixa nem valida o XSD oficial. A versão do schema é dinâmica e deve ser revisada antes da validação integral. Aceitar esse subconjunto não equivale a aceitar NF-e válida. |
| Valor do produto | [MOC 7.0 — regras I11-10 e I11-20](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=J+I+v4eN00E%3D): para NF-e normal, compara `vProd` com `qCom × vUnCom` e `qTrib × vUnTrib`; a nota (*4) determina arredondamento em duas casas e tolerância de R$ 0,01. | Calcula com `Decimal`, arredondamento `ROUND_HALF_UP` em duas casas e alerta somente quando a diferença absoluta excede R$ 0,01. | Só se aplica a `finNFe=1`. Não afirma reproduzir a autorização da SEFAZ. |
| Regra de total de produtos | [MOC 7.0 — regra W07-10](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=J+I+v4eN00E%3D): relaciona `ICMSTot/vProd` ao somatório dos itens com `indTot=1`. | Compara exatamente, em decimal, a soma de `det/prod/vProd` participante do total com `total/ICMSTot/vProd`; itens `indTot=0` são excluídos. | É controle de consistência limitado, não substitui XSD nem as demais validações de autorização. |
| Classificação NCM | [Download oficial da NCM — Portal Único Siscomex](https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json); contrato e limitações registrados em [01-pipeline-tributaria.md](01-pipeline-tributaria.md). | Consome uma projeção em memória identificada por release_id, SHA-256 e source_as_of; ausência é alerta consultivo apenas na data de cobertura. | O artefato corrente não é histórico. Não usa valid_from para inferir cobertura que o artefato não assegura. O motor não se conecta ao Supabase nesta entrega. |

O [MOC 7.0 — Anexo I](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=J+I+v4eN00E%3D) é referência geral do leiaute, mas é anterior ao pacote de schemas atual; não é usado como substituto de XSD ou de Notas Técnicas mais recentes.

## Contratos iniciais

- analyze_nfe(xml_bytes, catalog=None) -> AnalysisReport: função pura em packages/fiscal-engine/src/contai_fiscal_engine/engine.py. Não faz rede, I/O, logging do XML ou persistência.
- AnalysisReport: versão do contrato, estado (analyzed / rejected), modelo, data de emissão, release NCM usada e lista ordenada de alertas.
- Alert: rule_id, rule_version, severidade, código estável, mensagem curta, caminho de campo e evidências sem conteúdo integral do documento.
- NcmCatalogSnapshot: conjunto de códigos de oito dígitos e proveniência (release_id, snapshot_sha256, source_as_of). A cobertura declarada é single_date.
- `dump_ncm_catalog` / `load_ncm_catalog`: manifesto `contai-ncm-catalog-v1`, com a projeção folha completa (9.000 a 20.000 códigos), lista ordenada, contagem e hash SHA-256. Exportação parcial, corrupção ou inconsistência interna é rejeitada antes da análise; autenticidade ainda depende do canal futuro de sincronização.
- `contai-fiscal-engine XML [--ncm-catalog ARQUIVO]`: CLI local que emite somente o relatório JSON; saída 0 para documento analisado e 2 para entrada rejeitada ou erro de arquivo.
- Entrada limitada a 2 MB e 5.000 itens. DOCTYPE, declarações de entidade, XML malformado, modelo diferente de 55, leiaute diferente de 4.00 e campos necessários ausentes são rejeitados.
- IDs fiscais, razão social, endereços, valores integrais do documento e XML bruto não são copiados para o relatório.

## Dados publicados já aproveitáveis

Consulta somente leitura feita em 2026-11-02 no ambiente `contai-dev`; não é produção e os ponteiros correntes podem mudar:

| Domínio | Release corrente | Registros | Cobertura temporal | Uso no motor |
| --- | --- | ---: | --- | --- |
| NCM | `291b98c2473956bfa73905422aa800bfd88dc448acdf4b55e568d582aee7faaa` | 15.157 no total; 10.516 folhas | `source_as_of=2026-10-30` | Consumível por projeção local verificada; a fixture usa o código publicado `01012100`. |
| TIPI | `9254e157b3766355d0a8b1ec16ede911199787781d357d85b6d2dc85ec4c7bba` | 11.103 | A fonte capturada não declara `source_as_of`. | Ainda não compara alíquota; `0101.21.00` consta como `NT`, mas isso não é inferido como regra aplicável na data da NF-e. |
| IBS/CBS | `e858a554bb21a386c9e65f4330d83ef562b77a3bb8067934158a86451d6d9e59` | 173 classificações | Vigência por registro. | Mapeado para incremento posterior; não ativado automaticamente como interpretação fiscal. |

O motor não recebe credencial do banco. Um componente de sincronização futuro deverá ler `tax_public`, produzir o manifesto local e verificar seus hashes antes da troca atômica da versão usada pelo aplicativo.

## Entregas e próximo incremento

1. Entregue: pacote sem dependências de runtime, parser restrito, limites de segurança, contratos tipados e CI.
2. Entregue: regras I11-10, I11-20 e W07-10, fixture sintética com item dentro e fora do total e testes de tolerância.
3. Entregue: manifesto NCM local verificável e CLI para exercitar XML → relatório JSON sem rede.
4. Próximo: versionar e validar o pacote XSD oficial em uma camada separada; depois ampliar totais somente com as exceções documentadas.
5. Depois: definir contrato temporal próprio antes de ativar TIPI e IBS/CBS. Ausência de `source_as_of` ou regra curada continua produzindo cobertura indisponível, não conclusão fiscal.

## Testes e aceite do primeiro marco

- Comandos de desenvolvimento: uv run --project packages/tax-data pytest --rootdir packages/tax-data packages/tax-data/tests e uv run --project packages/tax-data pytest --rootdir packages/fiscal-engine packages/fiscal-engine/tests.
- Fixture NF-e 4.00/modelo 55 sintética, sem dados reais.
- Rejeição de XML malformado, com DOCTYPE/entidade, modelo ou leiaute fora do contrato, tamanho excedido e campos essenciais inconsistentes.
- Divergência em `qCom × vUnCom`, `qTrib × vUnTrib` ou total de produtos produz alerta com regra e valores comparados; diferença no limite de R$ 0,01 é aceita nas regras de item.
- Item com `indTot=0` não participa de W07-10.
- NCM presente/ausente só é consultado na data coberta; fora dela a única conclusão é ncm_coverage_unavailable.
- Catálogo local malformado, internamente inconsistente ou fora do contrato é rejeitado.
- Execuções repetidas da mesma entrada e catálogo produzem relatórios idênticos.
- Testes unitários não usam rede, Supabase, .env ou documentos de clientes.

Execução manual da fixture:

```bash
uv run --project packages/fiscal-engine contai-fiscal-engine packages/fiscal-engine/tests/fixtures/nfe-synthetic-55.xml
```

## Fora deste marco

Validação XSD integral, assinatura digital, autorização SEFAZ, ZIP/lotes, duplicidade entre arquivos, CFOP/CST/CSOSN, totais além de W07-10, cálculos ICMS/IPI/PIS/COFINS/IBS/CBS, interpretação de lei, persistência de resultados, interface desktop e carga de documentos ou resultados no Supabase. O motor aceita um catálogo NCM previamente sincronizado, mas não recebe credenciais nem acessa o banco nesta versão.
