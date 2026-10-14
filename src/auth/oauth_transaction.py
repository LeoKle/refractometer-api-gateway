import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from jose import JWTError, jwt
from pydantic import BaseModel, Field

from settings import get_settings

ALGORITHM = "HS256"
TRANSACTION_TYPE = "oauth_transaction"
TRANSACTION_TTL_MINUTES = 10


class OAuthTransaction(BaseModel):
    state: str = Field(..., description="The CSRF state")
    code_verifier: str = Field(..., description="The PKCE code verifier")
    redirect_to: str = Field(..., description="The requested redirect target during login")


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
    """Return redirect_to only if it is a same-origin absolute path, else return "/" """
    if not redirect_to or not isinstance(redirect_to, str):
        return "/"

    # Reject backslashes and control characters
    if "\\" in redirect_to or any(ord(c) < 0x20 or ord(c) == 0x7F for c in redirect_to):
        return "/"

    # Must be an absolute path, and not protocol-relative
    if not redirect_to.startswith("/") or redirect_to.startswith("//"):
        return "/"

    try:
        parsed = urlsplit(redirect_to)
    except ValueError:
        return "/"

    if parsed.scheme or parsed.netloc:
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
