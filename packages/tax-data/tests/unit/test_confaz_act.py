from __future__ import annotations

import pytest

from contai_tax_data.confaz_act import parse_confaz_act


def _html(*, include_ementa: bool = True) -> bytes:
    ementa = '<p class="A3Ementa">Altera o Convênio ICMS 142/18.</p>' if include_ementa else ""
    return (
        '<html><body><h1 class="documentFirstHeading">Convênio ICMS 38/19</h1>'
        '<div class="documentDescription description">Descrição oficial literal.</div>'
        '<div id="parent-fieldname-text">'
        '<p class="A1-1TituloAcordo">CONVÊNIO ICMS 38/19, DE 5 DE ABRIL DE 2019</p>'
        '<p class="A2DataPublicacao">Publicado no DOU em 09.04.19.</p>'
        f"{ementa}"
        '<p class="A5-1TextoAcordo"><b>Cláusula primeira</b> Texto literal.</p>'
        '<table><tr><td><p class="A7-2Tabelajustificado">Item 1.0 — produto.</p></td></tr></table>'
        "</div></body></html>"
    ).encode()


def test_confaz_act_parser_preserves_official_headers_and_structural_blocks() -> None:
    document = parse_confaz_act(_html())

    assert document.source_title == "Convênio ICMS 38/19"
    assert document.description_text == "Descrição oficial literal."
    assert document.act_title == "CONVÊNIO ICMS 38/19, DE 5 DE ABRIL DE 2019"
    assert document.publication_text == "Publicado no DOU em 09.04.19."
    assert document.summary_text == "Altera o Convênio ICMS 142/18."
    assert [block.source_class for block in document.blocks[:4]] == [
        "A1-1TituloAcordo",
        "A2DataPublicacao",
        "A3Ementa",
        "A5-1TextoAcordo",
    ]
    assert document.blocks[-1].source_class == "A7-2Tabelajustificado"
    assert document.blocks[-1].text == "Item 1.0 — produto."
    assert all(
        left.source_block_index < right.source_block_index
        for left, right in zip(document.blocks, document.blocks[1:], strict=False)
    )


def test_confaz_act_parser_accepts_official_corrigendum_class_aliases() -> None:
    body = _html().replace(b"A1-1TituloAcordo", b"TituloAcordo").replace(b"A3Ementa", b"Ementa")
    document = parse_confaz_act(body)

    assert document.act_title == "CONVÊNIO ICMS 38/19, DE 5 DE ABRIL DE 2019"
    assert document.summary_text == "Altera o Convênio ICMS 142/18."


def test_confaz_act_parser_keeps_text_around_malformed_nested_paragraph_tags() -> None:
    body = _html().replace(b"Texto literal.</p>", b"Antes <p></p>depois do paragrafo.</p>")
    document = parse_confaz_act(body)
    clause = next(block for block in document.blocks if block.source_class == "A5-1TextoAcordo")

    assert clause.text == "Cláusula primeira Antes depois do paragrafo."


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"<html><body>unrecognized page</body></html>", "sem campos obrigatórios"),
        (_html(include_ementa=False), "sem campos obrigatórios"),
        (b"<html><body>\xff</body></html>", "UTF-8"),
        (b"", "raiz HTML"),
    ],
)
def test_confaz_act_parser_rejects_unexpected_content(body: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_confaz_act(body)


def test_confaz_act_parser_rejects_missing_content_root() -> None:
    body = _html().replace(b'<div id="parent-fieldname-text">', b"<main>").replace(b"</div></body>", b"</main></body>")
    with pytest.raises(ValueError, match="sem campos obrigatórios"):
        parse_confaz_act(body)
