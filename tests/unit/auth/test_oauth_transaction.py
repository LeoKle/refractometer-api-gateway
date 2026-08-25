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


def test_get_safe_redirect_target_on_safe():
    assert get_safe_redirect_target("/dashboard") == "/dashboard"


def test_get_safe_redirect_target_on_malicious():
    assert get_safe_redirect_target("https://malicious.com") == "/"
    assert get_safe_redirect_target("https://malicious.com/test") == "/"
    assert get_safe_redirect_target("//evil.com") == "/"
