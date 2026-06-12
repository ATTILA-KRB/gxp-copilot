"""Tests du chunking structurel : pages, sections, budget de tokens, recouvrement."""

from __future__ import annotations

from ingestion.chunk import _ENCODING, _OVERLAP_TOKENS, _TARGET_TOKENS, chunk_pages
from ingestion.parse import ParsedPage


def _tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def test_empty_input_returns_no_chunks():
    assert chunk_pages([]) == []


def test_single_paragraph_single_chunk():
    pages = [ParsedPage(numero_page=3, texte="Un court paragraphe.")]
    chunks = chunk_pages(pages)
    assert len(chunks) == 1
    assert chunks[0].texte == "Un court paragraphe."
    assert chunks[0].numero_page == 3
    assert chunks[0].ordre == 0
    assert chunks[0].section is None


def test_section_detected_from_numbered_heading():
    pages = [ParsedPage(numero_page=1, texte="3.1 Access control\nLe contenu de la section.")]
    chunks = chunk_pages(pages)
    assert len(chunks) == 1
    assert chunks[0].section == "3.1"


def test_section_detected_from_keyword_heading():
    pages = [ParsedPage(numero_page=1, texte="Annex 11 Computerised Systems\nContenu.")]
    chunks = chunk_pages(pages)
    assert chunks[0].section == "Annex 11"


def test_section_detected_from_lone_number_line():
    # Style EU GMP Annexe 11 : le numero seul sur sa ligne, le titre en dessous.
    texte = "4.\nValidation\nLe contenu de la section validation.\n\n4.1\nSuite du contenu."
    pages = [ParsedPage(numero_page=1, texte=texte)]
    chunks = chunk_pages(pages)
    assert chunks[0].section == "4"


def test_chunk_section_is_section_at_chunk_start_not_last_seen():
    # Premier chunk : section 1 ; les en-tetes vus EN FIN de chunk ne doivent
    # pas re-etiqueter le chunk entier (bug observe sur l'Annexe 11 reelle).
    filler = " ".join(f"mot{i}" for i in range(420))  # remplit le budget du chunk 1
    texte = f"1. Introduction\n{filler}\n\n2. Scope\nContenu de la section deux."
    pages = [ParsedPage(numero_page=1, texte=texte)]
    chunks = chunk_pages(pages)
    assert len(chunks) >= 2
    assert chunks[0].section == "1"


def test_year_or_long_number_is_not_a_section():
    pages = [ParsedPage(numero_page=1, texte="2011\nUn paragraphe qui suit une annee.")]
    chunks = chunk_pages(pages)
    assert chunks[0].section is None


def test_section_propagates_to_following_paragraphs():
    texte = "4.2 Audit trail\nPremier paragraphe.\n\nDeuxieme paragraphe sans en-tete."
    pages = [ParsedPage(numero_page=1, texte=texte)]
    chunks = chunk_pages(pages)
    assert all(c.section == "4.2" for c in chunks)


def test_oversized_paragraph_is_split_under_budget():
    long_text = " ".join(f"mot{i}" for i in range(3000))  # >> _TARGET_TOKENS
    pages = [ParsedPage(numero_page=2, texte=long_text)]
    chunks = chunk_pages(pages)
    assert len(chunks) > 1
    for chunk in chunks:
        assert _tokens(chunk.texte) <= _TARGET_TOKENS + _OVERLAP_TOKENS
        assert chunk.numero_page == 2


def test_ordre_is_sequential():
    long_text = " ".join(f"mot{i}" for i in range(3000))
    pages = [ParsedPage(numero_page=1, texte=long_text)]
    chunks = chunk_pages(pages)
    assert [c.ordre for c in chunks] == list(range(len(chunks)))


def test_chunk_page_number_is_first_unit_page():
    # Deux pages dont les paragraphes tiennent dans un seul chunk :
    # le numero de page cite est celui du premier paragraphe.
    pages = [
        ParsedPage(numero_page=5, texte="Paragraphe page cinq."),
        ParsedPage(numero_page=6, texte="Paragraphe page six."),
    ]
    chunks = chunk_pages(pages)
    assert len(chunks) == 1
    assert chunks[0].numero_page == 5


def test_overlap_reinjects_tail_of_previous_chunk():
    # Paragraphes courts et nombreux : le dernier paragraphe d'un chunk
    # doit reapparaitre au debut du suivant (recouvrement <= _OVERLAP_TOKENS).
    paras = "\n\n".join(f"Paragraphe numero {i} avec un peu de texte." for i in range(120))
    pages = [ParsedPage(numero_page=1, texte=paras)]
    chunks = chunk_pages(pages)
    assert len(chunks) >= 2
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        # Le chunk suivant commence par la queue du precedent...
        first_para_next = nxt.texte.split("\n\n")[0]
        assert first_para_next in prev.texte
        # ...et contient bien le dernier paragraphe du precedent.
        last_para_prev = prev.texte.split("\n\n")[-1]
        assert last_para_prev in nxt.texte
