from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    api_key: str
    log_level: str = "INFO"

    database_url: str
    redis_url: str

    supabase_url: str
    supabase_service_key: str
    supabase_storage_bucket: str = "resumes"

    azure_di_endpoint: str
    azure_di_key: str

    gemini_api_key: str
    groq_api_key: str
    hf_api_token: str
    openai_api_key: str

    azure_openai_endpoint: str | None = None
    azure_openai_key: str | None = None
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    azure_openai_api_version: str = "2024-02-01"

    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536


settings = Settings()
