# Etapa 02 — Motor fiscal

## Objetivo, estado e definição finita

Entregar o primeiro motor fiscal local do contAI: um pacote Python reproduzível que recebe uma NF-e 4.00
modelo 55, valida sua estrutura e executa um conjunto **explicitamente limitado** de conferências determinísticas.
O resultado é um relatório JSON com regras versionadas e evidências, sem copiar o XML ou identificadores fiscais.

O contrato público deste marco é `fiscal-engine-v1`. A etapa 02 só pode ser encerrada quando todos os critérios
abaixo estiverem verificados:

- [x] pacote Python 3.12 isolado, lockfile próprio e CLI local;
- [x] validação offline pelo XSD oficial da NF-e, com versão, origem e hashes fixados;
- [x] rejeição segura de entrada malformada, fora do contrato ou acima dos limites;
- [x] regras I11-10, I11-20, W07-10, W08-10, W09-10, W10-10 e W15-10 com evidências estáveis;
- [x] consulta NCM opcional, local, versionada e sem extrapolação temporal;
- [x] fixture integralmente sintética e regressões offline de estrutura, cálculo, segurança e determinismo;
- [x] execução no CI de lockfile, lint, formatação, tipos e testes do motor em seu próprio ambiente;
- [x] artefatos wheel e sdist contendo os cinco XSDs necessários;
- [x] limites de cobertura documentados, sem alegação de conformidade fiscal integral.

**Interpretação do resultado:** `status=analyzed` significa apenas que a entrada passou pelo contrato estrutural e
que as regras listadas aqui foram executadas. Ausência de alerta não é garantia de conformidade fiscal, validade da
assinatura, autorização pela SEFAZ ou correção tributária completa.

## Fontes oficiais e artefatos fixados

### Leiaute XML

O motor incorpora o subconjunto NF-e do pacote oficial
[`PL_010g_v1.03.zip`](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=EQhOQMgipXY%3D),
publicado no Portal Nacional em 2026-10-26 e capturado em 2026-11-02.

- SHA-256 do ZIP: `b329ecbe7e4c05a41bfbc1527f105defb7047328acfeada7c77e1666da485eaf`;
- cinco XSDs preservados sem modificação em
  `packages/fiscal-engine/src/contai_fiscal_engine/schemas/pl_010g_v1_03/`;
- hash de cada arquivo registrado no README do pacote e conferido em runtime antes de compilar o schema;
- validação sem rede, DTD ou resolução de entidades externas.

Para raiz `NFe`, o documento completo é validado. Para `nfeProc`, este marco valida apenas o filho `NFe`, pois os
schemas de processo/protocolo não pertencem ao subconjunto incorporado. A conformidade XMLDSig é somente estrutural:
o motor não verifica criptografia, certificado, cadeia de confiança ou autorização.

### Regras de cálculo

As conferências abaixo seguem o
[`MOC 7.0 — Anexo I`](https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=J+I+v4eN00E%3D).
Notas técnicas posteriores podem alterar leiaute e regras; por isso, o XSD e cada regra permanecem versionados
separadamente e não são atualizados de modo implícito.

| Regra oficial | Regra contAI | Conferência implementada | Limite |
| --- | --- | --- | --- |
| I11-10 | `NFE-ITEM-VPROD-COM-001` | `vProd` versus `qCom × vUnCom`, arredondado em duas casas | Somente `finNFe=1`; alerta se diferença absoluta for maior que R$ 0,01 |
| I11-20 | `NFE-ITEM-VPROD-TRIB-001` | `vProd` versus `qTrib × vUnTrib`, arredondado em duas casas | Mesmo limite e tolerância de I11-10 |
| W07-10 | `NFE-TOTAL-PROD-001` | `ICMSTot/vProd` versus soma de `prod/vProd` | Somente itens com `indTot=1` |
| W08-10 | `NFE-TOTAL-FRETE-001` | `ICMSTot/vFrete` versus soma de `prod/vFrete` | Campo ausente no item vale zero |
| W09-10 | `NFE-TOTAL-SEGURO-001` | `ICMSTot/vSeg` versus soma de `prod/vSeg` | Campo ausente no item vale zero |
| W10-10 | `NFE-TOTAL-DESCONTO-001` | `ICMSTot/vDesc` versus soma de `prod/vDesc` | Campo ausente no item vale zero |
| W15-10 | `NFE-TOTAL-OUTRO-001` | `ICMSTot/vOutro` versus soma de `prod/vOutro` | Campo ausente no item vale zero |

