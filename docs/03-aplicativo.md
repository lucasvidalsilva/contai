# Etapa 03 — Aplicativo desktop

## Objetivo e estado

Construir a experiência local de conferência do contAI com Tauri v2, React e TypeScript. O XML fiscal permanece no
computador do usuário; a interface chama o motor Python da etapa 02 por um sidecar empacotado, sem API remota e sem
credenciais do Supabase.

**Estado:** em andamento. O primeiro corte vertical cobre uma NF-e por vez no Windows. Ele precisa funcionar de ponta
a ponta antes de lote, persistência ou exportação.

O instalador de desenvolvimento atual é direcionado a Windows 10/11 x64. Compatibilidade ampla não será declarada
somente porque a compilação funciona: ainda exige teste manual do produto, máquinas virtuais limpas e assinatura de
código antes da distribuição pública.

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
- O instalador NSIS usa português do Brasil, instalação por usuário e WebView2 offline; não exige privilégios de
  administrador nem conexão durante a instalação.

## Direção de produto e interface

A direção visual em validação usa as referências locais apenas como linguagem, sem copiar ou empacotar suas imagens:

- estrutura operacional com navegação carvão e área de trabalho creme;
- tipografia editorial contida nos títulos e sans-serif nos dados e controles;
- hierarquia compacta, bordas discretas, ícones lineares e ausência de gradientes, vidro ou decoração gratuita;
- estados e evidências mais importantes que slogans, ilustrações ou promessas de conformidade;
- uma única ação primária por contexto.

Essa direção ainda depende da aprovação visual do responsável pelo produto no instalador real. Os arquivos de
referência não entram no bundle nem no histórico Git.

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
- [x] verificar 12 NF-e sintéticas no sidecar de desenvolvimento e no sidecar instalado;
- [x] compilar frontend e backend Tauri no Windows;
- [x] instalar, inicializar e desinstalar o pacote NSIS em destino isolado;
- [x] documentar execução e limitações.

O item ainda aberto exige a seleção da fixture no diálogo da janela nativa e inspeção do relatório renderizado. O
sidecar e a UI já foram verificados separadamente; a build instalada inicializa WebView2 sem encerrar, mas o helper de
automação visual não estava disponível nesta execução. A aprovação manual do responsável pelo produto é obrigatória
antes de push ou pull request.

## Matriz sintética de validação

`npm run testdata:build` gera arquivos descartáveis em `apps/desktop/var/test-invoices/`, a partir da fixture sintética
da etapa 02. O manifesto `contai-desktop-testdata-v1` cobre:

- documento válido sem alertas;
- divergência de total de produtos, componentes e valor unitário;
- schema inválido, modelo 65, XML truncado, DTD, namespace ausente e UTF-16;
- arquivo vazio e arquivo acima de 2 MB.

`npm run testdata:verify` executa todos os casos contra o sidecar. Nenhum XML real, CNPJ válido ou documento de cliente
é usado.

## Instalador e compatibilidade

O comando `npm run installer:build` produz um NSIS x64 autocontido. `npm run installer:verify` instala o pacote em
`apps/desktop/var/install-smoke`, executa a matriz sintética com o sidecar instalado, mantém o aplicativo aberto por
oito segundos e desinstala a cópia de teste.

Resultado local atual:

- Windows cliente 25H2, build 26200, AMD64;
- instalação silenciosa por usuário com código de saída zero;
- aplicativo, sidecar e desinstalador presentes no destino;
- 12 cenários aprovados no sidecar instalado;
- inicialização do WebView2 sem stderr e desinstalação completa;
- instalador de 232.922.396 bytes com WebView2 offline.

Ainda são obrigatórios antes de concluir o M4:

- teste visual e funcional do responsável pelo produto;
- instalação limpa em Windows 10 x64 e Windows 11 x64;
- decisão e build separado para Windows ARM64, se entrar no suporte inicial;
- certificado de assinatura de código e verificação do fluxo SmartScreen;
- teste do instalador assinado, upgrade, downgrade e remoção de dados locais.

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

- Nenhum XML de cliente entra no repositório ou em testes; somente fixtures geradas a partir da NF-e sintética são
  permitidas.
- Nenhuma chave `service_role`, `.env` ou credencial é distribuída no aplicativo.
- A webview não executa comandos arbitrários e não recebe permissão para acessar todo o sistema de arquivos.
- O sidecar herda os limites do motor: NF-e 4.00 modelo 55, até 2 MB e 5.000 itens.
- `status=analyzed` não significa conformidade fiscal; assinatura, autorização SEFAZ e regras fora da etapa 02
  continuam não avaliadas.
