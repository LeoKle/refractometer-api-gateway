import uuid

from auth.interfaces.refresh_token_repository_interface import (
    RefreshTokenRepositoryInterface,
    RefreshTokenRotationResult,
)
from auth.tokens import JsonWebToken


class MockRefreshTokenRepository(RefreshTokenRepositoryInterface):
    def __init__(self):
        self.families: dict[uuid.UUID, tuple[uuid.UUID, uuid.UUID]] = {}  # fid -> (user, jti)
        self.rotate_calls = 0

    def start(self, token: JsonWebToken) -> None:
        self.families[token.fid] = (token.sub, token.jti)

    def rotate(self, presented: JsonWebToken, new: JsonWebToken) -> RefreshTokenRotationResult:
        self.rotate_calls += 1
        entry = self.families.get(presented.fid)
        if entry is None:
            return RefreshTokenRotationResult.UNKNOWN
        if entry[1] != presented.jti:
            del self.families[presented.fid]
            return RefreshTokenRotationResult.REUSE
        self.families[presented.fid] = (presented.sub, new.jti)
        return RefreshTokenRotationResult.OK

    def revoke_family(self, user_id: uuid.UUID, family_id: uuid.UUID) -> None:
        self.families.pop(family_id, None)

    def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        self.families = {f: v for f, v in self.families.items() if v[0] != user_id}
