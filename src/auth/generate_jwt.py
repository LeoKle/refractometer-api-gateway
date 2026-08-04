from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from settings import settings
from users.user import User

ALGORITHM = "HS256"


def create_access_token(user: User, validity_minutes: int = 10) -> str:
    return jwt.encode(
        {
            "user_id": str(user.id),
            "exp": datetime.now(UTC) + timedelta(minutes=validity_minutes),
            "type": "access",
        },
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=ALGORITHM,
    )


def create_refresh_token(user: User, validity_minutes: int = 31 * 24 * 60) -> str:
    return jwt.encode(
        {
            "user_id": str(user.id),
            "exp": datetime.now(UTC) + timedelta(minutes=validity_minutes),
            "type": "refresh",
        },
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=ALGORITHM,
    )


def decode_token(token: str, expected_type: str | None = None) -> dict:
    payload = jwt.decode(token, settings.JWT_SECRET_KEY.get_secret_value(), algorithms=[ALGORITHM])
    if expected_type and payload.get("type") != expected_type:
        msg = f"expected token type {expected_type!r}, got {payload.get('type')!r}"
        raise JWTError(msg)
    return payload
