from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import SecretStr

from auth.oauth_transaction import (
    TRANSACTION_TYPE,
    InvalidTransactionError,
    OAuthTransaction,
    _code_challenge_from_verifier,
    _generate_code_verifier,
    decode_transaction,
    encode_transaction,
    get_safe_redirect_target,
)
from settings import get_settings


def test_generate_code_verifier():
    code_verifier = _generate_code_verifier()

    # check RFC7636 compliance
    assert len(code_verifier) >= 43
    assert len(code_verifier) <= 128


def test_code_challenge_from_verifier():
    code_verifier = "code_verifier"
    code_challenge = _code_challenge_from_verifier(code_verifier)

    assert code_verifier != code_challenge


@pytest.mark.parametrize(
    "bad",
    [
        "https://evil.com",
        "//evil.com",
        "/\\evil.com",
        "\\\\evil.com",
        "\\/evil.com",
        " //evil.com",
        "/\t/evil.com",
        "javascript:alert(1)",
        "evil.com",
        "http:evil.com",
        "/ok\r\nSet-Cookie: x=y",
        "http://[bad",
        None,
        "",
    ],
)
def test_rejects(bad):
    assert get_safe_redirect_target(bad) == "/"


@pytest.mark.parametrize("good", ["/", "/dashboard", "/a/b?x=1#frag"])
def test_accepts(good):
    assert get_safe_redirect_target(good) == good


TEST_KEY = "test-secret-that-is-at-least-64-bytes-long-so-pyjwt-does-not-throw-warnings"


@pytest.fixture
def hs256_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(settings, "JWT_PRIVATE_KEY", SecretStr(TEST_KEY))
    monkeypatch.setattr(settings, "JWT_PUBLIC_KEY", TEST_KEY)


def _valid_payload(**overrides) -> dict:
    return {
        "state": "s",
        "code_verifier": "v",
        "redirect_to": "/",
        "type": TRANSACTION_TYPE,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        **overrides,
    }


def _without(key: str) -> dict:
    return {k: v for k, v in _valid_payload().items() if k != key}


@pytest.mark.usefixtures("hs256_settings")
class TestDecodeTransaction:
    def test_roundtrip(self):
        transaction = OAuthTransaction(state="s", code_verifier="v", redirect_to="/x")

        assert decode_transaction(encode_transaction(transaction)) == transaction

    def test_garbage(self):
        with pytest.raises(InvalidTransactionError):
            decode_transaction("not.a.jwt")

    def test_signed_with_another_key(self):
        token = jwt.encode(_valid_payload(), "x" * 64, algorithm="HS256")

        with pytest.raises(InvalidTransactionError):
            decode_transaction(token)

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param(lambda: _valid_payload(type="refresh"), id="wrong-type"),
            pytest.param(lambda: _without("state"), id="missing-field"),
            pytest.param(lambda: _valid_payload(state=123), id="malformed-field"),
            pytest.param(lambda: _without("exp"), id="no-expiry"),
            pytest.param(
                lambda: _valid_payload(exp=datetime.now(UTC) - timedelta(seconds=1)),
                id="expired",
            ),
        ],
    )
    def test_rejects_validly_signed(self, payload):
        token = jwt.encode(payload(), TEST_KEY, algorithm="HS256")

        with pytest.raises(InvalidTransactionError):
            decode_transaction(token)
