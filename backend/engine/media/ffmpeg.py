"""ffmpeg invocation for browser copies: remux (stream copy) or transcode."""

import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from engine.errors import EngineError, ErrorCode
from engine.media.compat import PlaybackAction, PlaybackPlan, StreamOp

STDERR_TAIL = 4000


@dataclass(frozen=True)
class EncodeOptions:
    preset: str = "veryfast"
    crf: int = 21
    audio_bitrate: str = "160k"
    threads: int = 0


def build_command(
    src: Path, dst: Path, plan: PlaybackPlan, options: EncodeOptions, binary: str = "ffmpeg"
) -> list[str]:
    if plan.action not in (PlaybackAction.REMUX, PlaybackAction.TRANSCODE):
        raise ValueError(f"No browser copy needed for action {plan.action}")
    command = [binary, "-hide_banner", "-nostdin", "-y", "-i", str(src), "-map", "0:v:0"]
    if plan.audio_op is not StreamOp.NONE:
        command += ["-map", "0:a:0?"]

    if plan.video_op is StreamOp.ENCODE:
        command += [
            "-c:v", "libx264",
            "-preset", options.preset,
            "-crf", str(options.crf),
            "-pix_fmt", "yuv420p",
        ]  # fmt: skip
    else:
        command += ["-c:v", "copy"]

    if plan.audio_op is StreamOp.ENCODE:
        command += ["-c:a", "aac", "-b:a", options.audio_bitrate]
    elif plan.audio_op is StreamOp.COPY:
        command += ["-c:a", "copy"]

    command += [
        "-threads", str(options.threads),
        "-movflags", "+faststart",
        "-f", "mp4",
        "-progress", "pipe:1",
        "-nostats",
        str(dst),
    ]  # fmt: skip
    return command


def parse_progress(line: str, duration: float | None) -> float | None:
    """Percent from an ffmpeg `-progress` line (out_time_us / out_time_ms are microseconds)."""
    key, _, value = line.strip().partition("=")
    if key not in ("out_time_us", "out_time_ms") or not duration or duration <= 0:
        return None
    try:
        seconds = int(value) / 1_000_000
    except ValueError:
        return None
    return max(0.0, min(100.0, 100.0 * seconds / duration))


def run(
    command: list[str],
    duration: float | None,
    on_progress: Callable[[float], None],
    on_activity: Callable[[], None],
    timeout: int,
) -> None:
    binary = shutil.which(command[0])
    if binary is None:
        raise EngineError(ErrorCode.PROCESSING, "ffmpeg is not installed.")
    process = subprocess.Popen(
        [binary, *command[1:]],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    stderr_chunks: list[str] = []
    reader = threading.Thread(
        target=lambda: stderr_chunks.append(process.stderr.read()), daemon=True
    )
    reader.start()
    deadline = time.monotonic() + timeout
    try:
        for line in process.stdout:
            percent = parse_progress(line, duration)
            if percent is not None:
                on_progress(percent)
            else:
                on_activity()
            if time.monotonic() > deadline:
                process.kill()
                raise EngineError(ErrorCode.PROCESSING, "ffmpeg did not finish in time.")
        process.wait(timeout=max(1, deadline - time.monotonic()))
    except subprocess.TimeoutExpired as exc:
        process.kill()
        raise EngineError(ErrorCode.PROCESSING, "ffmpeg did not finish in time.") from exc
    finally:
        reader.join(timeout=5)
    if process.returncode != 0:
        stderr = "".join(stderr_chunks)[-STDERR_TAIL:].strip()
        raise EngineError(ErrorCode.PROCESSING, f"ffmpeg: {stderr or 'unknown error'}")
