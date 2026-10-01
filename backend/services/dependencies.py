"""Default infrastructure used by the services; tests inject their own."""

from engine.downloader.base import BaseDownloader
from storage import Storage


def get_storage() -> Storage:
    from services.library_service import build_storage

    return build_storage()


def get_downloader() -> BaseDownloader:
    from engine.downloader.ytdlp import YTDLPDownloader

    return YTDLPDownloader()
