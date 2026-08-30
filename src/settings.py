from enum import StrEnum
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings as PydanticBaseSettings
from pydantic_settings import SettingsConfigDict


class EnvType(StrEnum):
    test: str = "test"
    dev: str = "dev"
    prod: str = "prod"


class BaseSettings(PydanticBaseSettings):
    ENV: EnvType = EnvType.prod

    DB_URL: str
    DB_ECHO: bool = False

    COOKIE_NAME_ACCESS: str = "refractometer_access"
    COOKIE_NAME_REFRESH: str = "refractometer_refresh"
    COOKIE_NAME_OAUTH_TRANSACTION: str = "refractometer_oauth"

    @property
    def COOKIES_SECURE(self) -> bool:
        return EnvType.prod == self.ENV

    JWT_SECRET_KEY: SecretStr = SecretStr("supersecret")

    OAUTH_URL: str
    OAUTH_CLIENT_ID: str
    OAUTH_CLIENT_SECRET: SecretStr
    OAUTH_REDIRECT_URL: str
    OAUTH_SCOPES: str = "openid email"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


class TestSettings(BaseSettings):
    ENV: EnvType = EnvType.test
    DB_URL: str = ""

    JWT_SECRET_KEY: SecretStr = SecretStr("supersecret")

    OAUTH_URL: str = ""
    OAUTH_CLIENT_ID: str = ""
    OAUTH_CLIENT_SECRET: SecretStr = SecretStr("")
    OAUTH_REDIRECT_URL: str = ""


class DevSettings(BaseSettings):
    ENV: EnvType = EnvType.dev
    DB_URL: str = "postgresql://refractometer:password@localhost:5432/refractometer-api-gateway"

    JWT_SECRET_KEY: SecretStr = SecretStr("supersecret")

    OAUTH_URL: str = ""
    OAUTH_CLIENT_ID: str = ""
    OAUTH_CLIENT_SECRET: SecretStr = SecretStr("")
    OAUTH_REDIRECT_URL: str = "http://localhost:5173/api/v1/auth/callback"


class ProdSettings(BaseSettings):
    ENV: EnvType = EnvType.prod


settings_mapping = {
    EnvType.dev: DevSettings,
    EnvType.test: TestSettings,
    EnvType.prod: ProdSettings,
}


@lru_cache
def get_settings() -> BaseSettings:
    app_env = BaseSettings().ENV
    return settings_mapping[app_env]()
