# Dados tributários versionados

Esta pasta contém snapshots públicos capturados diretamente das fontes oficiais e seus arquivos normalizados. O Git registra cada atualização aprovada como histórico imutável e permite revisar diferenças por pull request. Não incluir documentos de clientes, credenciais ou dados pessoais.

## Snapshots iniciais

| Fonte | Captura (UTC) | Artefato bruto SHA-256 | Release/conjunto | Conteúdo |
|---|---|---|---|---|
| Portal Único Siscomex — NCM | 2026-11-01 | `65fa5c039c08b35608e836437f6923ce85f61a886fad7e2ec762ead56eb4125e` | `291b98c2473956bfa73905422aa800bfd88dc448acdf4b55e568d582aee7faaa` | 15.157 códigos, 10.516 folhas |
| Receita Federal — TIPI | 2026-11-01 | `d155f1baafb4039dcb74f97bb5abc1aec69f6760da9bd3f94a90bd40b33a2e9a` | `9254e157b3766355d0a8b1ec16ede911199787781d357d85b6d2dc85ec4c7bba` | 11.103 itens, 582 exceções |
| SVRS — IBS/CBS | 2026-11-01 | `5e1825e961461d18124ab3d7dd7f1b084688a53bd6afdc69311dd65378f6ccc9` | `e858a554bb21a386c9e65f4330d83ef562b77a3bb8067934158a86451d6d9e59` | 18 CST, 173 classificações, 4.728 vínculos |
| CONFAZ — CEST | 2026-11-01 | `7c2bdc9db1ceb11faaa56b2582e77e5a1bcb66e51cd62b6de0f155a78359c45a` | `0f39241a25eb02b0ae16b3c9d13879e7731b32f88d297f4d295698ab3cfee9e5` | 1.569 candidatos; todos `unresolved`; captura confirmou texto do Convênio 107/26 |
| CONFAZ — sitemap oficial | 2026-11-01 | `78b3451ba25e4ab2d818c673e22764fda27712362d7d15820741108b76ce404d` | Snapshot `106e8b06f556eebf7e98b4ee94814fe93199299d4eb5e35eebaa2b4b9215c7e0` | 30.746 URLs na origem; 11.369 candidatos em convênios, ajustes e protocolos; `lastmod` não interpretado |
| CONFAZ — Convênio ICMS 107/26 | 2026-11-01 | `e471d2fdeed0d8841fc1a7f22e3c1e2e60c8bffa82f833f50daf82dea1363c94` | Sem parsing | HTML oficial, 114.390 bytes; URL validada pelo sitemap; conteúdo jurídico não interpretado |
| CONFAZ — referências de alteração do Convênio 142/18 | Reprocessado 2026-11-01 | Origem `7c2bdc9db1ceb11faaa56b2582e77e5a1bcb66e51cd62b6de0f155a78359c45a` | Snapshot `e3f89a9a0cad0289340611e568adff5ef22f4917841fbcdc8b6a4148e2b8f23a` | 25 referências literais; 24 URLs no catálogo e 1 `resolveuid` relativo não resolvido; sem interpretação jurídica |
| Câmara dos Deputados — LC 214/2025 atualizada | 2026-11-01 | `dc87a43e7a4c293bc3c47817754286438db33a7c42472eb0400258e7707a2bde` | Snapshot estrutural `d6eed7211094e706b096c6fd909ea8579c98de5208c17f13ea746397f3c24dea` | HTML oficial, 3.095.827 bytes; parser `federal-law-block-v3`, 8.793 blocos e 581 marcadores de artigo, sem vigência interpretada |
| Câmara — publicação original LC 214/2025 | 2026-11-01 | `efd06578a4789874fd277c3dbf68d424cd9b4baebc1a853735ec350b692ecd29` | Sem parsing | HTML oficial, 958.783 bytes |
| Câmara — mensagem de veto LC 214/2025 | 2026-11-01 | `de0fedef4f5c0725fd9a505675c7651b3c72b605466d37649dd368778ff5dc90` | Sem parsing | HTML oficial, 77.738 bytes |
| Câmara — promulgação dos vetos LC 214/2025 | 2026-11-01 | `554c50ed37f0aadf63bcf401814409fdfa3541b18a4149f67e0a7b0093638d3b` | Sem parsing | HTML oficial, 43.729 bytes |

Cada pasta de domínio preserva os caminhos de artefato, manifesto, snapshot e ponteiro esperados pelos fluxos locais. NCM, TIPI e IBS/CBS têm releases estruturadas; CEST permanece como candidatos unresolved. CONFAZ mantém um índice de URLs, a captura bruta individual do Convênio 107/26 e referências explícitas de alteração extraídas do Convênio 142/18, sem classificação jurídica. LC 214 tem texto bruto e blocos estruturais literais, sem relações históricas, status de vigência ou aptidão para cálculo fiscal.

As URLs, cabeçalhos permitidos, horários completos, tamanho e status HTTP ficam nos manifestos das respectivas capturas. A atribuição à fonte oficial acompanha os metadados. A licença do código deste repositório não é apresentada como licença concedida por Receita Federal, SVRS, CONFAZ ou Câmara dos Deputados para seus arquivos.

## Atualizações

Execute a captura em `var/tax-data/` para manter a área de trabalho; valide schema, qualidade, hash e diff; depois promova o artefato original, o manifesto e a release aceita para esta pasta em um branch próprio. Não substitua artefatos endereçados por hash nem altere um snapshot existente. A revisão do PR é o ponto de aprovação para persistir uma nova versão no GitHub.
