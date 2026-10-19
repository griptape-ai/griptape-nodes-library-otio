"""Placeholder media for the timeline, so every clip points at a real file. No engine imports.

Each video clip gets a slate: a still frame showing the clip's name, sequence, heading and description, encoded as a
small video. All audio clips share one silent audio file. Both are made with ffmpeg, from `static-ffmpeg`, which the
engine already depends on. A slate is padded with handles on both sides, so a clip can be lengthened in an editor
without running out of media.

Media made here is marked with a key starting "griptape:". Clips that point at media without that key (for example a
file from another tool) are left alone, and so are files already on disk: a generated file is never written over, and
its name holds a hash of its content, so changing a clip's text or length makes a new file beside the old one. Only
the OTIO's own metadata changes when a name or description is edited, never a file another timeline may use.
"""

from __future__ import annotations

import copy
import hashlib
import math
import subprocess
import tempfile
import textwrap
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import unquote, urlparse

from PIL import Image, ImageDraw, ImageFont

from otio_nodes.model import MEDIA_KEY_PREFIX

SLATE_SIZE = (1280, 720)
AUDIO_EXTENSIONS = (".wav", ".wave", ".mp3", ".aif", ".aiff", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma")
SILENCE_KEY = f"{MEDIA_KEY_PREFIX}silence"
DEFAULT_HANDLE_SECONDS = 10.0
FONT_CANDIDATES = (
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


class Encoder(Protocol):
    def slate(self, text: dict[str, str], path: Path, frames: int, rate: float) -> None: ...

    def silence(self, path: Path, frames: int, rate: float) -> None: ...


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default(size)


def draw_slate(text: dict[str, str], size: tuple[int, int] = SLATE_SIZE) -> Image.Image:
    """Draw the slate frame: title, subtitle and a wrapped description."""
    width, height = size
    image = Image.new("RGB", size, (22, 22, 26))
    draw = ImageDraw.Draw(image)
    margin = round(width * 0.05)
    draw.text(
        (margin, round(height * 0.10)), text.get("title", ""), font=_font(round(height * 0.08)), fill=(240, 240, 240)
    )
    draw.text(
        (margin, round(height * 0.24)), text.get("subtitle", ""), font=_font(round(height * 0.05)), fill=(214, 172, 92)
    )
    body_font = _font(round(height * 0.045))
    chars_per_line = max(10, round((width - 2 * margin) / (height * 0.045 * 0.55)))
    y = round(height * 0.38)
    for line in textwrap.wrap(text.get("body", ""), chars_per_line)[:10]:
        draw.text((margin, y), line, font=body_font, fill=(185, 185, 190))
        y += round(height * 0.065)
    return image


class FfmpegEncoder:
    """Make the slate and silence files with the ffmpeg that `static-ffmpeg` provides."""

    def __init__(self, ffmpeg: str | None = None) -> None:
        self._ffmpeg = ffmpeg

    def _executable(self) -> str:
        if self._ffmpeg is None:
            try:
                from static_ffmpeg import run  # type: ignore[import-untyped]

                self._ffmpeg = str(run.get_or_fetch_platform_executables_else_raise()[0])
            except Exception as e:
                msg = f"ffmpeg is not available, so placeholder media cannot be made: {e}"
                raise ValueError(msg) from e
        return self._ffmpeg

    def _run(self, args: list[str]) -> None:
        result = subprocess.run(
            [self._executable(), "-y", "-loglevel", "error", *args], capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            msg = f"ffmpeg failed: {result.stderr.strip() or 'no error text'}"
            raise ValueError(msg)

    def _run_with_progress(
        self,
        args: list[str],
        on_progress: Callable[[float], None] | None,
        seconds: float | None,
    ) -> None:
        """Run ffmpeg and report the fraction done (0 to 1) as it works, when the length `seconds` is known."""
        command = [self._executable(), "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1", *args]
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

    def proxy(
        self,
        source: Path,
        target: Path,
        on_progress: Callable[[float], None] | None = None,
        seconds: float | None = None,
    ) -> None:
        """A small copy of a video for the editor's viewer: 720p H.264 with a keyframe every half second, no B-frames
        and no audio. Browsers seek in it without trouble, which not every camera or generated file allows."""
        self._run_with_progress(
            [
                "-i", str(source), "-an", "-vf", "scale=-2:'min(720,ih)'", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "26", "-pix_fmt", "yuv420p", "-g", "12", "-keyint_min", "12", "-sc_threshold", "0", "-bf", "0",
                "-movflags", "+faststart", str(target),
            ],
            on_progress,
            seconds,
        )  # fmt: skip

    def audio_proxy(
        self,
        source: Path,
        target: Path,
        on_progress: Callable[[float], None] | None = None,
        seconds: float | None = None,
    ) -> None:
        """A copy of an audio file for the editor to play: AAC in an .m4a, which every browser plays and seeks in,
        whatever the original format (AIFF, for one, is not played everywhere)."""
        self._run_with_progress(
            ["-i", str(source), "-vn", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(target)],
            on_progress,
            seconds,
        )

    def slate(self, text: dict[str, str], path: Path, frames: int, rate: float) -> None:
        with tempfile.TemporaryDirectory() as folder:
            frame = Path(folder) / "slate.png"
            draw_slate(text).save(frame)
            self._run(
                [
                    "-loop",
                    "1",
                    "-framerate",
                    f"{rate:g}",
                    "-i",
                    str(frame),
                    "-frames:v",
                    str(frames),
                    "-c:v",
                    "libx264",
                    "-tune",
                    "stillimage",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "30",
                    "-pix_fmt",
                    "yuv420p",
                    "-g",
                    str(max(1, round(rate * 10))),
                    "-movflags",
                    "+faststart",
                    "-an",
                    str(path),
                ]  # fmt: skip
            )

    def silence(self, path: Path, frames: int, rate: float) -> None:
        self._run(
            [
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=48000:cl=mono",
                "-t",
                f"{frames / rate:.3f}",
                "-c:a",
                "aac",
                "-b:a",
                "32k",
                str(path),
            ]  # fmt: skip
        )


def url_to_path(url: str) -> Path:
    parsed = urlparse(url)
    return Path(unquote(parsed.path)) if parsed.scheme == "file" else Path(url)


def slate_text(clip: dict[str, Any]) -> dict[str, str]:
    meta = clip.get("meta", {})
    sequence = meta.get("sequence")
    parts = [f"SQ{sequence:02d}" if isinstance(sequence, int) else "", meta.get("heading", "")]
    return {
        "title": clip["name"],
        "subtitle": "  ".join(p for p in parts if p),
        "body": clip.get("description", ""),
    }


def _digest(*parts: Any) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:8]


def slate_key(text: dict[str, str], rate: float) -> str:
    digest = hashlib.sha1(f"{text}|{rate}|{SLATE_SIZE}".encode()).hexdigest()[:12]
    return f"{MEDIA_KEY_PREFIX}slate:{digest}"


def _is_foreign(clip: dict[str, Any]) -> bool:
    media = clip.get("media")
    return bool(media) and not str(media.get("key", "")).startswith(MEDIA_KEY_PREFIX)


def _covers(media: dict[str, Any] | None, clip: dict[str, Any], key: str) -> bool:
    return (
        bool(media)
        and media["key"] == key
        and url_to_path(media["url"]).exists()
        and media["start"] + clip["duration"] <= media["duration"]
    )


def ensure_media(
    model: dict[str, Any],
    folder: str | Path,
    handle_seconds: float = DEFAULT_HANDLE_SECONDS,
    encoder: Encoder | None = None,
) -> dict[str, Any]:
    """Return a copy of the model where every clip we own points at placeholder media in `folder`.

    Media that already exists and still covers its clip is kept. A slate is remade when the clip's text changes or
    the clip has grown past its handles. The folder is only created when something has to be made.
    """
    if handle_seconds < 0:
        msg = f"handle_seconds cannot be negative, got {handle_seconds}"
        raise ValueError(msg)
    result = copy.deepcopy(model)
    rate = float(result["rate"])
    handle = round(handle_seconds * rate)
    folder = Path(folder)
    encoder = encoder or FfmpegEncoder()

    audio_clips: list[dict[str, Any]] = []
    for track in result["tracks"]:
        for clip in track["clips"]:
            if _is_foreign(clip):
                continue
            if track["kind"] == "audio":
                audio_clips.append(clip)
                continue
            text = slate_text(clip)
            key = slate_key(text, rate)
            if _covers(clip.get("media"), clip, key):
                clip["media"].setdefault("shown", text)  # older timelines did not record what the slate shows
                continue
            frames = clip["duration"] + 2 * handle
            # The name holds a hash of what the file shows and its length, so a clip whose text or length changes gets a
            # new file. A file that exists is never written over: another timeline may still point at it.
            path = folder / f"slate_{clip['id']}_{_digest(text, rate, SLATE_SIZE, frames)}.mov"
            if not path.exists():
                folder.mkdir(parents=True, exist_ok=True)
                encoder.slate(text, path, frames, rate)
            clip["media"] = {
                "url": path.resolve().as_uri(),
                "start": handle,
                "duration": frames,
                "key": key,
                "shown": text,  # lets the editor tell when the clip's text has moved on from the file
            }

    if audio_clips and not all(_covers(c.get("media"), c, SILENCE_KEY) for c in audio_clips):
        frames = max(c["duration"] for c in audio_clips) + 2 * handle
        path = folder / f"silence_{rate:g}fps_{frames}f.mov"
        if not path.exists():
            folder.mkdir(parents=True, exist_ok=True)
            encoder.silence(path, frames, rate)
        for clip in audio_clips:
            clip["media"] = {"url": path.resolve().as_uri(), "start": handle, "duration": frames, "key": SILENCE_KEY}
    return result


def is_linked(media: dict[str, Any] | None) -> bool:
    """True for media a person linked: a file this library did not make."""
    return bool(media) and not str(media.get("key", "")).startswith(MEDIA_KEY_PREFIX)


def viewer_proxy_path(source: Path, folder: Path) -> Path:
    """Where the viewer copy of a video lives. The name holds a hash of the source's path, size and time, so a changed
    file gets its own copy and an existing copy is never written over."""
    info = source.stat()
    token = hashlib.sha1(f"{source.resolve()}|{info.st_size}|{info.st_mtime_ns}".encode()).hexdigest()[:10]  # noqa: S324
    suffix = ".m4a" if source.suffix.lower() in AUDIO_EXTENSIONS else ".mp4"
    return folder / f"{source.stem}_{token}{suffix}"


def make_viewer_proxy(
    source: Path,
    target: Path,
    encoder: FfmpegEncoder | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> None:
    """Make the viewer copy at `target`, which appears whole or not at all. The source is only read."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.parent / f".{target.stem}.partial{target.suffix}"
    encoder = encoder or FfmpegEncoder()
    make = encoder.audio_proxy if target.suffix == ".m4a" else encoder.proxy
    try:
        make(source, partial, on_progress, ffprobe_seconds(source))
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)


def linked_files(model: dict[str, Any], resolve: Callable[[str], Path]) -> dict[str, Path]:
    """The files linked to clips, as {address typed in the clip: path}. Missing files and addresses that cannot be
    resolved are left out. Media this library made is not included."""
    found: dict[str, Path] = {}
    for track in model.get("tracks", []):
        for clip in track.get("clips", []):
            media = clip.get("media")
            if not is_linked(media) or media["url"] in found:
                continue
            try:
                path = resolve(media["url"])
            except Exception:  # noqa: BLE001
                continue
            if path.is_file():
                found[media["url"]] = path
    return found


def ffprobe_seconds(path: Path) -> float | None:
    """The length of a media file in seconds, or None if it cannot be measured (a still image, or no ffprobe)."""
    try:
        from static_ffmpeg import run  # type: ignore[import-untyped]

        ffprobe = str(run.get_or_fetch_platform_executables_else_raise()[1])
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        return float(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip() else None
    except Exception:
        return None


def link_media(
    model: dict[str, Any],
    resolve: Callable[[str], Path],
    probe: Callable[[Path], float | None] = ffprobe_seconds,
) -> dict[str, Any]:
    """Return a copy of the model where every linked clip points at a checked, measured file.

    A person links a clip to a file by typing a path in the editor: a plain path, a file:// address or a project
    macro such as {inputs}/plate.mov. `resolve` turns that into a path on disk. The file must exist. Its length is
    measured with `probe`, so a clip longer than its file is reported instead of going offline in an editor. A length
    that cannot be measured is left unknown. Media this library made is left as it is.
    """
    result = copy.deepcopy(model)
    rate = float(result["rate"])
    missing: list[str] = []
    for track in result["tracks"]:
        for clip in track["clips"]:
            media = clip.get("media")
            if not is_linked(media):
                continue
            try:
                path = resolve(str(media["url"]))
            except Exception as e:
                missing.append(f"clip '{clip['name']}': {media['url']} ({e})")
                continue
            if not path.is_file():
                missing.append(f"clip '{clip['name']}': {media['url']}")
                continue
            seconds = probe(path)
            media["url"] = path.resolve().as_uri()
            media["start"] = max(0, round(media.get("start") or 0))
            media["duration"] = math.floor(seconds * rate + 1e-6) if seconds is not None else media.get("duration")
    if missing:
        msg = "Linked media was not found, so nothing was saved:\n- " + "\n- ".join(missing)
        raise ValueError(msg)
    return result


def restore_linked_urls(resolved: dict[str, Any], typed: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of `resolved` where each linked clip has the path it was given, not the absolute one.

    Saving needs absolute file:// addresses, because programs other than this engine read the OTIO. The editor keeps
    what a person typed ({inputs}/plate.mov), so the path still works if the project moves.
    """
    result = copy.deepcopy(resolved)
    given = {c["id"]: c["media"]["url"] for t in typed["tracks"] for c in t["clips"] if is_linked(c.get("media"))}
    for track in result["tracks"]:
        for clip in track["clips"]:
            if clip["id"] in given and is_linked(clip.get("media")):
                clip["media"]["url"] = given[clip["id"]]
    return result
