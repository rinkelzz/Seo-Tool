"""Anwendungseinstellungen, geladen aus Umgebungsvariablen."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: str = Field(default="development")
    app_log_level: str = Field(default="INFO")
    app_api_token: str = Field(default="change-me")

    # Database / Redis
    database_url: str = Field(default="postgresql+psycopg://seo:seo@localhost:5433/seo")
    redis_url: str = Field(default="redis://localhost:6380/0")

    # Crawler
    crawler_user_agent: str = Field(default="SeoToolBot/0.1 (+https://example.local/bot)")
    crawler_max_concurrency: int = Field(default=8)
    crawler_timeout_seconds: int = Field(default=15)
    crawler_respect_robots: bool = Field(default=True)

    # Tippfehler-Check via LanguageTool (Phase 4B). Opt-in — der LT-Container
    # ist mit ~2 GB Image/~600 MB RAM nicht ohne, deshalb default off. Wenn
    # enabled, fragt der Worker nach dem Hauptcrawl je Page einmal die LT-API.
    languagetool_url: str = Field(default="http://localhost:8010")
    crawler_spellcheck_enabled: bool = Field(default=False)
    crawler_spellcheck_max_chars: int = Field(default=8000)
    crawler_spellcheck_min_errors: int = Field(default=5)
    crawler_spellcheck_timeout_seconds: int = Field(default=20)


@lru_cache
def get_settings() -> Settings:
    return Settings()
