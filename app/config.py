from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    telegram_webhook_secret: str = Field(alias="TELEGRAM_WEBHOOK_SECRET")
    tasks_secret: str | None = Field(default=None, alias="TASKS_SECRET")
    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    google_service_account_json: str | None = Field(default=None, alias="GOOGLE_SERVICE_ACCOUNT_JSON")
    spreadsheet_id: str = Field(alias="SPREADSHEET_ID")

    konstantin_telegram_id: int = Field(alias="KONSTANTIN_TELEGRAM_ID")
    svitlana_telegram_id: int = Field(alias="SVITLANA_TELEGRAM_ID")

    openai_parse_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_PARSE_MODEL")
    openai_vision_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_VISION_MODEL")
    openai_transcribe_model: str = Field(default="gpt-4o-mini-transcribe", alias="OPENAI_TRANSCRIBE_MODEL")
    default_account_konstantin: str = Field(default="Family Card", alias="DEFAULT_ACCOUNT_KONSTANTIN")
    default_account_svitlana: str = Field(default="Svitlana Card", alias="DEFAULT_ACCOUNT_SVITLANA")
    timezone: str = Field(default="Europe/Warsaw", alias="TIMEZONE")


@lru_cache
def get_settings() -> Settings:
    return Settings()