Os cálculos usam `Decimal`; não passam por ponto flutuante binário. As regras de total são alertas de consistência,
não uma reprodução da autorização estadual.

### Catálogo NCM

`NcmCatalogSnapshot` recebe apenas uma projeção local com `release_id`, SHA-256 do snapshot, `source_as_of` e os
códigos folha de oito dígitos. O manifesto `contai-ncm-catalog-v1` valida formato, ordenação, contagem, completude
plausível e hash interno antes do uso.

O motor só conclui presença ou ausência quando `issue_date == source_as_of`. Para qualquer outra data, emite
`ncm_coverage_unavailable`; não usa a observação corrente para afirmar validade histórica. O motor não recebe
credenciais nem acessa o Supabase.

O snapshot público observado em `contai-dev` em 2026-11-02 tinha `source_as_of=2026-10-30`, 15.157 registros totais
e 10.516 folhas. TIPI e IBS/CBS não são ativados automaticamente: dado publicado não equivale a regra fiscal curada.

## Contratos e segurança

- `analyze_nfe(xml_bytes, catalog=None) -> AnalysisReport` é puro: não usa rede, arquivo, banco ou logging do XML.
- `Alert` informa `rule_id`, versão, severidade, código, caminho e evidências mínimas.
- A entrada aceita é `NFe` ou `nfeProc`, NF-e 4.00, modelo 55, UTF-8, até 2 MB e 5.000 itens.
- DOCTYPE, declaração de entidade, XML malformado, namespace inesperado e falha de XSD são rejeitados.
- O relatório não replica chave, CNPJ/CPF, emitente, destinatário, endereço, XML bruto ou assinatura.
- Falhas do XSD expõem apenas tipo, caminho e versão do pacote, não o valor privado encontrado.
- A fixture usa CNPJ/IE zerados, nomes e endereços declaradamente sintéticos e uma XMLDSig fictícia necessária
  apenas para satisfazer a estrutura do XSD. Ela não representa documento autorizado nem assinatura válida.

## Execução e testes

Preparação e verificações do pacote:

```bash
uv sync --locked --project packages/fiscal-engine
uv run --project packages/fiscal-engine pytest --rootdir packages/fiscal-engine packages/fiscal-engine/tests
uv run --project packages/fiscal-engine ruff check packages/fiscal-engine
uv run --project packages/fiscal-engine ruff format --check packages/fiscal-engine
uv run --project packages/fiscal-engine mypy packages/fiscal-engine/src
```

Demonstração local sem catálogo:

```bash
uv run --project packages/fiscal-engine contai-fiscal-engine \
  packages/fiscal-engine/tests/fixtures/nfe-synthetic-55.xml
```

Saída `0` significa documento analisado; saída `2` significa documento rejeitado ou erro local. O JSON usa ordem
estável de chaves. Repetir a mesma entrada com o mesmo catálogo produz o mesmo relatório.

Os testes transformam a fixture válida em cenários sintéticos para cobrir: campo obrigatório ausente, XSD inválido,
DOCTYPE/entidade, codificação, namespace, versão e modelo fora do contrato, limites, tolerância de R$ 0,01, valores
comercial e tributável divergentes, itens dentro/fora de W07, todos os totais implementados, cobertura temporal NCM,
manifesto corrompido, CLI e determinismo. Nenhum teste do motor usa rede, Supabase, `.env` ou documento de cliente.

## Fora da etapa 02

- validação criptográfica XMLDSig, certificado, consulta de protocolo e autorização SEFAZ;
- validação do envelope/protocolo de `nfeProc`, eventos, inutilização, lotes e ZIP;
- deduplicação entre arquivos, persistência local e interface — responsabilidades da etapa 03;
- CNPJ/CPF/IE, GTIN, CFOP, CST/CSOSN, benefício fiscal e regras estaduais;
- W11 a W16 e cálculos de ICMS, FCP, ST, IPI, II, PIS, COFINS, ISSQN, IBS/CBS e Imposto Seletivo;
- aplicação automática de TIPI, legislação ou inferência de enquadramento tributário;
- alegação de que o conjunto atual substitui revisão profissional ou cobre toda a validação da SEFAZ.

Novas regras podem ampliar o motor em versões posteriores, mas não reabrem esta definição de etapa: devem ter fonte,
vigência, exceções, identificador, testes e mudança de versão próprios.
