from ninja import Schema


class LoginIn(Schema):
    username: str
    password: str


class UserOut(Schema):
    id: int
    username: str
    is_superuser: bool
