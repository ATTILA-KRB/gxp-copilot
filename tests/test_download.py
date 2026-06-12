"""Tests du telechargement : idempotence et rejet des contenus non-PDF (sans reseau)."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import httpx
import pytest

import ingestion.sources
from ingestion.download import download_one
from ingestion.sources import SourceDoc


@pytest.fixture
def doc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SourceDoc:
    # Redirige PDF_DIR (utilise par SourceDoc.local_pdf_path) vers un dossier temporaire.
    monkeypatch.setattr(ingestion.sources, "PDF_DIR", tmp_path)
    return SourceDoc(
        slug="doc-test",
        titre="Document de test",
        agence="EMA",
        reference=None,
        version=None,
        date_publication=date(2011, 6, 30),
        url_source="https://example.org/doc.pdf",
    )


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_downloads_and_writes_pdf(doc: SourceDoc):
    content = b"%PDF-1.4 contenu factice"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, headers={"content-type": "application/pdf"})

    digest = download_one(doc, _client(handler))
    assert doc.local_pdf_path.read_bytes() == content
    assert digest == hashlib.sha256(content).hexdigest()


def test_existing_file_is_not_redownloaded(doc: SourceDoc):
    content = b"%PDF-1.4 deja present"
    doc.local_pdf_path.write_bytes(content)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("aucun appel reseau attendu pour un fichier deja present")

    digest = download_one(doc, _client(handler))
    assert digest == hashlib.sha256(content).hexdigest()


def test_non_pdf_content_rejected(doc: SourceDoc):
    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"content-type": "text/html"}
        return httpx.Response(200, content=b"<html>404</html>", headers=headers)

    with pytest.raises(ValueError, match="PDF non confirme"):
        download_one(doc, _client(handler))
    assert not doc.local_pdf_path.exists()


def test_http_error_raised(doc: SourceDoc):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    with pytest.raises(httpx.HTTPStatusError):
        download_one(doc, _client(handler))
