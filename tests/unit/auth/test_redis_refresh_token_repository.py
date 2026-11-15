import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import fakeredis
import pytest
import redis
import redis.exceptions as rex

from auth.interfaces.refresh_token_repository_interface import (
    RefreshTokenRepositoryError,
    RefreshTokenRepositoryUnavailableError,
)
from auth.interfaces.refresh_token_repository_interface import RefreshTokenRotationResult as Result
from auth.redis_refresh_token_repository import KEY_PREFIX, RedisRefreshTokenRepository
from auth.tokens import JsonWebToken

REFRESH_LIFETIME = 60 * 60  # seconds

pytestmark = pytest.mark.unit


def family_key(fid: uuid.UUID) -> str:
    return f"{KEY_PREFIX}:family:{fid}"


def user_key(user_id: uuid.UUID) -> str:
    return f"{KEY_PREFIX}:user:{user_id}"


def make_token(
    user_id: uuid.UUID,
    family_id: uuid.UUID | None = None,
    lifetime: int = REFRESH_LIFETIME,
) -> JsonWebToken:
    """Builds the model directly, so no JWT settings are needed for store tests."""
    now = int(time.time())
    return JsonWebToken(
        iss="test-issuer",
        sub=user_id,
        aud="test-audience",
        iat=now,
        exp=now + lifetime,
        jti=uuid.uuid4(),
        fid=family_id or uuid.uuid4(),
        token_type="refresh",
    )


def next_token(previous: JsonWebToken, lifetime: int = REFRESH_LIFETIME) -> JsonWebToken:
    """The token issued when `previous` is rotated: same user and family, new jti."""
    return make_token(previous.sub, family_id=previous.fid, lifetime=lifetime)


@pytest.fixture(params=[True, False], ids=["decode_responses", "bytes"])
def redis_client(request):
    """Runs every test with and without decode_responses, as the repo must handle both."""
    client = fakeredis.FakeRedis(decode_responses=request.param)
    yield client
    client.flushall()


@pytest.fixture
def repo(redis_client) -> RedisRefreshTokenRepository:
    return RedisRefreshTokenRepository(redis_client)


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


class TestStart:
    def test_registers_the_jti_as_the_families_valid_token(self, repo, redis_client, user_id):
        token = make_token(user_id)
        repo.start(token)

        stored = redis_client.get(family_key(token.fid))
        stored = stored.decode() if isinstance(stored, bytes) else stored
        assert stored == str(token.jti)

    def test_family_expires_with_the_token(self, repo, redis_client, user_id):
        token = make_token(user_id, lifetime=REFRESH_LIFETIME)
        repo.start(token)

        ttl = redis_client.ttl(family_key(token.fid))
        assert REFRESH_LIFETIME - 5 <= ttl <= REFRESH_LIFETIME

    def test_family_is_added_to_the_user_index(self, repo, redis_client, user_id):
        token = make_token(user_id)
        repo.start(token)

        assert redis_client.zscore(user_key(user_id), str(token.fid)) == token.exp

    def test_index_prunes_expired_families(self, repo, redis_client, user_id):
        stale_fid = uuid.uuid4()
        redis_client.zadd(user_key(user_id), {str(stale_fid): int(time.time()) - 10})

        token = make_token(user_id)
        repo.start(token)

        assert redis_client.zscore(user_key(user_id), str(stale_fid)) is None
        assert redis_client.zscore(user_key(user_id), str(token.fid)) is not None

    def test_a_started_family_can_be_rotated(self, repo, user_id):
        first = make_token(user_id)
        repo.start(first)

        assert repo.rotate(first, next_token(first)) is Result.OK


class TestRotate:
    def test_valid_token_rotates(self, repo, user_id):
        first = make_token(user_id)
        repo.start(first)

        assert repo.rotate(first, next_token(first)) is Result.OK

    def test_chain_of_rotations_all_succeed(self, repo, user_id):
        current = make_token(user_id)
        repo.start(current)

        for _ in range(5):
            new = next_token(current)
            assert repo.rotate(current, new) is Result.OK
            current = new

    def test_new_token_is_stored_as_the_valid_one(self, repo, redis_client, user_id):
        first = make_token(user_id)
        repo.start(first)
        second = next_token(first)
        repo.rotate(first, second)

        stored = redis_client.get(family_key(first.fid))
        stored = stored.decode() if isinstance(stored, bytes) else stored
        assert stored == str(second.jti)

    def test_rotation_slides_the_family_expiry_forward(self, repo, redis_client, user_id):
        first = make_token(user_id, lifetime=60)
        repo.start(first)
        second = next_token(first, lifetime=REFRESH_LIFETIME)
        repo.rotate(first, second)

        assert redis_client.ttl(family_key(first.fid)) > 60
        assert redis_client.zscore(user_key(user_id), str(first.fid)) == second.exp

    def test_never_started_family_is_unknown(self, repo, user_id):
        stranger = make_token(user_id)

        assert repo.rotate(stranger, next_token(stranger)) is Result.UNKNOWN

    def test_unknown_family_is_not_created_by_the_attempt(self, repo, redis_client, user_id):
        stranger = make_token(user_id)
        repo.rotate(stranger, next_token(stranger))

        assert not redis_client.exists(family_key(stranger.fid))

    def test_expired_family_is_unknown(self, repo, redis_client, user_id):
        token = make_token(user_id)
        repo.start(token)
        redis_client.delete(family_key(token.fid))  # what Redis does when the TTL elapses

        assert repo.rotate(token, next_token(token)) is Result.UNKNOWN


