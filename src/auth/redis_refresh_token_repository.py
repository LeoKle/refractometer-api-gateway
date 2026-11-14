import time
from uuid import UUID

from redis import Redis

from auth.interfaces.refresh_token_repository_interface import (
    RefreshTokenRepositoryInterface,
    RefreshTokenRotationResult,
)
from auth.tokens import JsonWebToken

KEY_PREFIX = "auth:refresh"

# Keys:
#   auth:refresh:family:{fid}      -> jti of the family's one valid refresh token
#                                     (TTL = remaining lifetime of that token)
#   auth:refresh:user:{user_id}    -> sorted set of the user's family ids,
#                                     scored by family expiry (for revoke-all)
#
# KEYS[1] family key, KEYS[2] user index key
# ARGV[1] presented jti, ARGV[2] new jti, ARGV[3] ttl seconds,
# ARGV[4] family id,     ARGV[5] new exp (unix), ARGV[6] now (unix)
_ROTATE_SCRIPT = """
local current = redis.call("GET", KEYS[1])
if not current then
  return 0
end
if current ~= ARGV[1] then
  redis.call("DEL", KEYS[1])
  redis.call("ZREM", KEYS[2], ARGV[4])
  return -1
end
redis.call("SET", KEYS[1], ARGV[2], "EX", ARGV[3])
redis.call("ZADD", KEYS[2], ARGV[5], ARGV[4])
redis.call("ZREMRANGEBYSCORE", KEYS[2], "-inf", ARGV[6])
redis.call("EXPIRE", KEYS[2], ARGV[3])
return 1
"""

_SCRIPT_RESULTS = {
    1: RefreshTokenRotationResult.OK,
    -1: RefreshTokenRotationResult.REUSE,
    0: RefreshTokenRotationResult.UNKNOWN,
}


def _as_str(value: str | bytes) -> str:
    """redis-py returns bytes unless the client was built with decode_responses=True."""
    return value.decode() if isinstance(value, bytes) else value


class RedisRefreshTokenRepository(RefreshTokenRepositoryInterface):
    def __init__(self, redis_client: Redis):
        self._redis = redis_client
        self._rotate = redis_client.register_script(_ROTATE_SCRIPT)

    @staticmethod
    def _family_key(family_id: UUID | str) -> str:
        return f"{KEY_PREFIX}:family:{family_id}"

    @staticmethod
    def _user_key(user_id: UUID | str) -> str:
        return f"{KEY_PREFIX}:user:{user_id}"

    @staticmethod
    def _ttl(token: JsonWebToken) -> int:
        return max(token.exp - int(time.time()), 1)

    def start(self, token: JsonWebToken) -> None:
        ttl = self._ttl(token)
        user_key = self._user_key(token.sub)

        pipe = self._redis.pipeline(transaction=True)
        pipe.set(self._family_key(token.fid), str(token.jti), ex=ttl)
        pipe.zadd(user_key, {str(token.fid): token.exp})
        pipe.zremrangebyscore(user_key, "-inf", int(time.time()))  # prune expired families
        pipe.expire(user_key, ttl)
        pipe.execute()

    def rotate(self, presented: JsonWebToken, new: JsonWebToken) -> RefreshTokenRotationResult:
        result = self._rotate(
            keys=[self._family_key(presented.fid), self._user_key(presented.sub)],
            args=[
                str(presented.jti),
                str(new.jti),
                self._ttl(new),
                str(presented.fid),
                new.exp,
                int(time.time()),
            ],
        )
        return _SCRIPT_RESULTS[int(result)]

    def revoke_family(self, user_id: UUID, family_id: UUID) -> None:
        pipe = self._redis.pipeline(transaction=True)
        pipe.delete(self._family_key(family_id))
        pipe.zrem(self._user_key(user_id), str(family_id))
        pipe.execute()

    def revoke_all_for_user(self, user_id: UUID) -> None:
        user_key = self._user_key(user_id)
        family_ids = [_as_str(fid) for fid in self._redis.zrange(user_key, 0, -1)]

        # A family created between the read above and the delete below is missed.
        # Acceptable for "log out everywhere"; the user can repeat it.
        pipe = self._redis.pipeline(transaction=True)
        for family_id in family_ids:
            pipe.delete(self._family_key(family_id))
        pipe.delete(user_key)
        pipe.execute()
