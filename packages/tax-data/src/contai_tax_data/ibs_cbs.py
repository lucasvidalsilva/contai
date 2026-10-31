"""Contrato publico do catalogo IBS/CBS exposto pela SVRS/Conformidade Facil."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

IBS_CBS_SOURCE_URL = "https://dfe-portal.svrs.rs.gov.br/CFF/ClassificacaoTributaria"
IBS_CBS_CONTRACT_VERSION = "ibs-cbs-v1"
IBS_CBS_ACCEPT = "text/html"

_DATA_PATTERN = re.compile(r"var\s+dadosOriginais\s*=\s*(\[.*?\]);\s*var\s+dadosFiltrados", re.DOTALL)
_CST_FIELDS = frozenset(
    {
        "Cst",
        "NomeCst",
        "IndExigeTrib",
        "IndMonofasica",
        "IndReducaoAliq",
        "IndDiferimento",
        "DthPublicacao",
        "DthIniVig",
        "DthFimVig",
        "CtrDthInc",
        "IndReducaoBc",
        "IndTransferenciaCred",
        "IndCredPresIbsZfm",
        "IndAjusteCompet",
        "ClassificacoesTributarias",
    }
)
_CLASS_FIELDS = frozenset(
    {
        "CodClassTrib",
        "NomeClassTrib",
        "IndTribRegular",
        "IndPermiteCredPres",
        "PercRedIbs",
        "PercRedCbs",
        "DthPublicacao",
        "DthIniVig",
        "DthFimVig",
        "CtrDthInc",
        "Cst",
        "IndMonoRetem",
        "IndMonoRet",
        "IndMonoDif",
        "NomeReduzido",
        "IndMonoVal",
        "IndNfe",
        "IndNfce",
        "IndCte",
        "IndCteos",
        "IndBpe",
        "IndNf3e",
        "IndNfcom",
        "IndNfse",
        "IndBpetm",
        "IndBpeta",
        "IndNfag",
        "IndNfsvia",
        "IndNfabi",
        "NroAnexo",
        "TexUrlLegislacao",
        "TipoAliq",
        "IndEstornoCred",
        "IndNfgas",
        "IndDere",
        "TexRegCbs",
        "TexRegIbs",
        "IndPbioDiferenca",
        "IndDir",
        "IndDuimp",
        "TipoRbSn",
        "TipoDoacao",
        "PossuiIndDfe",
        "CstNavigation",
        "Anexos",
        "AnexoNew",
    }
)
_ANNEX_FIELDS = frozenset(
    {
        "CodIntProdServ",
        "NroAnexo",
        "CodNcmNbs",
        "TipoCodigo",
        "TipoPermissao",
        "DescCondicao",
        "DescExcecao",
        "Observacao",
        "DthIniVig",
        "DthFimVig",
        "CtrDthInc",
        "NroItemAnexoLei",
        "DescItemAnexo",
        "DescAnexo",
    }
)
_IGNORED_CST_FIELDS = frozenset({"CtrDthInc", "ClassificacoesTributarias"})
_IGNORED_CLASS_FIELDS = frozenset({"CtrDthInc", "CstNavigation", "Anexos", "AnexoNew"})
_IGNORED_ANNEX_FIELDS = frozenset({"CtrDthInc"})


class IbsCbsContractError(ValueError):
    """HTML, JSON incorporado ou schema inesperado na origem oficial."""


class IbsCbsQualityError(ValueError):
    """Catálogo fora dos limites plausíveis definidos para a captura."""


@dataclass(frozen=True, slots=True)
class IbsCbsDataset:
    csts: tuple[dict[str, Any], ...]
    classifications: tuple[dict[str, Any], ...]
    annex_links: tuple[dict[str, Any], ...]


def _object(value: object, expected: frozenset[str], context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise IbsCbsContractError(f"{context} deve ser objeto")
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise IbsCbsContractError(f"schema {context} divergente; ausentes={missing}; novos={extra}")
    return value


def _date(value: object, field: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str):
        raise IbsCbsContractError(f"{field} deve ser data ISO ou nulo")
    try:
        _parse_datetime(value)
    except ValueError:
        raise IbsCbsContractError(f"{field} deve conter data ISO") from None


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _check_date_range(start: object, end: object, context: str) -> None:
    if (
        end is not None
        and isinstance(start, str)
        and isinstance(end, str)
        and _parse_datetime(end) < _parse_datetime(start)
    ):
        raise IbsCbsContractError(f"vigencia invertida em {context}")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IbsCbsContractError(f"{field} deve ser texto nao vazio")
    return " ".join(value.split())


def _boolean_fields(record: dict[str, Any], fields: tuple[str, ...], context: str) -> None:
    for field in fields:
        if type(record[field]) is not bool:
            raise IbsCbsContractError(f"{context}.{field} deve ser booleano")


def _copy_fields(record: dict[str, Any], ignored: frozenset[str]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in ignored}


def parse_ibs_cbs_html(body: bytes) -> IbsCbsDataset:
    if not body:
        raise IbsCbsContractError("HTML vazio")
    try:
        html = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise IbsCbsContractError("HTML deve estar em UTF-8") from None
    match = _DATA_PATTERN.search(html)
    if not match:
        raise IbsCbsContractError("bloco dadosOriginais da SVRS nao encontrado")
    try:
        source_csts = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        message = f"JSON dadosOriginais malformado na linha {error.lineno}, coluna {error.colno}"
        raise IbsCbsContractError(message) from None
    if not isinstance(source_csts, list):
        raise IbsCbsContractError("dadosOriginais deve ser lista")

    csts: list[dict[str, Any]] = []
    classifications: list[dict[str, Any]] = []
    annex_links: list[dict[str, Any]] = []
    cst_codes: set[str] = set()
    class_codes: set[str] = set()
    annex_record_keys: set[tuple[str, int]] = set()
    for index, source_cst in enumerate(source_csts):
        cst = _object(source_cst, _CST_FIELDS, f"CST[{index}]")
        cst_code = _required_text(cst["Cst"], f"CST[{index}].Cst")
        if not re.fullmatch(r"\d{3}", cst_code) or cst_code in cst_codes:
            raise IbsCbsContractError(f"CST invalido ou duplicado: {cst_code!r}")
        cst_codes.add(cst_code)
        _required_text(cst["NomeCst"], f"CST[{index}].NomeCst")
        _boolean_fields(
            cst,
            (
                "IndExigeTrib",
                "IndMonofasica",
                "IndReducaoAliq",
                "IndDiferimento",
                "IndReducaoBc",
                "IndTransferenciaCred",
                "IndCredPresIbsZfm",
                "IndAjusteCompet",
            ),
            f"CST[{index}]",
        )
        for field in ("DthPublicacao", "DthIniVig"):
            _date(cst[field], f"CST[{index}].{field}")
        _date(cst["DthFimVig"], f"CST[{index}].DthFimVig", nullable=True)
        _check_date_range(cst["DthIniVig"], cst["DthFimVig"], f"CST[{index}]")
        source_classes = cst["ClassificacoesTributarias"]
        if not isinstance(source_classes, list):
            raise IbsCbsContractError(f"CST[{index}].ClassificacoesTributarias deve ser lista")
        csts.append(_copy_fields(cst, _IGNORED_CST_FIELDS))
        for class_index, source_class in enumerate(source_classes):
            context = f"cClassTrib[{class_index}]"
            classification = _object(source_class, _CLASS_FIELDS, context)
            class_code = _required_text(classification["CodClassTrib"], f"{context}.CodClassTrib")
            if not re.fullmatch(r"\d{6}", class_code) or class_code in class_codes:
                raise IbsCbsContractError(f"cClassTrib invalido ou duplicado: {class_code!r}")
            if classification["Cst"] != cst_code:
                raise IbsCbsContractError(f"CST divergente em cClassTrib {class_code}")
            class_codes.add(class_code)
            for field in ("NomeClassTrib", "NomeReduzido"):
                _required_text(classification[field], f"{context}.{field}")
            for field in ("DthPublicacao", "DthIniVig"):
                _date(classification[field], f"{context}.{field}")
            _date(classification["DthFimVig"], f"{context}.DthFimVig", nullable=True)
            _check_date_range(classification["DthIniVig"], classification["DthFimVig"], context)
            for field in ("PercRedIbs", "PercRedCbs"):
                amount = classification[field]
                if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not 0 <= amount <= 100:
                    raise IbsCbsContractError(f"{context}.{field} deve ser percentual entre 0 e 100")
            annex_number = classification["NroAnexo"]
            if annex_number is not None and (not isinstance(annex_number, int) or isinstance(annex_number, bool)):
                raise IbsCbsContractError(f"{context}.NroAnexo deve ser inteiro ou nulo")
            for field in (
                "IndTribRegular",
                "IndPermiteCredPres",
                "IndMonoRetem",
                "IndMonoRet",
                "IndMonoDif",
                "IndMonoVal",
                "IndNfe",
                "IndNfce",
                "IndCte",
                "IndCteos",
                "IndBpe",
                "IndNf3e",
                "IndNfcom",
                "IndNfse",
                "IndBpetm",
                "IndBpeta",
                "IndNfag",
                "IndNfsvia",
                "IndNfabi",
                "IndEstornoCred",
                "IndNfgas",
                "IndDere",
                "IndPbioDiferenca",
                "IndDir",
                "IndDuimp",
                "PossuiIndDfe",
            ):
                if type(classification[field]) is not bool:
                    raise IbsCbsContractError(f"{context}.{field} deve ser booleano")
            classifications.append(_copy_fields(classification, _IGNORED_CLASS_FIELDS))
            source_annexes = classification["Anexos"]
            if not isinstance(source_annexes, list):
                raise IbsCbsContractError(f"{context}.Anexos deve ser lista")
            for annex_index, source_annex in enumerate(source_annexes):
                annex_context = f"{context}.Anexos[{annex_index}]"
                annex = _object(source_annex, _ANNEX_FIELDS, annex_context)
                source_id = annex["CodIntProdServ"]
                annex_number = annex["NroAnexo"]
                item_number = annex["NroItemAnexoLei"]
                if not isinstance(source_id, int) or isinstance(source_id, bool) or source_id <= 0:
                    raise IbsCbsContractError(f"{annex_context}.CodIntProdServ deve ser inteiro positivo")
                if not isinstance(annex_number, int) or isinstance(annex_number, bool):
                    raise IbsCbsContractError(f"{annex_context}.NroAnexo deve ser inteiro")
                if item_number is not None and (not isinstance(item_number, int) or isinstance(item_number, bool)):
                    raise IbsCbsContractError(f"{annex_context}.NroItemAnexoLei deve ser inteiro ou nulo")
                if (class_code, source_id) in annex_record_keys:
                    raise IbsCbsContractError(f"vinculo duplicado em {annex_context}")
                annex_record_keys.add((class_code, source_id))
                code = _required_text(annex["CodNcmNbs"], f"{annex_context}.CodNcmNbs")
                code_type = _required_text(annex["TipoCodigo"], f"{annex_context}.TipoCodigo")
                if code_type not in {"NCM", "NBS"} or not re.fullmatch(r"\d+", code):
                    raise IbsCbsContractError(f"tipo/codigo NCM-NBS invalido em {annex_context}")
                for field in (
                    "TipoPermissao",
                    "DescCondicao",
                    "DescExcecao",
                    "Observacao",
                    "DescItemAnexo",
                    "DescAnexo",
                ):
                    if annex[field] is not None and not isinstance(annex[field], str):
                        raise IbsCbsContractError(f"{annex_context}.{field} deve ser texto ou nulo")
                for field in ("DthIniVig",):
                    _date(annex[field], f"{annex_context}.{field}")
                _date(annex["DthFimVig"], f"{annex_context}.DthFimVig", nullable=True)
                _check_date_range(annex["DthIniVig"], annex["DthFimVig"], annex_context)
                annex_links.append(
                    {
                        "cclasstrib_code": class_code,
                        "source_record_id": annex["CodIntProdServ"],
                        **_copy_fields(annex, _IGNORED_ANNEX_FIELDS),
                    }
                )

    return IbsCbsDataset(tuple(csts), tuple(classifications), tuple(annex_links))


def validate_ibs_cbs(
    dataset: IbsCbsDataset,
    *,
    minimum_csts: int = 1,
    maximum_csts: int = 40,
    minimum_classifications: int = 100,
    maximum_classifications: int = 500,
    maximum_annex_links: int = 50_000,
) -> None:
    if not minimum_csts <= len(dataset.csts) <= maximum_csts:
        raise IbsCbsQualityError(f"quantidade de CST fora do intervalo plausivel: {len(dataset.csts)}")
    if not minimum_classifications <= len(dataset.classifications) <= maximum_classifications:
        raise IbsCbsQualityError(
            f"quantidade de cClassTrib fora do intervalo plausivel: {len(dataset.classifications)}"
        )
    if not 0 <= len(dataset.annex_links) <= maximum_annex_links:
        raise IbsCbsQualityError(f"quantidade de vinculos fora do intervalo plausivel: {len(dataset.annex_links)}")
    cst_codes = {record["Cst"] for record in dataset.csts}
    if any(record["Cst"] not in cst_codes for record in dataset.classifications):
        raise IbsCbsQualityError("classificacao referencia CST ausente")
    class_codes = {record["CodClassTrib"] for record in dataset.classifications}
    if any(record["cclasstrib_code"] not in class_codes for record in dataset.annex_links):
        raise IbsCbsQualityError("vinculo referencia cClassTrib ausente")


def ibs_cbs_snapshot(dataset: IbsCbsDataset) -> bytes:
    values = (
        [{"record_type": "cst", **record} for record in dataset.csts]
        + [{"record_type": "cclasstrib", **record} for record in dataset.classifications]
        + [{"record_type": "annex_link", **record} for record in dataset.annex_links]
    )
    values.sort(
        key=lambda row: (
            row["record_type"],
            row.get("Cst", row.get("cclasstrib_code", "")),
            row.get("CodClassTrib", ""),
            row.get("CodNcmNbs", ""),
            json.dumps(row, ensure_ascii=False, sort_keys=True),
        )
    )
    return b"".join(
        (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for row in values
    )


def ibs_cbs_release_id(snapshot: bytes) -> str:
    return hashlib.sha256(f"{IBS_CBS_CONTRACT_VERSION}\n".encode() + snapshot).hexdigest()
