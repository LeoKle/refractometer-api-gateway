"""Attacks on the authorization-code flow: CSRF / login CSRF, code interception
(PKCE), code replay, forged or tampered transactions and open redirects.

Every rejected callback must:
* answer 400 without a session,
* not create a user, and
* (where the gateway can tell before talking to GitHub) not redeem the code.
"""

import base64
import json
import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from auth.oauth_transaction import decode_transaction
from auth.tokens import JsonWebToken
from tests.integration.auth.conftest import (
    CALLBACK,
    USER,
    callback,
    cookie_names,
    login,
    plant_cookie,
    plant_transaction,
    query,
    set_cookie_headers,
    start_login,
)
from tests.integration.auth.fake_github import GitHubAccount
from users.user import User

pytestmark = pytest.mark.integration


def assert_rejected_without_session(response, user_repo, *emails: str) -> None:
    access_name, refresh_name, _ = cookie_names()
    assert response.status_code == 400, response.text
    headers = set_cookie_headers(response)
    assert access_name not in headers
    assert refresh_name not in headers
    for email in emails:
        assert user_repo.get_by_email(email) is None


def b64url(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def tx_payload(**overrides) -> dict:
    payload = {
        "state": "attacker-chosen-state",
        "code_verifier": "a" * 43,
        "redirect_to": "/",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        "type": "oauth_transaction",
    }
    payload.update(overrides)
    return payload


# CSRF / state


class TestStateAndTransactionBinding:
    def test_callback_without_transaction_cookie(self, client, github, alice, user_repo):
        """Unsolicited callback: no login was ever started in this browser."""
        _, _, tx_name = cookie_names()
        code, state = github.authorize(start_login(client), alice)
        for cookie in [c for c in client.cookies.jar if c.name == tx_name]:
            client.cookies.jar.clear(cookie.domain, cookie.path, cookie.name)

        response = callback(client, code, state)

        assert_rejected_without_session(response, user_repo, alice.primary_email)
        assert github.token_requests == []  # code never redeemed

    def test_callback_without_state(self, client, github, alice, user_repo):
        code, _ = github.authorize(start_login(client), alice)

        response = callback(client, code, None)

        assert_rejected_without_session(response, user_repo, alice.primary_email)
        assert github.token_requests == []

    @pytest.mark.parametrize("state", ["", "wrong", "x" * 43])
    def test_callback_with_wrong_state(self, client, github, alice, user_repo, state):
        code, _ = github.authorize(start_login(client), alice)

        response = callback(client, code, state)

        assert_rejected_without_session(response, user_repo, alice.primary_email)
        assert github.token_requests == []

    def test_login_csrf_attacker_code_in_victim_browser(
        self, client, make_client, github, mallory, user_repo
    ):
        """Mallory starts a login in her own browser, approves it with her
        GitHub account, and lures the victim to the callback URL with her code
        and state. The victim's browser has its own pending transaction (or
        none) so the state does not match: the victim must not end up logged
        in as Mallory."""
        attacker = make_client()
        code, state = github.authorize(start_login(attacker), mallory)

        start_login(client)  # victim has an unrelated login pending
        response = callback(client, code, state)

        assert_rejected_without_session(response, user_repo, mallory.primary_email)
        # Mallory can still use her own code; the victim's attempt did not burn it
        assert callback(attacker, code, state).status_code == 307

    def test_login_csrf_victim_without_pending_login(
        self, client, make_client, github, mallory, user_repo
    ):
        attacker = make_client()
        code, state = github.authorize(start_login(attacker), mallory)

        response = callback(client, code, state)

        assert_rejected_without_session(response, user_repo, mallory.primary_email)

    def test_transaction_cookie_from_another_login_is_useless(
        self, client, make_client, github, alice, user_repo
    ):
        """Two parallel logins: swapping state between them fails both ways."""
        other = make_client()
        code_a, _state_a = github.authorize(start_login(client), alice)
        _code_b, state_b = github.authorize(start_login(other), alice)

        response = callback(client, code_a, state_b)

        assert_rejected_without_session(response, user_repo, alice.primary_email)


# PKCE


class TestPKCE:
    def test_intercepted_code_cannot_be_redeemed_by_attacker(
        self, client, make_client, github, alice, user_repo
    ):
        """Authorization code interception (RFC 7636 section 1): Mallory steals
        Alice's code (e.g. from logs, Referer or a malicious app) and plays it
        into a login *she* started. State and transaction cookie are valid
        for her, but her code_verifier does not match the challenge Alice's
        code was issued for, so GitHub refuses the exchange."""
        code, alice_state = github.authorize(start_login(client), alice)

        attacker = make_client()
        attacker_state = query(start_login(attacker))["state"]
        response = callback(attacker, code, attacker_state)

        assert_rejected_without_session(response, user_repo, alice.primary_email)
        assert response.json() == {"detail": "Authentication failed"}
        assert len(github.token_requests) == 1  # it was tried, and refused
        assert attacker.get(USER).status_code == 401

        # Alice's own, legitimate callback still works
        assert callback(client, code, alice_state).status_code == 307

    def test_challenge_is_derived_from_the_verifier_sent_on_exchange(self, client, github, alice):
        _, _, tx_name = cookie_names()
        authorize_url = start_login(client)
        verifier = decode_transaction(client.cookies[tx_name]).code_verifier
        code, state = github.authorize(authorize_url, alice)

        assert callback(client, code, state).status_code == 307
        assert github.token_requests[0]["code_verifier"] == verifier

    def test_forged_transaction_with_attacker_verifier(
        self, client, make_client, github, alice, attacker_keys, user_repo
    ):
        """If the transaction signature were not checked, an attacker could put
        a verifier of her choice next to a stolen code."""
        code, _ = github.authorize(start_login(client), alice)
        forged = jwt.encode(tx_payload(), attacker_keys.private_pem, algorithm="EdDSA")

        attacker = make_client()
        plant_transaction(attacker, forged)
        response = callback(attacker, code, "attacker-chosen-state")

        assert_rejected_without_session(response, user_repo, alice.primary_email)
        assert github.token_requests == []


# code replay


class TestCodeReplay:
    def test_replayed_callback_is_rejected(self, client, make_client, github, alice):
        """The transaction JWT is stateless and is not consumed server-side, so
        replaying the exact callback request (code, state and the old cookie)
        is only stopped by the provider's single-use code."""
        _, _, tx_name = cookie_names()
        authorize_url = start_login(client)
        tx_cookie = client.cookies[tx_name]
        code, state = github.authorize(authorize_url, alice)
        assert callback(client, code, state).status_code == 307

        replayer = make_client()
        plant_transaction(replayer, tx_cookie)
        response = callback(replayer, code, state)

        assert response.status_code == 400
        assert replayer.get(USER).status_code == 401

    def test_expired_code(self, client, github, alice, user_repo):
        code, state = github.authorize(start_login(client), alice)
        github.expire_code(code)

        response = callback(client, code, state)

        assert_rejected_without_session(response, user_repo, alice.primary_email)

    def test_made_up_code(self, client, github, alice, user_repo):
        _, state = github.authorize(start_login(client), alice)

        response = callback(client, "deadbeef", state)

        assert_rejected_without_session(response, user_repo, alice.primary_email)


# forged transactions


class TestForgedTransaction:
    def _attempt(self, client, github, alice, cookie_value: str):
        code, state = github.authorize(start_login(client), alice)
        plant_transaction(client, cookie_value)
        return callback(client, code, state), state

    def test_tampered_redirect_target(self, client, github, alice, user_repo):
        """Flip redirect_to inside a genuine transaction without re-signing."""
        _, _, tx_name = cookie_names()
        code, state = github.authorize(start_login(client), alice)
        header, payload, signature = client.cookies[tx_name].split(".")
        claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
        claims["redirect_to"] = "https://evil.example/phish"
        plant_transaction(client, f"{header}.{b64url(claims)}.{signature}")

        response = callback(client, code, state)

        assert_rejected_without_session(response, user_repo, alice.primary_email)

    def test_alg_none(self, client, github, alice, user_repo):
        _, _, tx_name = cookie_names()
        code, state = github.authorize(start_login(client), alice)
        genuine = decode_transaction(client.cookies[tx_name])
        payload = tx_payload(
            state=genuine.state,
            code_verifier=genuine.code_verifier,
            exp=int(time.time()) + 300,
        )
        unsigned = f"{b64url({'alg': 'none', 'typ': 'JWT'})}.{b64url(payload)}."
        plant_transaction(client, unsigned)

        response = callback(client, code, state)

        assert_rejected_without_session(response, user_repo, alice.primary_email)
        assert github.token_requests == []

    def test_expired_transaction(self, client, github, alice, signing_keys, user_repo):
        _, _, tx_name = cookie_names()
        code, state = github.authorize(start_login(client), alice)
        genuine = decode_transaction(client.cookies[tx_name])
        expired = jwt.encode(
            tx_payload(
                state=genuine.state,
                code_verifier=genuine.code_verifier,
                exp=datetime.now(UTC) - timedelta(seconds=1),
            ),
            signing_keys.private_pem,
            algorithm="EdDSA",
        )
        plant_transaction(client, expired)

        response = callback(client, code, state)

        assert_rejected_without_session(response, user_repo, alice.primary_email)
        assert github.token_requests == []

    def test_transaction_without_expiry(self, client, github, alice, signing_keys, user_repo):
        payload = tx_payload()
        del payload["exp"]
        token = jwt.encode(payload, signing_keys.private_pem, algorithm="EdDSA")

        response, _ = self._attempt(client, github, alice, token)

        assert_rejected_without_session(response, user_repo, alice.primary_email)

    def test_access_token_used_as_transaction(self, client, github, alice, user_repo):
        """Token confusion: a validly signed JWT of another type."""
        eve = user_repo.create(User(email="eve@example.com", name="Eve", access=True))
        access = JsonWebToken.access(eve.id).encode()

        response, _ = self._attempt(client, github, alice, access)

        assert_rejected_without_session(response, user_repo, alice.primary_email)
        assert github.token_requests == []

    @pytest.mark.parametrize("token_type", ["access", "refresh", None])
    def test_transaction_shaped_token_of_another_type(
        self, client, github, alice, signing_keys, user_repo, token_type
    ):
        """Correctly signed, carries the genuine state and verifier, but is not
        typed as a transaction. Only the type claim can reject it."""
        _, _, tx_name = cookie_names()
        code, state = github.authorize(start_login(client), alice)
        genuine = decode_transaction(client.cookies[tx_name])
        payload = tx_payload(
            state=genuine.state, code_verifier=genuine.code_verifier, type=token_type
        )
        if token_type is None:
            del payload["type"]
        plant_transaction(client, jwt.encode(payload, signing_keys.private_pem, algorithm="EdDSA"))

        response = callback(client, code, state)

        assert_rejected_without_session(response, user_repo, alice.primary_email)
        assert github.token_requests == []

    @pytest.mark.parametrize("garbage", ["", "not-a-jwt", "a.b.c", "e30.e30.", "%00"])
    def test_garbage_transaction(self, client, github, alice, user_repo, garbage):
        response, _ = self._attempt(client, github, alice, garbage)

        assert_rejected_without_session(response, user_repo, alice.primary_email)


# open redirect


OPEN_REDIRECT_PAYLOADS = [
    "https://evil.example",
    "http://evil.example/path",
    "//evil.example",
    "///evil.example",
    "/\\evil.example",
    "\\\\evil.example",
    "\\/evil.example",
    "/\t/evil.example",
    "/\n/evil.example",
    "/\r\nSet-Cookie: x=y",
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "evil.example",
    "https:evil.example",
    " //evil.example",
]


class TestOpenRedirect:
    @pytest.mark.parametrize("target", OPEN_REDIRECT_PAYLOADS)
    def test_external_redirect_targets_collapse_to_root(self, client, github, alice, target):
        response = login(client, github, alice, redirect_to=target)

        assert response.status_code == 307
        assert response.headers["location"] == "/"

    @pytest.mark.parametrize("target", ["/dashboard", "/measurements/42?view=raw#chart", "/a/b/c"])
    def test_same_origin_paths_are_kept(self, client, github, alice, target):
        response = login(client, github, alice, redirect_to=target)

        assert response.headers["location"] == target

    def test_failed_login_never_redirects(self, client, github, alice):
        code, _ = github.authorize(start_login(client, "https://evil.example"), alice)

        response = callback(client, code, "wrong-state")

        assert response.status_code == 400
        assert "location" not in response.headers


# misc


class TestSessionFixation:
    def test_preset_session_cookies_are_replaced_on_login(
        self, client, make_client, github, alice, mallory, user_repo
    ):
        """An attacker who plants her own session cookies in the victim's
        browser must not keep the victim inside her session after login."""
        access_name, refresh_name, _ = cookie_names()
        attacker = make_client()
        login(attacker, github, mallory)
        planted_access = attacker.cookies[access_name]
        planted_refresh = attacker.cookies[refresh_name]

        plant_cookie(client, access_name, planted_access)
        plant_cookie(client, refresh_name, planted_refresh)
        login(client, github, alice)

        assert client.cookies[access_name] != planted_access
        assert client.cookies[refresh_name] != planted_refresh
        alice_user = user_repo.get_by_email(alice.primary_email)
        assert JsonWebToken.decode(client.cookies[access_name], "access").sub == alice_user.id


class TestProviderSideRejections:
    def test_unverified_email_is_rejected(self, client, github, user_repo):
        unverified = GitHubAccount.with_email(7, "trudy", "alice@example.com", verified=False)

        response = login(client, github, unverified)

        assert_rejected_without_session(response, user_repo, "alice@example.com")

    def test_user_denies_consent(self, client, user_repo):
        """GitHub redirects back with ?error=access_denied and no code."""
        start_login(client)

        response = client.get(CALLBACK, params={"error": "access_denied", "state": "x"})

        assert 400 <= response.status_code < 500
        access_name, refresh_name, _ = cookie_names()
        assert access_name not in set_cookie_headers(response)
        assert refresh_name not in set_cookie_headers(response)
