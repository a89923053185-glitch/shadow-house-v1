from __future__ import annotations

from functools import lru_cache
from typing import List, Optional, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Shadow House API"
    app_version: str = "1.0.0"

    database_url: str = Field(
        default="postgresql+psycopg://shadow_user:shadow_password@localhost:5432/shadow_house",
        alias="DATABASE_URL",
    )

    backend_host: str = Field(default="0.0.0.0", alias="BACKEND_HOST")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")
    backend_cors_origins: Union[List[str], str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        alias="BACKEND_CORS_ORIGINS",
    )

    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.2", alias="OPENAI_MODEL")
    openai_enabled: bool = Field(default=False, alias="OPENAI_ENABLED")
    otp_provider: str = Field(default="dev", alias="OTP_PROVIDER")
    otp_code_ttl_seconds: int = Field(default=300, alias="OTP_CODE_TTL_SECONDS")
    otp_max_attempts: int = Field(default=5, alias="OTP_MAX_ATTEMPTS")
    otp_dev_mode: bool = Field(default=True, alias="OTP_DEV_MODE")
    otp_dev_fixed_code: Optional[str] = Field(default=None, alias="OTP_DEV_FIXED_CODE")
    otp_secret_key: str = Field(default="shadow-house-dev-otp-secret", alias="OTP_SECRET_KEY")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: Union[str, List[str]]):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
