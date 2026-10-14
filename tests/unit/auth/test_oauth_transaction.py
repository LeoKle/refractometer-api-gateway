import pytest

from auth.oauth_transaction import (
    _code_challenge_from_verifier,
    _generate_code_verifier,
    get_safe_redirect_target,
)


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
