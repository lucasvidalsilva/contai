# contAI Desktop

Aplicativo Tauri v2 + React/TypeScript para conferência fiscal local. O primeiro corte aceita uma NF-e modelo 55 por
vez e chama o `contai-fiscal-engine` empacotado como sidecar; o XML não é enviado a servidores.

## Preparação no Windows

- Microsoft C++ Build Tools com o workload Desktop development with C++;
- Rust stable com alvo `x86_64-pc-windows-msvc`;
- Node.js 24+ e Python 3.12 gerenciado pelo `uv`.

```powershell
uv sync --locked --project packages/fiscal-engine
npm ci --prefix apps/desktop
npm --prefix apps/desktop run sidecar:build
npm --prefix apps/desktop run sidecar:verify
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

O executável do sidecar é gerado em `src-tauri/binaries/` e não é versionado. Consulte
[`docs/03-aplicativo.md`](../../docs/03-aplicativo.md) para escopo, critérios e limites de segurança.
