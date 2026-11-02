"""Motor local de verificações determinísticas da NF-e."""

from contai_fiscal_engine.catalog import NCM_CATALOG_CONTRACT_VERSION, dump_ncm_catalog, load_ncm_catalog
from contai_fiscal_engine.engine import analyze_nfe
from contai_fiscal_engine.models import Alert, AnalysisReport, NcmCatalogSnapshot

__all__ = [
    "NCM_CATALOG_CONTRACT_VERSION",
    "Alert",
    "AnalysisReport",
    "NcmCatalogSnapshot",
    "analyze_nfe",
    "dump_ncm_catalog",
    "load_ncm_catalog",
]
