"""Tests de la configuration : valeurs par defaut et URL de connexion."""

from __future__ import annotations

from app.config import Settings


def _isolated_settings(**overrides) -> Settings:
    """Settings sans lecture du .env (reproductible quel que soit l'environnement)."""
    return Settings(_env_file=None, **overrides)


def test_defaults():
    settings = _isolated_settings()
    assert settings.provider == "cloud"
    assert settings.embedding_dim == 1024  # doit correspondre a vector(1024) du schema SQL


def test_database_url_composition():
    settings = _isolated_settings(
        postgres_host="db.example",
        postgres_port=5433,
        postgres_db="gxp",
        postgres_user="alice",
        postgres_password="secret",
    )
    assert settings.database_url == "postgresql://alice:secret@db.example:5433/gxp"


def test_provider_rejects_unknown_value():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _isolated_settings(provider="azure")
