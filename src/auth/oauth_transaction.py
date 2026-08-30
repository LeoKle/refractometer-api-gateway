import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from jose import JWTError, jwt
from pydantic import BaseModel

from settings import get_settings

ALGORITHM = "HS256"
TRANSACTION_TYPE = "oauth_transaction"
TRANSACTION_TTL_MINUTES = 10


class OAuthTransaction(BaseModel):
    state: str
    code_verifier: str
    redirect_to: str


class PKCECodeChallenge(BaseModel):
    code_challenge: str
    code_challenge_method: str


def _generate_code_verifier() -> str:
    """RFC 7636: create a 43-128 character string"""
    return secrets.token_urlsafe(64)


def _code_challenge_from_verifier(code_verifier: str) -> str:
    """RFC 7636: code_challenge = BASE64URL-ENOCDE(SHA256(ASCII(code_verifier)))"""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def get_safe_redirect_target(redirect_to: str | None) -> str:
    """Ensure requested redirect target is safe."""
    if not redirect_to:
        return "/"

    parsed = urlparse(redirect_to)

    if parsed.scheme or parsed.netloc or redirect_to.startswith("//"):
        return "/"

    return redirect_to


def create_transaction(redirect_to: str | None) -> tuple[OAuthTransaction, PKCECodeChallenge]:
    code_verifier = _generate_code_verifier()
    transaction = OAuthTransaction(
        state=secrets.token_urlsafe(32),
        code_verifier=code_verifier,
        redirect_to=get_safe_redirect_target(redirect_to),
    )
    return transaction, PKCECodeChallenge(
        code_challenge=_code_challenge_from_verifier(code_verifier),
        code_challenge_method="S256",
    )


def encode_transaction(transaction: OAuthTransaction) -> str:
    return jwt.encode(
        {
            **transaction.model_dump(),
            "exp": datetime.now(UTC) + timedelta(minutes=TRANSACTION_TTL_MINUTES),
            "type": TRANSACTION_TYPE,
        },
        get_settings().JWT_SECRET_KEY.get_secret_value(),
        algorithm=ALGORITHM,
    )


def decode_transaction(token: str) -> OAuthTransaction | None:
    try:
        payload = jwt.decode(
            token, get_settings().JWT_SECRET_KEY.get_secret_value(), algorithms=[ALGORITHM]
        )
    except JWTError:
        return None

    if payload.get("type") != TRANSACTION_TYPE:
        return None

    try:
        return OAuthTransaction(
            state=payload["state"],
            code_verifier=payload["code_verifier"],
            redirect_to=payload["redirect_to"],
        )
    except KeyError:
        return None
