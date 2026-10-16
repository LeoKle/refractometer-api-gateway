from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import jwt
from jwt import PyJWTError
from pydantic import BaseModel, ValidationError

from settings import get_settings

ALGORITHM = "HS256"


class InvalidTokenError(Exception): ...


TokenType = Literal["access", "refresh"]


class JsonWebToken(BaseModel):
    iss: str
    sub: UUID
    aud: str
    iat: int
    exp: int
    token_type: TokenType

    def encode(self) -> str:
        settings = get_settings()

        return jwt.encode(
            self.model_dump(mode="json"),  # mode="json" to ensure sub gets cast to str
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithm=ALGORITHM,
        )

    @classmethod
    def decode(cls, token: str) -> "JsonWebToken":
        settings = get_settings()

        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY.get_secret_value(),
                algorithms=[ALGORITHM],
                audience=settings.JWT_AUDIENCE,
            )

            return cls(**payload)
        except (ValidationError, PyJWTError) as err:
            raise InvalidTokenError() from err

    @classmethod
    def create(
        cls,
        user_id: UUID,
        token_type: TokenType,
        expires_in: timedelta,
    ) -> "JsonWebToken":
        settings = get_settings()
        now = datetime.now(UTC)

        return cls(
            iss=settings.JWT_ISSUER,
            sub=user_id,
            aud=settings.JWT_AUDIENCE,
            iat=int(now.timestamp()),
            exp=int((now + expires_in).timestamp()),
            token_type=token_type,
        )

    @classmethod
    def access(cls, user_id: UUID) -> "JsonWebToken":
        settings = get_settings()

        return cls.create(
            user_id=user_id,
            token_type="access",
            expires_in=timedelta(minutes=settings.JWT_ACCESS_TOKEN_TTL),
        )

    @classmethod
    def refresh(cls, user_id: UUID) -> "JsonWebToken":
        settings = get_settings()

        return cls.create(
            user_id=user_id,
            token_type="refresh",
            expires_in=timedelta(days=settings.JWT_REFRESH_TOKEN_TTL),
        )
