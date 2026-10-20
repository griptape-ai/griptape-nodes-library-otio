"""Render a timeline to a movie with ffmpeg. No engine imports.

The picture is built from the clips on the video tracks. Each enabled clip with a file is cut to the part of the file
it shows, fitted to the frame size and laid at its place on a black background, so gaps are black and a later track
covers an earlier one. A clip that outlasts its file holds the last frame. The sound is every enabled clip that has an
audio stream (audio tracks, and video clips that carry sound), each delayed to its place and mixed at full level.
Gaps are silent. Placeholder slates are drawn like any other video, so a timeline with no real footage renders as an
animatic. The spoken lines are drawn as subtitles, as in the editor's viewer. The mute buttons in the editor are not saved with the timeline, so they do not apply here.
"""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from otio_nodes.media import SILENCE_KEY, _font
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
    show_dialogue: bool = True


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


Caption = tuple[int, int, Path]  # first frame, end frame, picture


def caption_segments(model: dict[str, Any]) -> list[tuple[int, int, list[tuple[str, str]]]]:
    """The spoken lines as (first frame, end frame, [(speaker, text)]). Lines that overlap in time share a segment."""
    lines = []
    for track in model["tracks"]:
        for clip in track["clips"]:
            meta = clip.get("meta") or {}
            if meta.get("kind") != "dialogue" or clip.get("enabled") is False:
                continue
            who = f"{meta.get('character') or clip['name']}" + (
                f" ({meta['extension']})" if meta.get("extension") else ""
            )
            lines.append(
                (clip["start"], clip["start"] + clip["duration"], who, clip.get("description") or clip["name"])
            )
    edges = sorted({edge for line in lines for edge in line[:2]})
    segments = []
    for first, last in zip(edges, edges[1:], strict=False):
        active = [(who, text) for start, end, who, text in lines if start <= first and last <= end]
        if active:
            segments.append((first, last, active))
    return segments


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: Any, first_width: float, width: float) -> list[str]:
    """Break `text` into lines that fit; the first line has less room because the speaker's name is beside it."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and draw.textlength(trial, font=font) > (first_width if not lines else width):
            lines.append(current)
            current = word
        else:
            current = trial
    return [*lines, current]


def draw_caption(lines: list[tuple[str, str]], size: tuple[int, int]) -> Image.Image:
    """A transparent picture of the size of the frame with the lines as subtitles at the bottom. The speaker is gold."""
    width, height = size
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = _font(max(12, round(height * 0.045)))
    margin = round(width * 0.06)
    room = width - 2 * margin
    rows: list[tuple[str, str]] = []  # (speaker label on this row, text on this row)
    for who, text in lines:
        label = f"{who}: "
        pieces = _wrap(draw, text, font, room - draw.textlength(label, font=font), room)
        rows.extend((label if index == 0 else "", piece) for index, piece in enumerate(pieces))
    step = round(height * 0.062)
    top = height - round(height * 0.06) - step * len(rows)
    draw.rounded_rectangle(
        (margin - 12, top - 8, width - margin + 12, top + step * len(rows) + 4), radius=8, fill=(0, 0, 0, 170)
    )
    for index, (label, piece) in enumerate(rows):
        y = top + index * step
        draw.text((margin, y), label, font=font, fill=(214, 172, 92, 255))
        draw.text((margin + draw.textlength(label, font=font), y), piece, font=font, fill=(240, 240, 240, 255))
    return image


def make_captions(model: dict[str, Any], settings: RenderSettings, folder: Path) -> list[Caption]:
    if not settings.show_dialogue:
        return []
    captions = []
    for index, (first, last, lines) in enumerate(caption_segments(model)):
        path = folder / f"caption-{index:04d}.png"
        draw_caption(lines, (settings.width, settings.height)).save(path)
        captions.append((first, last, path))
    return captions


def build_args(
    model: dict[str, Any],
    files: list[tuple[dict[str, Any], str, Path]],
    has_audio: Callable[[Path], bool],
    settings: RenderSettings,
    output: Path,
    captions: list[Caption] | None = None,
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
    for number, (first, last, picture) in enumerate(captions or []):
        index = len(files) + number
        args += ["-loop", "1", "-framerate", f"{rate:g}", "-t", total, "-i", str(picture)]
        layers += 1
        graph.append(
            f"[v{layers - 1}][{index}:v]overlay=enable='between(t,{_seconds(first, rate)},{_seconds(last, rate)})'"
            f":format=auto:shortest=0[v{layers}]"
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
    with tempfile.TemporaryDirectory() as folder:
        args = build_args(model, files, has_audio, settings, output, make_captions(model, settings, Path(folder)))
        run_ffmpeg(args, on_progress, frames / float(model["rate"]))
    return len(files)
