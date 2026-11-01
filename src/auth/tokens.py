from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import jwt
from jwt import PyJWTError
from pydantic import BaseModel, ValidationError

from settings import get_settings

REQUIRED_CLAIMS = ["iss", "sub", "aud", "iat", "exp", "jti", "fid"]


class InvalidTokenError(Exception): ...


TokenType = Literal["access", "refresh"]


class JsonWebToken(BaseModel):
    iss: str
    sub: UUID
    aud: str
    iat: int
    exp: int
    jti: UUID  # unique per token
    fid: UUID  # session family: shared by every token descended from one login
    token_type: TokenType

    def encode(self) -> str:
        settings = get_settings()

        return jwt.encode(
            # mode="json" to ensure sub, jti and fid get cast to str
            self.model_dump(mode="json"),
            settings.JWT_PRIVATE_KEY.get_secret_value(),
            algorithm=settings.JWT_ALGORITHM,
        )

    @classmethod
    def decode(cls, token: str, expected_type: TokenType) -> "JsonWebToken":
        settings = get_settings()

        try:
            payload = jwt.decode(
                token,
                settings.JWT_PUBLIC_KEY,
                algorithms=[settings.JWT_ALGORITHM],
                audience=settings.JWT_AUDIENCE,
                issuer=settings.JWT_ISSUER,
                options={"require": REQUIRED_CLAIMS},
            )

            decoded = cls(**payload)
        except (ValidationError, PyJWTError) as err:
            raise InvalidTokenError() from err

        if decoded.token_type != expected_type:
            raise InvalidTokenError()

        return decoded

    @classmethod
    def create(
        cls,
        user_id: UUID,
        token_type: TokenType,
        expires_in: timedelta,
        family_id: UUID | None = None,
    ) -> "JsonWebToken":
        """`family_id=None` starts a new family (login). Pass the existing
        family's id when rotating, so the whole chain shares one fid."""
        settings = get_settings()
        now = datetime.now(UTC)

        return cls(
            iss=settings.JWT_ISSUER,
            sub=user_id,
            aud=settings.JWT_AUDIENCE,
            iat=int(now.timestamp()),
            exp=int((now + expires_in).timestamp()),
            jti=uuid4(),
            fid=family_id or uuid4(),
            token_type=token_type,
        )

    @classmethod
    def access(cls, user_id: UUID, family_id: UUID | None = None) -> "JsonWebToken":
        settings = get_settings()

        return cls.create(
            user_id=user_id,
            token_type="access",
            expires_in=timedelta(minutes=settings.JWT_ACCESS_TOKEN_TTL),
            family_id=family_id,
        )

    @classmethod
    def refresh(cls, user_id: UUID, family_id: UUID | None = None) -> "JsonWebToken":
        settings = get_settings()

        return cls.create(
            user_id=user_id,
            token_type="refresh",
            expires_in=timedelta(days=settings.JWT_REFRESH_TOKEN_TTL),
            family_id=family_id,
        )
