from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./agent.db"
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5:7b-instruct"
    llm_fallback_model: str = "llama3.2:3b"
    llm_base_url: str = "http://localhost:11434"
    llm_api_key: str | None = None
    ollama_host: str = "http://localhost:11434"
    timezone: str = "UTC"
    whisper_model: str = "base.en"
    piper_model: str = ""
    rate_limit_per_minute: int = 120
    credentials_key: str = ""
    grace_minutes: int = 10
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_sender: str = "agent@localhost"
    smtp_console: bool = True
    dev_mode: bool = True
    version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
