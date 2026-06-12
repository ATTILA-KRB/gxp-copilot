"""Tests du parsing PDF : numeros de page 1-indexes, pages vides ignorees, tableaux."""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from ingestion.parse import _tables_to_text, parse_pdf


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """PDF synthetique : page 1 avec texte, page 2 vide, page 3 avec texte."""
    path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text((72, 72), "Texte de la premiere page.")
    doc.new_page()  # page 2 vide
    page3 = doc.new_page()
    page3.insert_text((72, 72), "Texte de la troisieme page.")
    doc.save(str(path))
    doc.close()
    return path


def test_page_numbers_are_one_indexed_and_blank_pages_skipped(sample_pdf: Path):
    pages = parse_pdf(sample_pdf)
    assert [p.numero_page for p in pages] == [1, 3]


def test_page_text_is_extracted(sample_pdf: Path):
    pages = parse_pdf(sample_pdf)
    assert "premiere page" in pages[0].texte
    assert "troisieme page" in pages[1].texte


def test_tables_to_text_flattens_rows():
    tables = [[["Attribut", "Definition"], ["Attribuable", "Qui a fait quoi"], [None, ""]]]
    text = _tables_to_text(tables)
    assert "Attribut | Definition" in text
    assert "Attribuable | Qui a fait quoi" in text
    # La ligne entierement vide est ignoree.
    assert text.count("\n") == 1


def test_tables_to_text_empty_input():
    assert _tables_to_text([]) == ""


def test_tables_to_text_drops_empty_cells():
    # Cellules vides ignorees : pas de bruit "| | |" (observe sur PI 041-1).
    tables = [[["Signature", None, "", "Tracabilite"]]]
    assert _tables_to_text(tables) == "Signature | Tracabilite"


@pytest.fixture
def pdf_with_repeated_footer(tmp_path: Path) -> Path:
    """Quatre pages avec pied de page repete ('Guidance ACME' + 'Page N of 4')."""
    path = tmp_path / "footer.pdf"
    doc = fitz.open()
    contenus = ["alpha", "beta", "gamma", "delta"]
    for n, mot in enumerate(contenus, start=1):
        page = doc.new_page()
        page.insert_text((72, 72), f"Contenu utile {mot} de cette page.")
        page.insert_text((72, 760), "Guidance ACME Revision 1")
        page.insert_text((72, 780), f"Page {n} of 4")
    doc.save(str(path))
    doc.close()
    return path


def test_repeated_footer_removed(pdf_with_repeated_footer: Path):
    pages = parse_pdf(pdf_with_repeated_footer)
    assert len(pages) == 4
    for page in pages:
        assert "Guidance ACME" not in page.texte
        assert "of 4" not in page.texte
        assert "Contenu utile" in page.texte


def test_unique_edge_content_is_kept(sample_pdf: Path):
    # Trois pages au contenu distinct : rien ne doit etre retire.
    pages = parse_pdf(sample_pdf)
    assert "premiere page" in pages[0].texte
    assert "troisieme page" in pages[1].texte
