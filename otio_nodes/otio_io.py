"""Convert the editable timeline dict to and from an OpenTimelineIO timeline, and read and write .otio files.

Everything this library adds goes under one namespaced metadata key, never a custom schema, so any OTIO reader can
open the file. Clips point at placeholder media (see media.py) with an ExternalReference. A clip with no media falls back to a
MissingReference, which editors report as offline. Shot clips on the
"Shots" track, spoken lines on one audio track per speaker. Sequence, scene and note markers are derived from the shots
when writing and dropped when reading, so they always match the clips. No engine imports.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import opentimelineio as otio

from otio_nodes.model import (
    AUDIO_ROLE,
    DIALOGUE_ROLE,
    SHOTS_ROLE,
    derive_markers,
    validate_model,
)

METADATA_KEY = "griptape_otio"
SCHEMA_VERSION = 1
DERIVED_MARKER_KINDS = ("sequence", "scene", "note")
MARKER_COLORS = [name for name in dir(otio.schema.MarkerColor) if name.isupper()]


def _time(frame: float, rate: float) -> otio.opentime.RationalTime:
    return otio.opentime.RationalTime(frame, rate)


def _range(start: float, duration: float, rate: float) -> otio.opentime.TimeRange:
    return otio.opentime.TimeRange(_time(start, rate), _time(duration, rate))


def _frames(time: otio.opentime.RationalTime, rate: float) -> int:
    return round(time.rescaled_to(rate).value)


def _plain(value: Any) -> Any:
    """Deep-copy OTIO metadata into plain dicts and lists. OTIO's containers die with the timeline that owns them."""
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [_plain(v) for v in value]
    return value


def _marker_color(name: str) -> str:
    return name if name in MARKER_COLORS else otio.schema.MarkerColor.RED


def model_to_otio(model: dict[str, Any]) -> otio.schema.Timeline:
    """Build an OTIO timeline from a validated model. Gaps stand in for empty space between clips."""
    validate_model(model)
    rate = float(model["rate"])

    timeline = otio.schema.Timeline(name=model.get("title", ""))
    timeline.global_start_time = _time(0, rate)
    timeline.metadata[METADATA_KEY] = {
        "schema": SCHEMA_VERSION,
        "rate": rate,
        "title_page": dict(model.get("title_page", {})),
        "settings": dict(model.get("settings", {})),
    }

    for track in model["tracks"]:
        kind = otio.schema.TrackKind.Video if track["kind"] == "video" else otio.schema.TrackKind.Audio
        otio_track = otio.schema.Track(name=track["name"], kind=kind)
        otio_track.metadata[METADATA_KEY] = {"id": track["id"], "role": track["role"]}
        cursor = 0
        for clip in sorted(track["clips"], key=lambda c: c["start"]):
            if clip["start"] > cursor:
                otio_track.append(otio.schema.Gap(source_range=_range(0, clip["start"] - cursor, rate)))
            otio_track.append(_to_otio_clip(clip, rate))
            cursor = clip["start"] + clip["duration"]
        timeline.tracks.append(otio_track)

    host = next((t for t in timeline.tracks if t.metadata[METADATA_KEY]["role"] == SHOTS_ROLE), None)
    if host is None and len(timeline.tracks):
        host = timeline.tracks[0]
    if host is not None:
        for marker in derive_markers(model) + list(model.get("markers", [])):
            host.markers.append(_to_otio_marker(marker, rate))
    return timeline


