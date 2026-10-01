"""ffprobe wrapper: what the archived file really contains, not what the source claimed."""

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from engine.errors import EngineError, ErrorCode

DEFAULT_TIMEOUT = 120


@dataclass(frozen=True)
class VideoStream:
    codec: str
    profile: str = ""
    pix_fmt: str = ""
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class AudioStream:
    codec: str
    channels: int | None = None


@dataclass(frozen=True)
class MediaProbe:
    format_names: tuple[str, ...]
    duration: float | None = None
    video: VideoStream | None = None
    audio: AudioStream | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["format_names"] = list(self.format_names)
        return data

    @property
    def resolution(self) -> str:
        if self.video and self.video.width and self.video.height:
            return f"{self.video.width}x{self.video.height}"
        return ""


def parse_probe(data: dict) -> MediaProbe:
    """Build a MediaProbe from `ffprobe -show_format -show_streams -of json` output."""
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    video = next((s for s in streams if _is_video(s)), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    return MediaProbe(
        format_names=tuple(name for name in (fmt.get("format_name") or "").split(",") if name),
        duration=_to_float(fmt.get("duration")),
        video=VideoStream(
            codec=video.get("codec_name", ""),
            profile=video.get("profile", "") or "",
            pix_fmt=video.get("pix_fmt", "") or "",
            width=video.get("width"),
            height=video.get("height"),
        )
        if video
        else None,
        audio=AudioStream(codec=audio.get("codec_name", ""), channels=audio.get("channels"))
        if audio
        else None,
    )


def probe(path: Path, timeout: int = DEFAULT_TIMEOUT) -> MediaProbe:
    binary = shutil.which("ffprobe")
    if binary is None:
        raise EngineError(ErrorCode.PROCESSING, "ffprobe is not installed.")
    command = [binary, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise EngineError(ErrorCode.PROCESSING, "ffprobe did not answer in time.") from exc
    if completed.returncode != 0:
        raise EngineError(ErrorCode.PROCESSING, f"ffprobe: {completed.stderr.strip()}")
    try:
        return parse_probe(json.loads(completed.stdout or "{}"))
    except ValueError as exc:
        raise EngineError(ErrorCode.PROCESSING, "Invalid ffprobe output.") from exc


def _is_video(stream: dict) -> bool:
    # Cover art in audio files is a video stream flagged as attached picture.
    disposition = stream.get("disposition") or {}
    return stream.get("codec_type") == "video" and not disposition.get("attached_pic")


def _to_float(value) -> float | None:
    try:
        return float(value) if value not in (None, "N/A") else None
    except (TypeError, ValueError):
        return None
