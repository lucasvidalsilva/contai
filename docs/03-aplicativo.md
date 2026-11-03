# Etapa 03 — Aplicativo desktop

## Objetivo e estado

Construir a experiência local de conferência do contAI com Tauri v2, React e TypeScript. O XML fiscal permanece no
computador do usuário; a interface chama o motor Python da etapa 02 por um sidecar empacotado, sem API remota e sem
credenciais do Supabase.

**Estado:** em andamento. O primeiro corte vertical cobre uma NF-e por vez no Windows. Ele precisa funcionar de ponta
a ponta antes de lote, persistência ou exportação.

## Decisões do primeiro corte

- Tauri v2 com frontend Vite + React + TypeScript.
- Windows x86-64 primeiro; outros alvos exigirão builds nativos próprios do sidecar.
- `contai-fiscal-engine` empacotado com PyInstaller e registrado em `externalBin`.
- O frontend apenas solicita a seleção; o comando Rust abre o diálogo e não devolve o caminho completo à webview.
- A webview não recebe permissão de diálogo, sistema de arquivos ou shell.
- Um comando Rust valida extensão e tamanho, executa exclusivamente o sidecar conhecido e desserializa o contrato
  `fiscal-engine-v1` antes de devolver dados à webview.
- O relatório mostra apenas nome do arquivo, estado, modelo, data, versão do motor e alertas. Caminho completo e XML
  não são mantidos no estado exibido nem registrados em log.

O desenho segue as orientações oficiais de
[pré-requisitos do Tauri](https://v2.tauri.app/start/prerequisites/),
[sidecars](https://v2.tauri.app/develop/sidecar/) e
[diálogo nativo](https://v2.tauri.app/plugin/dialog/). O empacotamento Python segue a documentação de
[dados coletados pelo PyInstaller](https://pyinstaller.org/en/stable/runtime-information.html).

## Marcos e critérios

### M1 — fluxo individual local

- [x] selecionar somente um arquivo `.xml` pelo diálogo nativo;
- [x] construir e executar o sidecar sem exigir Python no uso do aplicativo empacotado;
- [ ] analisar a fixture sintética da etapa 02 e renderizar o relatório;
- [x] representar estados vazio, carregando, sucesso, alertas, rejeição e falha interna;
- [x] não expor caminho completo, XML, CNPJ, chave ou conteúdo fiscal em logs/erros;
- [x] testar contratos TypeScript, UI e fronteira Rust;
- [x] compilar frontend e backend Tauri no Windows;
- [x] documentar execução e limitações.

O item ainda aberto exige a seleção da fixture no diálogo da janela nativa e inspeção do relatório renderizado. O
sidecar e a UI já foram verificados separadamente; a build release inicializa WebView2 sem encerrar, mas o helper de
automação visual não estava disponível nesta execução.

### M2 — lote e deduplicação

- importar múltiplos XMLs e ZIPs com limites explícitos;
- identificar duplicidade local sem enviar chaves ou hashes ao servidor;
- acompanhar progresso, sucessos e rejeições por documento;
- permitir filtragem e priorização dos alertas.

### M3 — revisão persistente

- SQLite local versionado para sessões, resultados e decisões humanas;
- retenção e exclusão controladas pelo usuário;
- registro da versão do motor, regras e catálogo usados;
- migrações e testes de recuperação.

### M4 — exportação e acabamento

- exportar relatório reproduzível sem incluir XML por padrão;
- acessibilidade, atalhos, comportamento offline e instalador Windows verificados;
- política explícita para atualização do aplicativo e dos catálogos públicos.

A etapa 03 somente será declarada concluída após M1–M4. O primeiro corte não promete lote, histórico ou exportação.

## Segurança e limites

- Nenhum XML de cliente entra no repositório ou em testes; só a fixture sintética é permitida.
- Nenhuma chave `service_role`, `.env` ou credencial é distribuída no aplicativo.
- A webview não executa comandos arbitrários e não recebe permissão para acessar todo o sistema de arquivos.
- O sidecar herda os limites do motor: NF-e 4.00 modelo 55, até 2 MB e 5.000 itens.
- `status=analyzed` não significa conformidade fiscal; assinatura, autorização SEFAZ e regras fora da etapa 02
  continuam não avaliadas.