def _to_otio_clip(clip: dict[str, Any], rate: float) -> otio.schema.Clip:
    media = clip.get("media")
    if media:
        known = media.get("duration") is not None
        reference: otio.core.MediaReference = otio.schema.ExternalReference(
            target_url=media["url"], available_range=_range(0, media["duration"], rate) if known else None
        )
        source_range = _range(media["start"], clip["duration"], rate)
    else:
        source_range = _range(0, clip["duration"], rate)
        reference = otio.schema.MissingReference(name=clip["name"], available_range=source_range)
    details: dict[str, Any] = {
        "id": clip["id"],
        "description": clip.get("description", ""),
        "color": clip.get("color", ""),
        **clip.get("meta", {}),
    }
    if media:
        details["media_key"] = media.get("key", "")
        if media.get("shown") is not None:
            details["media_shown"] = media["shown"]
    otio_clip = otio.schema.Clip(
        name=clip["name"], media_reference=reference, source_range=source_range, metadata={METADATA_KEY: details}
    )
    otio_clip.enabled = bool(clip.get("enabled", True))
    if clip.get("color"):
        otio_clip.color = otio.core.Color.from_hex(clip["color"])
    return otio_clip


def _to_otio_marker(marker: dict[str, Any], rate: float) -> otio.schema.Marker:
    return otio.schema.Marker(
        name=marker["name"],
        marked_range=_range(marker["start"], marker["duration"], rate),
        color=_marker_color(marker.get("color", "")),
        comment=marker.get("comment", ""),
        metadata={METADATA_KEY: {"id": marker["id"], "kind": marker.get("kind", "user")}},
    )


def otio_to_model(timeline: otio.schema.Timeline) -> dict[str, Any]:
    """Build the editable model from any OTIO timeline. Files written by this library restore fully.

    For other files, clips keep their names and positions, and tracks get a default role. Transitions, nested stacks
    and clip-level markers are not represented. They are listed under "warnings" and dropped.
    """
    own = _plain(timeline.metadata.get(METADATA_KEY, {}))
    rate = float(own.get("rate") or _first_rate(timeline) or 24.0)
    warnings: list[str] = []
    if len(timeline.tracks.markers):
        warnings.append(f"Dropped {len(timeline.tracks.markers)} marker(s) set on the whole timeline.")
    used_ids: set[str] = set()

    def unique(wanted: str | None, fallback: str) -> str:
        candidate = wanted or fallback
        while candidate in used_ids:
            candidate += "-dup"
        used_ids.add(candidate)
        return candidate

    tracks: list[dict[str, Any]] = []
    markers: list[dict[str, Any]] = []
    clip_count = 0
    for position, track in enumerate(timeline.tracks, start=1):
        if not isinstance(track, otio.schema.Track):
            warnings.append(f"Skipped nested {type(track).__name__} '{track.name}'.")
            continue
        info = _plain(track.metadata.get(METADATA_KEY, {}))
        is_video = track.kind == otio.schema.TrackKind.Video
        default_role = SHOTS_ROLE if is_video else (DIALOGUE_ROLE if position > 1 else AUDIO_ROLE)
        clips: list[dict[str, Any]] = []
        for child in track:
            if isinstance(child, otio.schema.Clip):
                clip_count += 1
                if len(child.markers):
                    warnings.append(f"Dropped {len(child.markers)} marker(s) on clip '{child.name}'.")
                try:
                    clip_model = _from_otio_clip(child, rate, f"clip-{clip_count}")
                except otio.exceptions.OTIOError as e:
                    warnings.append(f"Skipped clip '{child.name}' on track '{track.name}': {e}")
                    continue
                clip_model["id"] = unique(clip_model["id"], f"clip-{clip_count}")
                clips.append(clip_model)
            elif isinstance(child, otio.schema.Transition):
                warnings.append(f"Dropped transition '{child.name}' on track '{track.name}'.")
            elif not isinstance(child, otio.schema.Gap):
                warnings.append(f"Skipped nested {type(child).__name__} '{child.name}' on track '{track.name}'.")
        tracks.append(
            {
                "id": unique(info.get("id"), f"track-{position}"),
                "name": track.name or f"Track {position}",
                "kind": "video" if is_video else "audio",
                "role": info.get("role", default_role),
                "clips": clips,
            }
        )
        for marker in track.markers:
            marker_info = _plain(marker.metadata.get(METADATA_KEY, {}))
            kind = marker_info.get("kind", "user")
            if kind in DERIVED_MARKER_KINDS:
                continue
            markers.append(
                {
                    "id": unique(marker_info.get("id"), f"marker-{len(markers) + 1}"),
                    "name": marker.name,
                    "start": _frames(marker.marked_range.start_time, rate),
                    "duration": max(1, _frames(marker.marked_range.duration, rate)),
                    "color": marker.color,
                    "comment": marker.comment,
                }
            )

    model: dict[str, Any] = {
        "title": timeline.name,
        "title_page": dict(own.get("title_page", {})),
        "rate": rate,
        "settings": dict(own.get("settings", {})),
        "tracks": tracks,
        "markers": markers,
    }
    if warnings:
        model["warnings"] = warnings
    return model


