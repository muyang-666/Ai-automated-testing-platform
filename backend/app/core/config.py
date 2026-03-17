from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "AI Test Assistant"
    APP_VERSION: str = "0.2.0"
    DATABASE_URL: str = "sqlite:///./ai_test_assistant.db"

    LLM_PROVIDER: str = "mock"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_MODEL: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()