class TestReuseDetection:
    def test_replaying_a_rotated_token_is_reuse(self, repo, user_id):
        first = make_token(user_id)
        repo.start(first)
        repo.rotate(first, next_token(first))

        assert repo.rotate(first, next_token(first)) is Result.REUSE

    def test_reuse_revokes_the_whole_family(self, repo, redis_client, user_id):
        first = make_token(user_id)
        repo.start(first)
        second = next_token(first)
        repo.rotate(first, second)

        repo.rotate(first, next_token(first))  # replay of the stolen token

        assert not redis_client.exists(family_key(first.fid))

    def test_after_reuse_the_legitimate_current_token_is_dead_too(self, repo, user_id):
        first = make_token(user_id)
        repo.start(first)
        second = next_token(first)
        repo.rotate(first, second)

        repo.rotate(first, next_token(first))  # attacker replays the old token

        assert repo.rotate(second, next_token(second)) is Result.UNKNOWN

    def test_reuse_removes_the_family_from_the_user_index(self, repo, redis_client, user_id):
        first = make_token(user_id)
        repo.start(first)
        repo.rotate(first, next_token(first))

        repo.rotate(first, next_token(first))

        assert redis_client.zscore(user_key(user_id), str(first.fid)) is None

    def test_reuse_does_not_affect_other_families_of_the_same_user(self, repo, user_id):
        compromised = make_token(user_id)
        other_device = make_token(user_id)
        repo.start(compromised)
        repo.start(other_device)
        repo.rotate(compromised, next_token(compromised))

        repo.rotate(compromised, next_token(compromised))  # reuse

        assert repo.rotate(other_device, next_token(other_device)) is Result.OK

    def test_a_token_from_another_family_cannot_rotate_this_one(self, repo, user_id):
        mine = make_token(user_id)
        theirs = make_token(user_id)
        repo.start(mine)
        repo.start(theirs)

        # Presented jti belongs to `theirs`, but the family id is `mine`
        forged = make_token(user_id, family_id=mine.fid)
        forged = forged.model_copy(update={"jti": theirs.jti})

        assert repo.rotate(forged, next_token(forged)) is Result.REUSE


class TestRevokeFamily:
    def test_revoked_family_can_no_longer_rotate(self, repo, user_id):
        token = make_token(user_id)
        repo.start(token)

        repo.revoke_family(user_id, token.fid)

        assert repo.rotate(token, next_token(token)) is Result.UNKNOWN

    def test_revoked_family_is_not_resurrected_by_a_rotation_attempt(
        self, repo, redis_client, user_id
    ):
        token = make_token(user_id)
        repo.start(token)
        repo.revoke_family(user_id, token.fid)

        repo.rotate(token, next_token(token))

        assert not redis_client.exists(family_key(token.fid))

    def test_removes_the_family_from_the_user_index(self, repo, redis_client, user_id):
        token = make_token(user_id)
        repo.start(token)

        repo.revoke_family(user_id, token.fid)

        assert redis_client.zscore(user_key(user_id), str(token.fid)) is None

    def test_other_families_are_untouched(self, repo, user_id):
        a, b = make_token(user_id), make_token(user_id)
        repo.start(a)
        repo.start(b)

        repo.revoke_family(user_id, a.fid)

        assert repo.rotate(b, next_token(b)) is Result.OK

    def test_is_idempotent(self, repo, user_id):
        token = make_token(user_id)
        repo.start(token)

        repo.revoke_family(user_id, token.fid)
        repo.revoke_family(user_id, token.fid)  # must not raise

    def test_revoking_an_unknown_family_does_not_raise(self, repo, user_id):
        repo.revoke_family(user_id, uuid.uuid4())


class TestRevokeAllForUser:
    def test_revokes_every_session_of_the_user(self, repo, user_id):
        sessions = [make_token(user_id) for _ in range(3)]
        for token in sessions:
            repo.start(token)

        repo.revoke_all_for_user(user_id)

        for token in sessions:
            assert repo.rotate(token, next_token(token)) is Result.UNKNOWN

    def test_clears_the_user_index(self, repo, redis_client, user_id):
        repo.start(make_token(user_id))
        repo.revoke_all_for_user(user_id)

        assert not redis_client.exists(user_key(user_id))

    def test_includes_families_whose_expiry_slid_forward(self, repo, user_id):
        first = make_token(user_id)
        repo.start(first)
        second = next_token(first)
        repo.rotate(first, second)

        repo.revoke_all_for_user(user_id)

        assert repo.rotate(second, next_token(second)) is Result.UNKNOWN

    def test_other_users_are_untouched(self, repo, user_id):
        other_user = uuid.uuid4()
        mine, theirs = make_token(user_id), make_token(other_user)
        repo.start(mine)
        repo.start(theirs)

        repo.revoke_all_for_user(user_id)

        assert repo.rotate(theirs, next_token(theirs)) is Result.OK

    def test_user_without_sessions_does_not_raise(self, repo):
        repo.revoke_all_for_user(uuid.uuid4())

    def test_is_idempotent(self, repo, user_id):
        repo.start(make_token(user_id))

        repo.revoke_all_for_user(user_id)
        repo.revoke_all_for_user(user_id)


