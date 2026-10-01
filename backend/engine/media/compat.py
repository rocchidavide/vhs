"""Browser playback policy (§18): MP4 with 8-bit H.264 video and AAC/MP3 audio."""

from dataclasses import dataclass
from enum import StrEnum

from engine.media.probe import MediaProbe


class PlaybackAction(StrEnum):
    NATIVE = "native"
    REMUX = "remux"
    TRANSCODE = "transcode"
    UNSUPPORTED = "unsupported"


class StreamOp(StrEnum):
    COPY = "copy"
    ENCODE = "encode"
    NONE = "none"


MP4_FORMATS = {"mp4", "mov"}
VIDEO_CODECS = {"h264"}
VIDEO_PIX_FMTS = {"yuv420p", "yuvj420p"}
AUDIO_CODECS = {"aac", "mp3"}
_CODEC_NAMES = {
    "vp9": "VP9",
    "vp8": "VP8",
    "av1": "AV1",
    "hevc": "HEVC (H.265)",
    "opus": "Opus",
    "vorbis": "Vorbis",
    "flac": "FLAC",
    "ac3": "AC-3",
    "eac3": "E-AC-3",
}


# Stable codes of what prevents direct playback; the UI translates them (with their
# parameters), the English reason is only a diagnostic detail.
class IssueCode(StrEnum):
    NO_VIDEO = "no_video"
    VIDEO_CODEC = "video_codec"
    PIXEL_FORMAT = "pixel_format"
    AUDIO_CODEC = "audio_codec"
    CONTAINER = "container"


_REASONS = {
    IssueCode.NO_VIDEO: "The file contains no video",
    IssueCode.VIDEO_CODEC: "{codec} video is not supported by every browser",
    IssueCode.PIXEL_FORMAT: "H.264 video with pixel format {pix_fmt} is not supported",
    IssueCode.AUDIO_CODEC: "{codec} audio is not supported by every browser",
    IssueCode.CONTAINER: "The {container} container cannot be played: changing it to MP4 is enough",
}


@dataclass(frozen=True)
class PlaybackPlan:
    action: PlaybackAction
    video_op: StreamOp
    audio_op: StreamOp
    # Each issue: {"code": IssueCode, ...parameters}, e.g. {"code": "video_codec", "codec": "VP9"}.
    issues: tuple[dict[str, str], ...] = ()

    @property
    def needs_encoding(self) -> bool:
        return StreamOp.ENCODE in (self.video_op, self.audio_op)

    @property
    def reason(self) -> str:
        return describe_issues(self.issues)


def describe_issues(issues) -> str:
    """English diagnostic sentence for a list of issues (not shown as the UI message)."""
    parts = [_REASONS[issue["code"]].format(**issue) for issue in issues]
    return "; ".join(parts) + "." if parts else ""


def plan_playback(probe: MediaProbe) -> PlaybackPlan:
    if probe.video is None:
        return PlaybackPlan(
            PlaybackAction.UNSUPPORTED,
            StreamOp.NONE,
            StreamOp.NONE,
            ({"code": IssueCode.NO_VIDEO},),
        )

    issues = []
    video_op = StreamOp.COPY
    if probe.video.codec not in VIDEO_CODECS:
        video_op = StreamOp.ENCODE
        issues.append({"code": IssueCode.VIDEO_CODEC, "codec": _name(probe.video.codec)})
    elif probe.video.pix_fmt and probe.video.pix_fmt not in VIDEO_PIX_FMTS:
        video_op = StreamOp.ENCODE
        issues.append({"code": IssueCode.PIXEL_FORMAT, "pix_fmt": probe.video.pix_fmt})

    audio_op = StreamOp.NONE
    if probe.audio is not None:
        audio_op = StreamOp.COPY
        if probe.audio.codec not in AUDIO_CODECS:
            audio_op = StreamOp.ENCODE
            issues.append({"code": IssueCode.AUDIO_CODEC, "codec": _name(probe.audio.codec)})

    if StreamOp.ENCODE in (video_op, audio_op):
        return PlaybackPlan(PlaybackAction.TRANSCODE, video_op, audio_op, tuple(issues))
    if not MP4_FORMATS & set(probe.format_names):
        container = probe.format_names[0] if probe.format_names else "unknown"
        return PlaybackPlan(
            PlaybackAction.REMUX,
            video_op,
            audio_op,
            ({"code": IssueCode.CONTAINER, "container": container},),
        )
    return PlaybackPlan(PlaybackAction.NATIVE, video_op, audio_op)


def _name(codec: str) -> str:
    return _CODEC_NAMES.get(codec, codec or "unknown")
