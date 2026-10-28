import os

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


def settings(**overrides):
    return Settings(
        database_url="postgresql://fake:never-expose-me@127.0.0.1:1/unreachable",
        app_env="test",
        **overrides,
    )


def test_unavailable_database_returns_503_without_credentials():
    with TestClient(create_app(settings())) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}
    assert response.headers["cache-control"] == "no-store"
    assert "never-expose-me" not in response.text


def test_cors_allows_only_configured_origin():
    with TestClient(create_app(settings(cors_origins=["https://example.org"]))) as client:
        allowed = client.options(
            "/health",
            headers={"Origin": "https://example.org", "Access-Control-Request-Method": "GET"},
        )
        forbidden = client.options(
            "/health",
            headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "GET"},
        )
    assert allowed.headers["access-control-allow-origin"] == "https://example.org"
    assert forbidden.status_code == 400
    assert "access-control-allow-origin" not in forbidden.headers


@pytest.mark.parametrize("url", ["sqlite:///test.db", "postgresql:///missing-host", "invalid"])
def test_invalid_database_configuration_is_rejected(url):
    with pytest.raises(ValidationError):
        Settings(database_url=url)


@pytest.mark.parametrize("origin", ["*", "https://example.org/path", "ftp://example.org"])
def test_unsafe_cors_configuration_is_rejected(origin):
    with pytest.raises(ValidationError):
        settings(cors_origins=[origin])


def test_render_postgres_url_uses_psycopg():
    config = Settings(database_url="postgres://user:password@example.org/database")
    assert config.database_url.get_secret_value().startswith("postgresql+psycopg://")
    assert "password" not in repr(config)


def test_production_hides_api_documentation():
    config = Settings(
        database_url="postgresql://user:password@localhost/database",
        app_env="production",
        public_origin="https://example.org",
    )
    with TestClient(create_app(config)) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_frontend_assets_do_not_override_health_or_unknown_api_routes(tmp_path):
    (tmp_path / "index.html").write_text("<html><body>ShipLens</body></html>")
    (tmp_path / "site.css").write_text("body { color: green; }")
    with TestClient(create_app(settings(static_dir=tmp_path))) as client:
        assert client.get("/").text == "<html><body>ShipLens</body></html>"
        assert client.get("/site.css").status_code == 200
        assert client.get("/health").status_code == 503
        assert client.get("/api/health").status_code == 503
        assert client.get("/api/does-not-exist").status_code == 404
        assert client.get("/../config.py").status_code == 404


def test_missing_static_directory_fails_startup(tmp_path):
    with pytest.raises(RuntimeError, match="does not exist"):
        create_app(settings(static_dir=tmp_path / "absent"))


@pytest.mark.integration
def test_health_executes_real_postgresql_query():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration check")
    config = Settings(database_url=database_url, app_env="test")
    with TestClient(create_app(config)) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
