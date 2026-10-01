from ninja import Schema


class HealthOut(Schema):
    status: str
    database: str
    storage: str = "unknown"
    storage_message: str = ""
