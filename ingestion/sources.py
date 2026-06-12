"""Chargement et validation du registre des sources (sources.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

# Racines de chemins, relatives au depot.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = Path(__file__).resolve().parent / "sources.yaml"
PDF_DIR = PROJECT_ROOT / "data" / "pdf"

_ALLOWED_AGENCIES = {"MHRA", "FDA", "PICS", "WHO", "EU", "EMA", "ANSM", "ICH"}


@dataclass(frozen=True)
class SourceDoc:
    slug: str
    titre: str
    agence: str
    reference: str | None
    version: str | None
    date_publication: date | None
    url_source: str

    @property
    def local_pdf_path(self) -> Path:
        return PDF_DIR / f"{self.slug}.pdf"


def _parse_date(value: object) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value))


def load_sources(path: Path = SOURCES_FILE) -> list[SourceDoc]:
    """Lit sources.yaml, valide les champs essentiels, renvoie la liste typee."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries = raw.get("documents", []) if isinstance(raw, dict) else []
    if not entries:
        raise ValueError(f"Aucun document dans {path}")

    docs: list[SourceDoc] = []
    seen_slugs: set[str] = set()
    for entry in entries:
        slug = entry["slug"]
        if slug in seen_slugs:
            raise ValueError(f"slug en double : {slug!r}")
        seen_slugs.add(slug)

        agence = entry["agence"]
        if agence not in _ALLOWED_AGENCIES:
            raise ValueError(f"Agence invalide {agence!r} pour {slug!r}")

        docs.append(
            SourceDoc(
                slug=slug,
                titre=entry["titre"],
                agence=agence,
                reference=entry.get("reference"),
                version=str(entry["version"]) if entry.get("version") else None,
                date_publication=_parse_date(entry.get("date_publication")),
                url_source=entry["url_source"],
            )
        )
    return docs
