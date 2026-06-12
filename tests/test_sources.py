"""Tests du registre des sources : le sources.yaml reel et les regles de validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.sources import load_sources


def _write_yaml(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "sources.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_real_registry_is_valid():
    docs = load_sources()
    assert docs, "le registre reel doit contenir au moins un document"
    assert all(doc.url_source.startswith("https://") for doc in docs)
    slugs = [doc.slug for doc in docs]
    assert len(slugs) == len(set(slugs))


def test_local_pdf_path_uses_slug():
    doc = load_sources()[0]
    assert doc.local_pdf_path.name == f"{doc.slug}.pdf"


def test_duplicate_slug_rejected(tmp_path: Path):
    path = _write_yaml(
        tmp_path,
        """
documents:
  - {slug: a, titre: T, agence: FDA, url_source: "https://x"}
  - {slug: a, titre: T2, agence: MHRA, url_source: "https://y"}
""",
    )
    with pytest.raises(ValueError, match="slug en double"):
        load_sources(path)


def test_unknown_agency_rejected(tmp_path: Path):
    path = _write_yaml(
        tmp_path,
        """
documents:
  - {slug: a, titre: T, agence: NASA, url_source: "https://x"}
""",
    )
    with pytest.raises(ValueError, match="Agence invalide"):
        load_sources(path)


def test_empty_registry_rejected(tmp_path: Path):
    path = _write_yaml(tmp_path, "documents: []\n")
    with pytest.raises(ValueError, match="Aucun document"):
        load_sources(path)


def test_date_publication_parsed(tmp_path: Path):
    path = _write_yaml(
        tmp_path,
        """
documents:
  - slug: a
    titre: T
    agence: EMA
    date_publication: "2011-06-30"
    url_source: "https://x"
""",
    )
    doc = load_sources(path)[0]
    assert doc.date_publication is not None
    assert doc.date_publication.isoformat() == "2011-06-30"
