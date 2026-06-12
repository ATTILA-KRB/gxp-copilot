"""Extraction PDF : texte par page (+ numero de page) et tableaux.

Le numero de page est indispensable : il alimente la citation verifiable
(document + page + passage), pilier du projet.

Les en-tetes/pieds de page repetes (titre du document, "Page N of M") sont
retires : ils polluent les chunks et donc la recherche. Une ligne est jugee
"mobilier" si, une fois ses chiffres normalises, elle apparait en bord de
page sur une majorite de pages.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

try:  # pymupdf expose les deux noms selon la version
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

# Lignes inspectees en haut et en bas de chaque page.
_FURNITURE_EDGE_LINES = 3
# Part minimale de pages ou la ligne doit apparaitre pour etre retiree.
_FURNITURE_MIN_RATIO = 0.6


@dataclass(frozen=True)
class ParsedPage:
    numero_page: int  # 1-indexe (comme affiche dans un lecteur PDF)
    texte: str


def _normalize_furniture(line: str) -> str:
    """Cle de comparaison : chiffres masques ("Page 5 of 21" == "Page 7 of 21")."""
    return re.sub(r"\d+", "#", line.strip()).lower()


def _edge_line_indices(lines: list[str]) -> set[int]:
    """Indices des lignes non vides en bord de page (haut et bas)."""
    nonempty = [i for i, line in enumerate(lines) if line.strip()]
    return set(nonempty[:_FURNITURE_EDGE_LINES] + nonempty[-_FURNITURE_EDGE_LINES:])


def _remove_repeated_furniture(texts: list[str]) -> list[str]:
    """Retire les lignes d'en-tete/pied repetees sur une majorite de pages."""
    if len(texts) < 3:
        return texts

    counts: Counter[str] = Counter()
    for text in texts:
        lines = text.splitlines()
        edge_keys = {_normalize_furniture(lines[i]) for i in _edge_line_indices(lines)}
        counts.update(edge_keys)

    threshold = max(2, int(len(texts) * _FURNITURE_MIN_RATIO))
    furniture = {key for key, count in counts.items() if count >= threshold}
    if not furniture:
        return texts

    cleaned: list[str] = []
    for text in texts:
        lines = text.splitlines()
        edge = _edge_line_indices(lines)
        kept = [
            line
            for i, line in enumerate(lines)
            if not (i in edge and _normalize_furniture(line) in furniture)
        ]
        cleaned.append("\n".join(kept))
    return cleaned


def _tables_to_text(tables: list[list[list[str | None]]]) -> str:
    """Aplati les tableaux en lignes 'cellule | cellule', cellules vides ignorees."""
    blocks: list[str] = []
    for table in tables:
        rows = [
            " | ".join(cell.strip() for cell in row if cell and cell.strip())
            for row in table
            if any(cell and cell.strip() for cell in row)
        ]
        if rows:
            blocks.append("\n".join(rows))
    return "\n\n".join(blocks)


def _extract_tables_by_page(path: Path) -> dict[int, str]:
    """Tableaux par numero de page (1-indexe). Best-effort : echec silencieux."""
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover
        return {}

    result: dict[int, str] = {}
    try:
        with pdfplumber.open(str(path)) as pdf:
            for idx, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables()
                if tables:
                    text = _tables_to_text(tables)
                    if text:
                        result[idx] = text
    except Exception:  # noqa: BLE001 - les tableaux sont un bonus, pas un bloquant
        return {}
    return result


def parse_pdf(path: Path) -> list[ParsedPage]:
    """Renvoie une page par element, texte + tableaux concatenes, pages vides ignorees."""
    tables_by_page = _extract_tables_by_page(path)
    with fitz.open(str(path)) as doc:
        raw_texts = [page.get_text("text") for page in doc]

    texts = _remove_repeated_furniture(raw_texts)

    pages: list[ParsedPage] = []
    for idx, texte in enumerate(texts, start=1):
        texte = texte.strip()
        table_text = tables_by_page.get(idx, "")
        if table_text:
            texte = f"{texte}\n\n[Tableau]\n{table_text}" if texte else table_text
        if texte:
            pages.append(ParsedPage(numero_page=idx, texte=texte))
    return pages
