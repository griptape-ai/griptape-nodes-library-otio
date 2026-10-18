"""Helpers shared by the nodes: input cleanup and the text summaries they show. No engine imports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from otio_nodes.media import DEFAULT_HANDLE_SECONDS, Encoder, ensure_media
from otio_nodes.model import total_frames, validate_model
from otio_nodes.otio_io import to_json


def parse_cue_lines(text: str | None) -> list[str]:
    """Turn a multi-line text box into shot cues: one per line, blanks dropped, capitalised."""
    return [line.strip().upper() for line in (text or "").splitlines() if line.strip()]


def format_runtime(frames: int, rate: float) -> str:
    seconds = frames / rate if rate else 0.0
    minutes, rest = divmod(seconds, 60)
    return f"{int(minutes)}:{rest:04.1f} ({seconds:.1f} s)"


def script_summary(parsed: dict[str, Any]) -> str:
    elements = parsed["elements"]
    counts: dict[str, int] = {}
    for element in elements:
        counts[element["type"]] = counts.get(element["type"], 0) + 1
    speakers = sorted({e["character"] for e in elements if e["type"] == "dialogue"})
    lines = [
        f"Title: {parsed['title_page'].get('Title', '(none)')}",
        f"Scenes: {sum(1 for s in parsed['scenes'] if s['heading'])}",
        f"Dialogue blocks: {counts.get('dialogue', 0)}",
        f"Action blocks: {counts.get('action', 0)}",
        f"Transitions: {counts.get('transition', 0)}",
        f"Speakers: {', '.join(speakers) if speakers else '(none)'}",
    ]
    if parsed["notes"]:
        lines.append(f"Notes outside any block: {len(parsed['notes'])}")
    return "\n".join(lines)


def timeline_summary(model: dict[str, Any]) -> str:
    rate = float(model["rate"])
    tracks = model["tracks"]
    shots = [c for t in tracks if t["role"] == "shots" for c in t["clips"]]
    sequences = {c["meta"].get("sequence") for c in shots if c["meta"].get("sequence") is not None}
    lines = [
        f"Title: {model.get('title') or '(none)'}",
        f"Runtime: {format_runtime(total_frames(model), rate)} at {rate:g} fps",
        f"Shots: {len(shots)}" + (f" in {len(sequences)} sequences" if sequences else ""),
    ]
    for track in tracks:
        if track["role"] != "shots":
            lines.append(f"Track '{track['name']}': {len(track['clips'])} clips")
    for warning in model.get("warnings", []):
        lines.append(f"Warning: {warning}")
    return "\n".join(lines)


MEDIA_FOLDER = "media"


def clean_file_name(name: str) -> str:
    """Return a safe file stem: no folders, no .otio extension, never empty."""
    stem = (name or "").strip()
    if stem.lower().endswith(".otio"):
        stem = stem[: -len(".otio")].strip()
    if "/" in stem or "\\" in stem:
        msg = f"'File Name' cannot contain slashes (got '{name}'). Use the folder setting to choose a folder."
        raise ValueError(msg)
    return stem or "timeline"


def save_timeline(
    model: dict[str, Any],
    folder: str | Path,
    file_name: str = "timeline",
    *,
    make_media: bool = True,
    handle_seconds: float = DEFAULT_HANDLE_SECONDS,
    encoder: Encoder | None = None,
) -> tuple[str, dict[str, Any]]:
    """Write the timeline as `<folder>/<file_name>.otio` and return that path and the saved model.

    The timeline is checked before anything is written. With `make_media`, placeholder media is made in
    `<folder>/media` first, and the returned model records it, so later saves reuse it. An existing file of the same
    name is replaced.
    """
    validate_model(model)
    stem = clean_file_name(file_name)
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    if make_media:
        model = ensure_media(model, target / MEDIA_FOLDER, handle_seconds, encoder)
    path = target / f"{stem}.otio"
    path.write_text(to_json(model), encoding="utf-8")
    return str(path), model


def save_through_destination(
    model: dict[str, Any],
    destination: Any,
    *,
    make_media: bool = True,
    handle_seconds: float = DEFAULT_HANDLE_SECONDS,
    encoder: Encoder | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Write the timeline as OTIO through a file destination and return the saved path and the saved model.

    The media goes in a `media` folder next to the file, so the file's folder has to be known before it is written. A
    destination with an explicit path (one that overwrites) can say where it is going. One whose name the project
    settles at write time (a version number is added then) cannot, so the file is written once to settle the name, then
    the media is made and the same file is overwritten with clips that point at it.
    """
    validate_model(model)
    try:
        folder = Path(destination.resolve()).parent
    except Exception:
        folder = None

    if folder is not None:
        if make_media:
            model = ensure_media(model, folder / MEDIA_FOLDER, handle_seconds, encoder)
        saved = destination.write_text(to_json(model))
        return Path(saved.resolve()), model

    saved = destination.write_text(to_json(model))
    path = Path(saved.resolve())
    if make_media:
        model = ensure_media(model, path.parent / MEDIA_FOLDER, handle_seconds, encoder)
        saved.write_text(to_json(model))
    return path, model
