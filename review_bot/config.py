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

    # OpenAI
    openai_api_key: str = ""

    # 리뷰 설정
    review_provider: str = "claude"  # "claude" 또는 "openai"
    review_model: str = "claude-sonnet-4-20250514"
    openai_review_model: str = "gpt-4o"
    max_hunks_per_file: int = 20
    max_files_per_mr: int = 30
    log_level: str = "INFO"

    @property
    def active_model(self) -> str:
        """현재 프로바이더에 맞는 모델명을 반환한다."""
        if self.review_provider == "openai":
            return self.openai_review_model
        return self.review_model


# 싱글턴 인스턴스
settings = Settings()
