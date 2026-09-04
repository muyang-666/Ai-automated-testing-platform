from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "AI Test Assistant"
    APP_VERSION: str = "0.2.0"
    DATABASE_URL: str = "mysql+pymysql://root:123456@127.0.0.1:3306/ai_test_assistant?charset=utf8mb4"

    LLM_PROVIDER: str = "mock"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_MODEL: str = ""

    # Agent Worker 执行所有权（P05-D）：heartbeat interval 应远小于 stale threshold
    AGENT_HEARTBEAT_INTERVAL_SECONDS: float = 10.0
    AGENT_STALE_THRESHOLD_SECONDS: float = 300.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
