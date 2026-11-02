# Retenção de dados tributários

O diretório `data/` mantém somente o índice das execuções mais recentes em [`tax-data/latest-runs.json`](tax-data/latest-runs.json). Capturas locais de trabalho ficam em `var/tax-data/`, ignorado pelo Git.

O Supabase `contai-dev` conserva releases estruturadas, metadados de proveniência, observações de captura, blocos legais e payloads brutos no schema privado `tax_ingest`. Os payloads são endereçados por SHA-256 e podem ser restaurados para reprocessamento com `packages/tax-data/scripts/restore_supabase_payload.py`.

Na consolidação de 02/11/2026, 34 payloads (20.563.634 bytes) foram restaurados/verificados no Supabase. Um metadado histórico NCM, `dfae9ea93ddaa01512009739341c38a01dd7a1d2c3e2fdf089f46dbe970d2fb5`, não tinha os bytes em `data/` nem nos artifacts do Actions consultados; o metadado foi preservado e a ausência está registrada, sem substituir o conteúdo por outra captura.

Os artifacts temporários do GitHub Actions expiram após 14 dias. A retenção histórica permanente de bruto e proveniência fica no Supabase dev; releases aprovadas permanecem nas tabelas versionadas de `tax_public`. Nenhuma carga foi feita em produção.
