from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    JWT_SECRET_KEY: SecretStr = SecretStr("supersecret")

    OAUTH_URL: str = ""
    OAUTH_CLIENT_ID: str | None = None
    OAUTH_CLIENT_SECRET: SecretStr = SecretStr("")
    OAUTH_REDIRECT_URL: str = "http://localhost:5173/api/v1/auth/callback"
    OAUTH_SCOPES: str = "openid email"
