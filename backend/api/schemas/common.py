from ninja import Schema


class ErrorOut(Schema):
    detail: str
    code: str | None = None
    video_id: int | None = None
