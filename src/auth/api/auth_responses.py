from pydantic import BaseModel


class UserInfoResponse(BaseModel):
    user_id: str
    name: str
    access: bool = False
    admin: bool = False
