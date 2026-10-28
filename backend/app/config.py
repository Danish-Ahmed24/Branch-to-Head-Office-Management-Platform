"""Validated process configuration. Credentials never belong in source control."""

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, hide_input_in_errors=True)

    database_url: SecretStr
    app_env: Literal["development", "test", "production"] = "development"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    static_dir: Path | None = None
    public_origin: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PUBLIC_ORIGIN", "RENDER_EXTERNAL_URL", "public_origin"),
    )
    session_ttl_seconds: int = Field(default=3600, ge=300, le=86400)

    @field_validator("public_origin")
    @classmethod
    def valid_public_origin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cls.validate_origins([value])
        return value

    @model_validator(mode="after")
    def production_origin_required(self):
        if self.app_env == "production" and (
            not self.public_origin or not self.public_origin.startswith("https://")
        ):
            raise ValueError(
                "PUBLIC_ORIGIN or RENDER_EXTERNAL_URL must be an HTTPS origin in production"
            )
        return self

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
        except Exception:
            raise ValueError("DATABASE_URL must be a PostgreSQL connection URL") from None
        if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
            raise ValueError("Only PostgreSQL with psycopg is supported")
        if not url.database or not url.host:
            raise ValueError("DATABASE_URL requires a database and hostname")
        return SecretStr(
            url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
        )

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            if origin == "*" or not origin.startswith(("http://", "https://")):
                raise ValueError("CORS_ORIGINS must contain explicit HTTP(S) origins")
            from urllib.parse import urlsplit

            parsed = urlsplit(origin)
            if (
                not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
            ):
                raise ValueError(
                    "CORS_ORIGINS entries must be origins without paths or credentials"
                )
        return origins