class TestConcurrency:
    """The property the whole design depends on: when several requests present the
    same token at once, exactly one of them may succeed."""

    @pytest.mark.parametrize("attempts", [2, 10, 30])
    def test_exactly_one_concurrent_rotation_wins(self, repo, user_id, attempts):
        token = make_token(user_id)
        repo.start(token)
        barrier = threading.Barrier(attempts)

        def attempt() -> Result:
            candidate = next_token(token)
            barrier.wait()  # release all threads at the same moment
            return repo.rotate(token, candidate)

        with ThreadPoolExecutor(max_workers=attempts) as pool:
            results = list(pool.map(lambda _: attempt(), range(attempts)))

        assert results.count(Result.OK) == 1
        # Losers see REUSE (they hit the live family) or UNKNOWN (the family was
        # already revoked by an earlier loser). Neither may succeed.
        assert all(r in (Result.REUSE, Result.UNKNOWN) for r in results if r is not Result.OK)

    def test_concurrent_race_ends_with_the_family_revoked(self, repo, redis_client, user_id):
        token = make_token(user_id)
        repo.start(token)
        barrier = threading.Barrier(5)

        def attempt(_):
            candidate = next_token(token)
            barrier.wait()
            return repo.rotate(token, candidate)

        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(attempt, range(5)))

        # Someone presented the token more than once, so the session must be dead.
        assert not redis_client.exists(family_key(token.fid))


class TestStoreOutage:
    """redis-py errors must not leak: callers only see the contract's errors."""

    @pytest.fixture
    def down_repo(self) -> RedisRefreshTokenRepository:
        server = fakeredis.FakeServer()
        server.connected = False
        return RedisRefreshTokenRepository(fakeredis.FakeRedis(server=server))

    @pytest.mark.parametrize(
        "call",
        [
            lambda repo, t: repo.start(t),
            lambda repo, t: repo.rotate(t, next_token(t)),
            lambda repo, t: repo.revoke_family(t.sub, t.fid),
            lambda repo, t: repo.revoke_all_for_user(t.sub),
        ],
        ids=["start", "rotate", "revoke_family", "revoke_all_for_user"],
    )
    def test_unreachable_store_is_unavailable(self, down_repo, user_id, call):
        token = make_token(user_id)

        with pytest.raises(RefreshTokenRepositoryUnavailableError) as exc:
            call(down_repo, token)

        assert isinstance(exc.value.__cause__, redis.RedisError)


class TestErrorTranslation:
    """Errors are classified, so callers can tell "retry later" from "needs a fix"."""

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            # transient
            (rex.ConnectionError, RefreshTokenRepositoryUnavailableError),
            (rex.TimeoutError, RefreshTokenRepositoryUnavailableError),
            (rex.MaxConnectionsError, RefreshTokenRepositoryUnavailableError),
            (rex.BusyLoadingError, RefreshTokenRepositoryUnavailableError),
            (rex.ReadOnlyError, RefreshTokenRepositoryUnavailableError),
            (rex.TryAgainError, RefreshTokenRepositoryUnavailableError),
            (rex.ClusterDownError, RefreshTokenRepositoryUnavailableError),
            (rex.MasterDownError, RefreshTokenRepositoryUnavailableError),
            (rex.OutOfMemoryError, RefreshTokenRepositoryUnavailableError),
            # permanent; the first two subclass ConnectionError in redis-py
            (rex.AuthenticationError, RefreshTokenRepositoryError),
            (rex.AuthorizationError, RefreshTokenRepositoryError),
            (rex.NoPermissionError, RefreshTokenRepositoryError),
            (rex.ResponseError, RefreshTokenRepositoryError),
            (rex.DataError, RefreshTokenRepositoryError),
            (rex.InvalidResponse, RefreshTokenRepositoryError),
        ],
        ids=lambda v: v.__name__,
    )
    def test_classification(self, repo, redis_client, user_id, monkeypatch, error, expected):
        cause = error("simulated")

        def fail(*args, **kwargs):
            raise cause

        monkeypatch.setattr(redis_client, "zrange", fail)

        with pytest.raises(RefreshTokenRepositoryError) as exc:
            repo.revoke_all_for_user(user_id)

        assert type(exc.value) is expected
        assert exc.value.__cause__ is cause

    def test_unexpected_script_result(self, repo, user_id, monkeypatch):
        token = make_token(user_id)
        monkeypatch.setattr(repo, "_rotate", lambda **_: 7)

        with pytest.raises(RefreshTokenRepositoryError) as exc:
            repo.rotate(token, next_token(token))

        assert type(exc.value) is RefreshTokenRepositoryError
