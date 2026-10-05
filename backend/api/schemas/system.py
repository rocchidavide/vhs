from ninja import Schema


class SystemInfoOut(Schema):
    vhs_version: str
    ytdlp_version: str
    deno_version: str
    ytdlp_auto_update: bool
    latest_version: str | None
    latest_release_url: str | None
    update_available: bool
