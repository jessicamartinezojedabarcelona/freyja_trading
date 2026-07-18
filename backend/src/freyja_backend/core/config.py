from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FREYJA_", frozen=True)

    app_name: str = "Freyja 2.0 Backend"
    app_version: str = "0.1.0"
    environment: Environment = "development"
    api_v1_prefix: str = "/api/v1"


def get_settings() -> Settings:
    return Settings()
