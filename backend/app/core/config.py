from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

"""Configuration settings for the Letterfeed application."""


class Settings(BaseSettings):
    """Application settings, loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", env_prefix="LETTERFEED_", frozen=True
    )

    production: bool = Field(
        False,
        validation_alias=AliasChoices("PRODUCTION", "LETTERFEED_PRODUCTION"),
    )

    database_url: str = Field(
        "sqlite:////data/letterfeed.db",
        validation_alias=AliasChoices("DATABASE_URL", "LETTERFEED_DATABASE_URL"),
    )
    app_base_url: str = Field(
        "http://backend:8000",
        validation_alias=AliasChoices("APP_BASE_URL", "LETTERFEED_APP_BASE_URL"),
    )
    imap_server: str = ""
    imap_username: str = ""
    imap_password: str = ""
    search_folder: str = "INBOX"
    move_to_folder: str | None = None
    mark_as_read: bool = False
    email_check_interval: int = 15
    auto_add_new_senders: bool = False
    max_entries_per_feed: int = 0
    auth_username: str | None = None
    auth_password: str | None = None
    secret_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SECRET_KEY", "LETTERFEED_SECRET_KEY"),
    )
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30


settings = Settings()
