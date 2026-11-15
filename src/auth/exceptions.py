"""Errors the auth module raises to its callers (controllers, guards, other modules).
AuthError
├── AuthenticationError              client side -> 4xx, retrying won't help
│   ├── InvalidLoginTransactionError
│   ├── LoginRejectedError
│   └── InvalidSessionError
└── AuthUnavailableError             server side -> 503, retry later
    ├── AuthProviderUnavailableError
    └── InfrastructureUnavailableError
"""


class AuthError(Exception):
    """Base class for every error the auth module raises to its callers."""


# --- client side ------------------------------------------------------------


class AuthenticationError(AuthError):
    """The request could not be authenticated. Repeating it unchanged will fail
    again; the user has to (re-)start the login."""


class InvalidLoginTransactionError(AuthenticationError):
    """The login callback does not belong to a login this server started:
    transaction missing, expired or forged, or the state does not match."""


class LoginRejectedError(AuthenticationError):
    """The OAuth provider rejected the authorization code, or did not return a
    usable identity (e.g. no verified email)."""


class InvalidSessionError(AuthenticationError):
    """The refresh token is missing, invalid, expired, revoked or was reused,
    or the user it belongs to no longer exists or has lost access."""


# --- server side ------------------------------------------------------------


class AuthUnavailableError(AuthError):
    """A dependency auth relies on is failing. The request itself was fine and
    may succeed when retried later. Must never be reported as 401: that would
    log every user out during an outage."""


class AuthProviderUnavailableError(AuthUnavailableError):
    """The OAuth provider could not be reached or answered with a server error."""


class InfrastructureUnavailableError(AuthUnavailableError):
    """Our own infrastructure (user database, refresh token store) is
    temporarily unavailable."""
