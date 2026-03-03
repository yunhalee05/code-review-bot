from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # GitLab
    gitlab_url: str = "https://gitlab.com"
    gitlab_token: str
    gitlab_project_id: int

    # Anthropic
    anthropic_api_key: str

    # OpenAI (Phase 3 - optional)
    openai_api_key: str = ""

    # 리뷰 설정
    max_hunks_per_file: int = 20
    max_files_per_mr: int = 30
    review_model: str = "claude-sonnet-4-20250514"
    log_level: str = "INFO"


# 싱글턴 인스턴스
settings = Settings()