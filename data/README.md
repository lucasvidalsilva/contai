# Dados tributários versionados

Esta pasta contém snapshots públicos capturados diretamente das fontes oficiais e seus arquivos normalizados. O Git registra cada atualização aprovada como histórico imutável e permite revisar diferenças por pull request. Não incluir documentos de clientes, credenciais ou dados pessoais.

## Snapshots iniciais

| Fonte | Captura (UTC) | Artefato bruto SHA-256 | Release/conjunto | Conteúdo |
|---|---|---|---|---|
| Portal Único Siscomex — NCM | 2026-11-01 | `65fa5c039c08b35608e836437f6923ce85f61a886fad7e2ec762ead56eb4125e` | `291b98c2473956bfa73905422aa800bfd88dc448acdf4b55e568d582aee7faaa` | 15.157 códigos, 10.516 folhas |
| Receita Federal — TIPI | 2026-11-01 | `d155f1baafb4039dcb74f97bb5abc1aec69f6760da9bd3f94a90bd40b33a2e9a` | `9254e157b3766355d0a8b1ec16ede911199787781d357d85b6d2dc85ec4c7bba` | 11.103 itens, 582 exceções |
| SVRS — IBS/CBS | 2026-11-01 | `5e1825e961461d18124ab3d7dd7f1b084688a53bd6afdc69311dd65378f6ccc9` | `e858a554bb21a386c9e65f4330d83ef562b77a3bb8067934158a86451d6d9e59` | 18 CST, 173 classificações, 4.728 vínculos |
| CONFAZ — CEST | 2026-10-31 | `7c2bdc9db1ceb11faaa56b2582e77e5a1bcb66e51cd62b6de0f155a78359c45a` | `0f39241a25eb02b0ae16b3c9d13879e7731b32f88d297f4d295698ab3cfee9e5` | 1.569 candidatos; todos `unresolved` |

Cada pasta de domínio preserva os caminhos de artefato, manifesto, release e ponteiro esperados pelos carregadores locais. Os arquivos brutos podem ser reprocessados com o contrato versionado; a NCM, TIPI e IBS/CBS têm releases estruturadas. CEST permanece apenas um conjunto de candidatos e não deve alimentar cálculo fiscal.

As URLs, cabeçalhos permitidos, horários completos, tamanho e status HTTP ficam nos manifestos das respectivas capturas. A atribuição à fonte oficial acompanha os metadados. A licença do código deste repositório não é apresentada como licença concedida por Receita Federal, SVRS ou CONFAZ para seus arquivos.

## Atualizações

Execute a captura em `var/tax-data/` para manter a área de trabalho; valide schema, qualidade, hash e diff; depois promova o artefato original, o manifesto e a release aceita para esta pasta em um branch próprio. Não substitua artefatos endereçados por hash nem altere um snapshot existente. A revisão do PR é o ponto de aprovação para persistir uma nova versão no GitHub.
