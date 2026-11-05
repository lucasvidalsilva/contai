# contAI Desktop

Aplicativo Tauri v2 + React/TypeScript para conferência fiscal local. Aceita uma NF-e modelo 55 em XML ou um ZIP com
até 100 XMLs, remove duplicatas por conteúdo e mostra o progresso e o resultado de cada documento. O
`contai-fiscal-engine` é empacotado como sidecar e nenhum XML é enviado a servidores.

O pacote atual suporta Windows 10/11 x64. O instalador NSIS inclui o WebView2 offline, instala por usuário e não exige
Python, Rust, Node.js ou privilégios administrativos na máquina de destino.

## Preparação no Windows

- Microsoft C++ Build Tools com o workload Desktop development with C++;
- Rust stable com alvo `x86_64-pc-windows-msvc`;
- Node.js 24+ e Python 3.12 gerenciado pelo `uv`.

```powershell
uv sync --locked --project packages/fiscal-engine
npm ci --prefix apps/desktop
npm --prefix apps/desktop run sidecar:build
npm --prefix apps/desktop run sidecar:verify
npm --prefix apps/desktop run testdata:build
npm --prefix apps/desktop run testdata:verify
npm --prefix apps/desktop run desktop:dev
```

## Verificações

```powershell
npm --prefix apps/desktop run check
npm --prefix apps/desktop run lint
npm --prefix apps/desktop run test
npm --prefix apps/desktop run build
cargo fmt --manifest-path apps/desktop/src-tauri/Cargo.toml -- --check
cargo test --locked --manifest-path apps/desktop/src-tauri/Cargo.toml
```

## Instalador de teste

```powershell
npm --prefix apps/desktop run installer:build
npm --prefix apps/desktop run installer:verify
```

O instalador é criado em
`apps/desktop/src-tauri/target/release/bundle/nsis/contAI_0.1.0_x64-setup.exe`. A matriz para teste manual fica em
`apps/desktop/var/test-invoices/`; `13-lote-sintetico.zip` cobre lote, rejeição, alerta, arquivo não XML e duplicata.

Limites atuais: ZIP compactado de até 25 MB, no máximo 50 MB descompactados, 1.000 entradas, 100 XMLs e 2 MB por XML.
Arquivos protegidos por senha, links simbólicos e caminhos inseguros são rejeitados antes da análise.

O pacote local ainda não possui assinatura de código e pode acionar o SmartScreen. Não distribuir publicamente antes
da assinatura, dos testes em Windows 10/11 limpos e da aprovação visual do responsável pelo produto.

O executável do sidecar é gerado em `src-tauri/binaries/` e não é versionado. Consulte
[`docs/03-aplicativo.md`](../../docs/03-aplicativo.md) para escopo, critérios e limites de segurança.
