from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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

    REDIS_URL: str

    COOKIE_NAME_ACCESS: str = "refractometer_access"
    COOKIE_NAME_REFRESH: str = "refractometer_refresh"
    COOKIE_NAME_OAUTH_TRANSACTION: str = "refractometer_oauth"

    @property
    def COOKIES_SECURE(self) -> bool:
        return EnvType.prod == self.ENV

    JWT_ALGORITHM: Literal["HS256", "EdDSA"]
    JWT_PRIVATE_KEY: SecretStr = Field(description="PEM private key, used to sign tokens")
    JWT_PUBLIC_KEY: str = Field(
        description="PEM public key, used to verify tokens.",
    )

    @model_validator(mode="after")
    def _check_key_material(self):
        if self.JWT_ALGORITHM == "HS256":
            if self.JWT_PRIVATE_KEY.get_secret_value() != self.JWT_PUBLIC_KEY:
                msg = "HS256 requires JWT_PUBLIC_KEY to equal JWT_PRIVATE_KEY"
                raise ValueError(msg)
            if EnvType.prod == self.ENV:
                msg_0 = "HS256 is not allowed in prod, use EdDSA"
                raise ValueError(msg_0)
        return self

    JWT_ISSUER: str
    JWT_AUDIENCE: str
    JWT_ACCESS_TOKEN_TTL: int = Field(default=10, description="TTL in minutes")
    JWT_REFRESH_TOKEN_TTL: int = Field(default=30, description="TTL in days")

    OAUTH_URL: str
    OAUTH_CLIENT_ID: str
    OAUTH_CLIENT_SECRET: SecretStr
    OAUTH_REDIRECT_URL: str
    OAUTH_SCOPES: str = "openid email"

    IMAGE_CLIENT_URL: str
    IMAGE_CLIENT_TIMEOUT: float = 2.0

    RESULT_CLIENT_URL: str
    RESULT_CLIENT_TIMEOUT: float = 2.0

    QUEUE_CLIENT_URL: str
    QUEUE_CLIENT_TIMEOUT: float = 2.0

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


class TestSettings(BaseSettings):
    ENV: EnvType = EnvType.test

    DB_URL: str = ""
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_ALGORITHM: Literal["HS256", "EdDSA"] = "HS256"
    JWT_PRIVATE_KEY: SecretStr = SecretStr("supersecret")
    JWT_PUBLIC_KEY: str = "supersecret"
    JWT_ISSUER: str = "gateway-refractometer"
    JWT_AUDIENCE: str = "api-refractometer"

    OAUTH_URL: str = ""
    OAUTH_CLIENT_ID: str = ""
    OAUTH_CLIENT_SECRET: SecretStr = SecretStr("")
    OAUTH_REDIRECT_URL: str = ""

    IMAGE_CLIENT_URL: str = ""
    RESULT_CLIENT_URL: str = ""
    QUEUE_CLIENT_URL: str = ""


class DevSettings(BaseSettings):
    ENV: EnvType = EnvType.dev

    DB_URL: str = "postgresql://refractometer:password@localhost:5432/refractometer-api-gateway"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_ALGORITHM: Literal["HS256", "EdDSA"] = "HS256"
    JWT_PRIVATE_KEY: SecretStr = SecretStr("supersecret")
    JWT_PUBLIC_KEY: str = "supersecret"
    JWT_ISSUER: str = "gateway-refractometer"
    JWT_AUDIENCE: str = "api-refractometer"

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


class _EnvSelector(PydanticBaseSettings):
    ENV: EnvType = EnvType.prod

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


@lru_cache
def get_settings() -> BaseSettings:
    app_env = _EnvSelector().ENV
    return settings_mapping[app_env]()
