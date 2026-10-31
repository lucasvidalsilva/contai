"""Primeiro fluxo vertical: captura e release local da NCM vigente."""

from pathlib import Path

from contai_tax_data.ncm import DEFAULT_QUALITY_POLICY, QualityPolicy
from contai_tax_data.source import NCM_SOURCE_URL, SourceClient
from contai_tax_data.storage import IngestionResult, ingest_ncm_artifact


def capture_ncm(
    output_dir: Path,
    *,
    client: SourceClient | None = None,
    quality_policy: QualityPolicy = DEFAULT_QUALITY_POLICY,
) -> IngestionResult:
    source_client = client or SourceClient()
    artifact = source_client.fetch(NCM_SOURCE_URL)
    return ingest_ncm_artifact(artifact, output_dir, quality_policy=quality_policy)
