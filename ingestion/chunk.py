"""Chunking structurel par paragraphe avec budget de tokens et recouvrement.

Conserve le numero de page (citation) et detecte la section/article
(ex. "3.1", "Annex 11", "Chapter 4") pour enrichir les metadonnees.

La section d'un chunk est celle en vigueur a son PREMIER paragraphe (pas la
derniere vue), et les en-tetes sont cherches sur toutes les lignes d'un
paragraphe : les PDF reglementaires posent souvent le numero seul sur sa
ligne ("4.", puis "Validation" en dessous).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import tiktoken

from ingestion.parse import ParsedPage

_ENCODING = tiktoken.get_encoding("cl100k_base")
_TARGET_TOKENS = 450
_OVERLAP_TOKENS = 60

# En-tete numerote en debut de ligne suivi d'un titre : "3.1 Access control".
# Premier composant limite a 2 chiffres pour eviter annees et references.
_INLINE_HEADING_RE = re.compile(r"^(?P<num>\d{1,2}(?:\.\d{1,3})*)\.?\s+\S")
# Numero seul sur sa ligne : "4.", "4.1", "12.4" (style EU GMP Annexe 11).
_LONE_NUMBER_RE = re.compile(r"^(?P<num>\d{1,2}(?:\.\d{1,3})*)\.?\s*$")
# Mot-cle structurel, avec son numero si present : "Annex 11", "Chapter 4".
_KEYWORD_RE = re.compile(
    r"^(?P<kw>Annex|Chapter|Appendix|Section)(?:\s+(?P<ref>\d+[A-Za-z]?))?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Chunk:
    texte: str
    numero_page: int
    section: str | None
    ordre: int


def _count(text: str) -> int:
    return len(_ENCODING.encode(text))


def _heading_label(line: str) -> str | None:
    """Etiquette de section si la ligne est un en-tete, sinon None."""
    match = _KEYWORD_RE.match(line)
    if match:
        kw, ref = match.group("kw"), match.group("ref")
        return f"{kw} {ref}" if ref else kw
    match = _LONE_NUMBER_RE.match(line) or _INLINE_HEADING_RE.match(line)
    if match:
        return match.group("num")
    return None


def _headings_in(paragraph: str) -> list[tuple[int, str]]:
    """Tous les en-tetes du paragraphe : (index de ligne, etiquette)."""
    found: list[tuple[int, str]] = []
    for idx, raw_line in enumerate(paragraph.splitlines()):
        label = _heading_label(raw_line.strip())
        if label:
            found.append((idx, label))
    return found


def _split_oversized(text: str) -> list[str]:
    """Coupe un paragraphe plus long que le budget en fenetres de tokens."""
    tokens = _ENCODING.encode(text)
    if len(tokens) <= _TARGET_TOKENS:
        return [text]
    pieces: list[str] = []
    for start in range(0, len(tokens), _TARGET_TOKENS):
        window = tokens[start : start + _TARGET_TOKENS]
        pieces.append(_ENCODING.decode(window))
    return pieces


def chunk_pages(pages: list[ParsedPage]) -> list[Chunk]:
    # Unites elementaires : (numero_page, paragraphe, section en vigueur a son debut).
    units: list[tuple[int, str, str | None]] = []
    current_section: str | None = None
    for page in pages:
        for raw_para in re.split(r"\n\s*\n", page.texte):
            para = raw_para.strip()
            if not para:
                continue
            headings = _headings_in(para)
            # Si le paragraphe COMMENCE par un en-tete, il ouvre cette section ;
            # sinon il appartient a la section deja en vigueur.
            starts_with_heading = bool(headings) and headings[0][0] == 0
            section_at_start = headings[0][1] if starts_with_heading else current_section
            if headings:
                current_section = headings[-1][1]
            for piece in _split_oversized(para):
                units.append((page.numero_page, piece, section_at_start))

    chunks: list[Chunk] = []
    current: list[tuple[int, str, str | None]] = []
    current_tokens = 0
    ordre = 0

    def flush() -> None:
        nonlocal ordre, current, current_tokens
        if not current:
            return
        texte = "\n\n".join(text for _, text, _ in current)
        chunks.append(
            Chunk(
                texte=texte,
                numero_page=current[0][0],
                section=current[0][2],  # section en vigueur au DEBUT du chunk
                ordre=ordre,
            )
        )
        ordre += 1

    for unit in units:
        para_tokens = _count(unit[1])
        if current and current_tokens + para_tokens > _TARGET_TOKENS:
            flush()
            # Recouvrement : on reinjecte la fin du chunk precedent.
            kept: list[tuple[int, str, str | None]] = []
            kept_tokens = 0
            for prev_unit in reversed(current):
                t = _count(prev_unit[1])
                if kept_tokens + t > _OVERLAP_TOKENS:
                    break
                kept.insert(0, prev_unit)
                kept_tokens += t
            current = kept
            current_tokens = kept_tokens

        current.append(unit)
        current_tokens += para_tokens

    flush()
    return chunks
