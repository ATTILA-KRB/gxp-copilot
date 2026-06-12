"""Telechargement des PDF publics du corpus (idempotent).

Usage : uv run python -m ingestion.download
"""

from __future__ import annotations

import hashlib
import sys

import httpx

from ingestion.sources import PDF_DIR, SourceDoc, load_sources

_TIMEOUT = httpx.Timeout(60.0)
_HEADERS = {"User-Agent": "gxp-copilot/0.0 (corpus public, usage de demonstration)"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download_one(doc: SourceDoc, client: httpx.Client) -> str:
    """Telecharge un document s'il est absent. Renvoie le sha256 du fichier local."""
    target = doc.local_pdf_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return _sha256(target.read_bytes())

    response = client.get(doc.url_source, headers=_HEADERS, follow_redirects=True)
    response.raise_for_status()
    content = response.content

    content_type = response.headers.get("content-type", "")
    if "pdf" not in content_type.lower() and not content[:5].startswith(b"%PDF"):
        raise ValueError(
            f"{doc.slug}: contenu inattendu (content-type={content_type!r}), PDF non confirme."
        )

    target.write_bytes(content)
    return _sha256(content)


def main() -> int:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    docs = load_sources()
    failures = 0
    with httpx.Client(timeout=_TIMEOUT) as client:
        for doc in docs:
            try:
                digest = download_one(doc, client)
                size_kb = doc.local_pdf_path.stat().st_size // 1024
                print(f"[ok]   {doc.slug}  ({size_kb} Ko, sha256={digest[:12]}...)")
            except Exception as exc:  # noqa: BLE001 - on veut continuer le lot
                failures += 1
                print(f"[FAIL] {doc.slug}: {exc}", file=sys.stderr)
    print(f"\nTermine : {len(docs) - failures}/{len(docs)} documents disponibles.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
