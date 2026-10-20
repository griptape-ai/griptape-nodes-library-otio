"""Render a timeline to a movie with ffmpeg. No engine imports.

The picture is built from the clips on the video tracks. Each enabled clip with a file is cut to the part of the file
it shows, fitted to the frame size and laid at its place on a black background, so gaps are black and a later track
covers an earlier one. A clip that outlasts its file holds the last frame. The sound is every enabled clip that has an
audio stream (audio tracks, and video clips that carry sound), each delayed to its place and mixed at full level.
Gaps are silent. Placeholder slates are drawn like any other video, so a timeline with no real footage renders as an
animatic. The mute buttons in the editor are not saved with the timeline, so they do not apply here.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from otio_nodes.media import SILENCE_KEY
from otio_nodes.model import total_frames

AUDIO_RATE = 48000
DEFAULT_SIZE = (1280, 720)
DEFAULT_CRF = 20


@dataclass(frozen=True)
class RenderSettings:
    width: int = DEFAULT_SIZE[0]
    height: int = DEFAULT_SIZE[1]
    crf: int = DEFAULT_CRF
    include_slates: bool = True


def _seconds(frames: float, rate: float) -> str:
    return f"{frames / rate:.6f}"


def clips_to_render(
    model: dict[str, Any],
    resolve: Callable[[str], Path],
    settings: RenderSettings,
) -> list[tuple[dict[str, Any], str, Path]]:
    """The enabled clips that have a file on disk, as (clip, track kind, path), in track order.

    Clips without media, or whose file is missing, are left out and so render as black and silence.
    """
    found = []
    for track in model["tracks"]:
        for clip in track["clips"]:
            media = clip.get("media")
            if clip.get("enabled") is False or not media or not media.get("url"):
                continue
            key = str(media.get("key") or "")
            if key == SILENCE_KEY or (key.startswith("griptape:") and not settings.include_slates):
                continue
            try:
                path = resolve(str(media["url"]))
            except Exception:  # noqa: BLE001
                continue
            if path.is_file():
                found.append((clip, track["kind"], path))
    return found


def build_args(
    model: dict[str, Any],
    files: list[tuple[dict[str, Any], str, Path]],
    has_audio: Callable[[Path], bool],
    settings: RenderSettings,
    output: Path,
) -> list[str]:
    """The ffmpeg arguments that render `files` (from `clips_to_render`) to `output`."""
    rate = float(model["rate"])
    total = _seconds(total_frames(model), rate)
    width, height = settings.width, settings.height
    args: list[str] = []
    graph: list[str] = [f"color=c=black:s={width}x{height}:r={rate:g}:d={total}[v0]"]
    layers = 0
    sounds: list[str] = []
    for index, (clip, kind, path) in enumerate(files):
        args += ["-i", str(path)]
        media = clip["media"]
        begin = _seconds(media.get("start") or 0, rate)
        length = _seconds(clip["duration"], rate)
        delay = _seconds(clip["start"], rate)
        if kind == "video":
            layers += 1
            graph.append(
                f"[{index}:v]trim=start={begin},setpts=PTS-STARTPTS,fps={rate:g},"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                f"tpad=stop_mode=clone:stop_duration={total},trim=duration={length},"
                f"setpts=PTS-STARTPTS+{delay}/TB[c{layers}]"
            )
            graph.append(f"[v{layers - 1}][c{layers}]overlay=eof_action=pass:format=auto[v{layers}]")
        if has_audio(path):
            sounds.append(
                f"[{index}:a]atrim=start={begin}:duration={length},asetpts=PTS-STARTPTS,"
                f"aresample={AUDIO_RATE},aformat=channel_layouts=stereo,"
                f"adelay={round(clip['start'] / rate * 1000)}:all=1[s{len(sounds)}]"
            )
    graph.extend(sounds)
    if sounds:
        mixed = "".join(f"[s{i}]" for i in range(len(sounds)))
        graph.append(
            f"{mixed}amix=inputs={len(sounds)}:normalize=0:duration=longest,"
            f"apad=whole_dur={total},atrim=duration={total}[a]"
        )
    else:
        graph.append(f"anullsrc=r={AUDIO_RATE}:cl=stereo,atrim=duration={total}[a]")
    graph.append(f"[v{layers}]format=yuv420p[v]")
    return [
        *args,
        "-filter_complex", ";".join(graph),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(settings.crf),
        "-c:a", "aac", "-b:a", "192k",
        "-t", total,
        "-movflags", "+faststart",
        str(output),
    ]  # fmt: skip


def ffprobe_has_audio(path: Path) -> bool:
    """True if the file has an audio stream. False if it has none or cannot be probed."""
    try:
        from static_ffmpeg import run  # type: ignore[import-untyped]

        ffprobe = str(run.get_or_fetch_platform_executables_else_raise()[1])
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:  # noqa: BLE001
        return False
    return result.returncode == 0 and "audio" in result.stdout


def ffmpeg_path() -> str:
    try:
        from static_ffmpeg import run  # type: ignore[import-untyped]

        return str(run.get_or_fetch_platform_executables_else_raise()[0])
    except Exception as e:
        msg = f"ffmpeg is not available, so the movie cannot be rendered: {e}"
        raise ValueError(msg) from e


def run_ffmpeg(args: list[str], on_progress: Callable[[float], None] | None, seconds: float) -> None:
    """Run ffmpeg with `args`, reporting the fraction done (0 to 1) as it works."""
    command = [ffmpeg_path(), "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1", *args]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:  # noqa: S603
        assert process.stdout is not None  # noqa: S101
        for line in process.stdout:
            key, _, value = line.strip().partition("=")
            if on_progress and seconds and key == "out_time_us" and value.lstrip("-").isdigit():
                on_progress(min(1.0, max(0.0, int(value) / 1_000_000 / seconds)))
        error = process.stderr.read() if process.stderr else ""
    if process.returncode != 0:
        msg = f"ffmpeg failed: {error.strip() or 'no error text'}"
        raise ValueError(msg)


def render_movie(
    model: dict[str, Any],
    resolve: Callable[[str], Path],
    output: Path,
    settings: RenderSettings | None = None,
    *,
    has_audio: Callable[[Path], bool] = ffprobe_has_audio,
    on_progress: Callable[[float], None] | None = None,
) -> int:
    """Render the timeline to `output` (an .mp4) and return how many clips contributed footage or sound."""
    settings = settings or RenderSettings()
    if settings.width < 2 or settings.height < 2 or settings.width % 2 or settings.height % 2:
        msg = f"The width and height must be even numbers of at least 2, got {settings.width}x{settings.height}."
        raise ValueError(msg)
    frames = total_frames(model)
    if frames < 1:
        msg = "The timeline has no clips, so there is nothing to render."
        raise ValueError(msg)
    files = clips_to_render(model, resolve, settings)
    args = build_args(model, files, has_audio, settings, output)
    run_ffmpeg(args, on_progress, frames / float(model["rate"]))
    return len(files)
