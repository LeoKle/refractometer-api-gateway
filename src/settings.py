from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENV: Literal["dev", "prod"] = "dev"

    DB_URL: str = ""

    COOKIE_NAME_ACCESS: str = "refractometer_access"
    COOKIE_NAME_REFRESH: str = "refractometer_refresh"

    @property
    def COOKIES_SECURE(self) -> bool:
        return self.ENV == "prod"

    JWT_SECRET_KEY: SecretStr = SecretStr("supersecret")

    OAUTH_URL: str = ""
    OAUTH_CLIENT_ID: str | None = None
    OAUTH_CLIENT_SECRET: SecretStr = SecretStr("")
    OAUTH_REDIRECT_URL: str = "http://localhost:5173/api/v1/auth/callback"
    OAUTH_SCOPES: str = "openid email"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
