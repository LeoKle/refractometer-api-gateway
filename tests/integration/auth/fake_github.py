"""An in-process stand-in for GitHub's OAuth server and user API.

It is a behavioural fake, not a stub: it enforces the parts of the protocol the
gateway relies on, so a broken gateway gets the same rejection real GitHub
would give it:

* authorization codes are bound to client_id, redirect_uri and the PKCE
  code_challenge they were issued for, are single use and expire,
* the token endpoint verifies client credentials and the PKCE code_verifier
  (S256 only), and answers errors GitHub-style (HTTP 200 + ``error`` member),
* the user API only answers to access tokens it issued.

The test plays the browser: it follows the gateway's redirect to
``/oauth/authorize`` by calling :meth:`FakeGitHub.authorize` directly.
"""

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

import httpx
import respx

AUTHORIZE_URL = "https://github.com/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
EMAILS_URL = "https://api.github.com/user/emails"

CODE_TTL_SECONDS = 600


@dataclass
class GitHubAccount:
    id: int
    login: str
    name: str | None
    emails: list[dict] = field(default_factory=list)

    @classmethod
    def with_email(cls, id: int, login: str, email: str, *, verified: bool = True):
        return cls(
            id=id,
            login=login,
            name=login.capitalize(),
            emails=[{"email": email, "primary": True, "verified": verified}],
        )

    @property
    def primary_email(self) -> str:
        return next(e["email"] for e in self.emails if e["primary"])


@dataclass
class IssuedCode:
    account: GitHubAccount
    client_id: str
    redirect_uri: str
    code_challenge: str
    code_challenge_method: str
    expires_at: float
    redeemed: bool = False


class AuthorizeRejectedError(Exception):
    """GitHub would show an error page instead of redirecting back."""


def s256(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class FakeGitHub:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

        self.codes: dict[str, IssuedCode] = {}
        self.access_tokens: dict[str, GitHubAccount] = {}

        # observability for assertions
        self.token_requests: list[dict[str, str]] = []
        self.user_api_calls = 0

        # fault injection
        self.token_endpoint_status: int | None = None
        self.user_api_status: int | None = None
        self.unreachable = False

    # browser side

    def authorize(self, authorize_url: str, account: GitHubAccount) -> tuple[str, str]:
        """The user approves the app on GitHub. Returns (code, state) as GitHub
        would append them to the redirect back to the gateway's callback."""
        parts = urlsplit(authorize_url)
        if f"{parts.scheme}://{parts.netloc}{parts.path}" != AUTHORIZE_URL:
            msg = f"not an authorize URL: {authorize_url}"
            raise AuthorizeRejectedError(msg)

        params = {k: v[0] for k, v in parse_qs(parts.query).items()}

        if params.get("client_id") != self.client_id:
            msg = "unknown client_id"
            raise AuthorizeRejectedError(msg)
        if params.get("redirect_uri") != self.redirect_uri:
            msg = "redirect_uri does not match the registered callback"
            raise AuthorizeRejectedError(msg)
        if params.get("response_type") != "code":
            msg = "unsupported response_type"
            raise AuthorizeRejectedError(msg)
        if not params.get("code_challenge"):
            msg = "PKCE code_challenge missing"
            raise AuthorizeRejectedError(msg)

        code = secrets.token_hex(10)
        self.codes[code] = IssuedCode(
            account=account,
            client_id=params["client_id"],
            redirect_uri=params["redirect_uri"],
            code_challenge=params["code_challenge"],
            code_challenge_method=params.get("code_challenge_method", "plain"),
            expires_at=time.time() + CODE_TTL_SECONDS,
        )
        return code, params.get("state", "")

    def expire_code(self, code: str) -> None:
        self.codes[code].expires_at = time.time() - 1

    # server side

    def install(self, router: respx.MockRouter) -> None:
        router.post(TOKEN_URL).mock(side_effect=self._token_endpoint)
        router.get(USER_URL).mock(side_effect=self._user_endpoint)
        router.get(EMAILS_URL).mock(side_effect=self._emails_endpoint)

    @staticmethod
    def _error(error: str, description: str) -> httpx.Response:
        # GitHub answers token errors with 200 and an error member
        return httpx.Response(200, json={"error": error, "error_description": description})

    def _token_endpoint(self, request: httpx.Request) -> httpx.Response:
        if self.unreachable:
            msg = "fake GitHub unreachable"
            raise httpx.ConnectError(msg, request=request)
        if self.token_endpoint_status is not None:
            return httpx.Response(self.token_endpoint_status, text="upstream failure")

        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.token_requests.append(form)

        issued_or_error = self._verify_grant(form)
        if isinstance(issued_or_error, httpx.Response):
            return issued_or_error

        issued_or_error.redeemed = True
        token = f"gho_{secrets.token_hex(16)}"
        self.access_tokens[token] = issued_or_error.account
        return httpx.Response(
            200, json={"access_token": token, "token_type": "bearer", "scope": "user:email"}
        )

    def _verify_grant(self, form: dict[str, str]) -> IssuedCode | httpx.Response:
        if (
            form.get("client_id") != self.client_id
            or form.get("client_secret") != self.client_secret
        ):
            return self._error("incorrect_client_credentials", "bad client credentials")

        issued = self.codes.get(form.get("code", ""))
        if issued is None or issued.expires_at < time.time():
            return self._error("bad_verification_code", "code is incorrect or expired")

        if issued.redeemed:
            # RFC 6749 4.1.2: a code used twice must be refused and SHOULD
            # revoke the tokens previously issued from it
            for token, account in list(self.access_tokens.items()):
                if account is issued.account:
                    del self.access_tokens[token]
            return self._error("bad_verification_code", "code already redeemed")

        if form.get("redirect_uri") != issued.redirect_uri:
            return self._error("redirect_uri_mismatch", "redirect_uri mismatch")

        verifier = form.get("code_verifier")
        if issued.code_challenge_method != "S256":
            return self._error("invalid_request", "only S256 PKCE is accepted")
        if not verifier or s256(verifier) != issued.code_challenge:
            return self._error("invalid_grant", "PKCE verification failed")

        return issued

    def _authenticated(self, request: httpx.Request) -> GitHubAccount | httpx.Response:
        if self.unreachable:
            msg = "fake GitHub unreachable"
            raise httpx.ConnectError(msg, request=request)
        self.user_api_calls += 1
        if self.user_api_status is not None:
            return httpx.Response(self.user_api_status, text="upstream failure")

        auth = request.headers.get("authorization", "")
        account = self.access_tokens.get(auth.removeprefix("Bearer ").strip())
        if account is None:
            return httpx.Response(401, json={"message": "Bad credentials"})
        return account

    def _user_endpoint(self, request: httpx.Request) -> httpx.Response:
        account = self._authenticated(request)
        if isinstance(account, httpx.Response):
            return account
        return httpx.Response(
            200, json={"id": account.id, "login": account.login, "name": account.name}
        )

    def _emails_endpoint(self, request: httpx.Request) -> httpx.Response:
        account = self._authenticated(request)
        if isinstance(account, httpx.Response):
            return account
        return httpx.Response(200, json=account.emails)