def _first_rate(timeline: otio.schema.Timeline) -> float | None:
    for clip in timeline.find_clips():
        if clip.source_range is not None:
            return clip.source_range.duration.rate
    return None


def _from_otio_clip(clip: otio.schema.Clip, rate: float, fallback_id: str) -> dict[str, Any]:
    info = _plain(clip.metadata.get(METADATA_KEY, {}))
    in_parent = clip.range_in_parent()
    meta = {k: v for k, v in info.items() if k not in ("id", "description", "color", "media_key", "media_shown")}
    media = None
    reference = clip.media_reference
    if isinstance(reference, otio.schema.ExternalReference):
        available = reference.available_range
        start = _frames(clip.source_range.start_time, rate) if clip.source_range is not None else 0
        if available is not None:
            start -= _frames(available.start_time, rate)  # media.start counts from the first frame of the file
        media = {
            "url": reference.target_url,
            "start": start,
            "duration": _frames(available.duration, rate)
            if available is not None
            else start + max(1, _frames(in_parent.duration, rate)),
            "key": info.get("media_key", ""),
        }
        if info.get("media_shown") is not None:
            media["shown"] = info["media_shown"]
    color = info.get("color")
    if color is None and clip.color is not None:
        color = clip.color.to_hex()
    return {
        "id": info.get("id") or fallback_id,
        "name": clip.name,
        "start": _frames(in_parent.start_time, rate),
        "duration": max(1, _frames(in_parent.duration, rate)),
        "description": info.get("description", ""),
        "color": color or "",
        "enabled": clip.enabled,
        "media": media,
        "meta": meta,
    }


def to_json(model: dict[str, Any]) -> str:
    return otio.adapters.write_to_string(model_to_otio(model), "otio_json")


def from_json(text: str) -> dict[str, Any]:
    return otio_to_model(_as_timeline(otio.adapters.read_from_string(text, "otio_json")))


def write_otio(model: dict[str, Any], path: str | Path) -> Path:
    """Write the model as an .otio file at `path`. Raises if the file exists, so versions are never overwritten."""
    target = Path(path)
    if target.exists():
        msg = f"{target} already exists. Choose a new version name instead of overwriting."
        raise FileExistsError(msg)
    target.parent.mkdir(parents=True, exist_ok=True)
    otio.adapters.write_to_file(model_to_otio(model), str(target), "otio_json")
    return target


def read_otio(path: str | Path) -> dict[str, Any]:
    return otio_to_model(_as_timeline(otio.adapters.read_from_file(str(path), "otio_json")))


def _as_timeline(obj: Any) -> otio.schema.Timeline:
    if isinstance(obj, otio.schema.Timeline):
        return obj
    msg = f"Expected an OTIO Timeline, got {type(obj).__name__}"
    raise ValueError(msg)


def next_version_path(directory: str | Path, stem: str, suffix: str = ".otio") -> Path:
    """Return directory/stem_v001.otio, or the next free version number."""
    folder = Path(directory)
    version = 1
    while (folder / f"{stem}_v{version:03d}{suffix}").exists():
        version += 1
    return folder / f"{stem}_v{version:03d}{suffix}"
