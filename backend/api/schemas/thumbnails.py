def local_thumbnail_url(video) -> str | None:
    """API URL of the archived thumbnail, or None when there is no local copy (§22)."""
    if not video.thumbnail_path:
        return None
    return f"/api/v1/videos/{video.pk}/thumbnail"
