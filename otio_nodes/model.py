"""The editable timeline: a plain JSON-friendly dict that the widget edits and that converts to and from OTIO.

    {"title", "rate", "settings", "title_page",
     "tracks": [{"id", "name", "kind": "video" | "audio", "role": "shots" | "dialogue" | "sfx" | "audio",
                 "clips": [{"id", "name", "start", "duration", "description", "color", "enabled", "meta", "media"}]}],
     "markers": [{"id", "name", "start", "duration", "color", "comment"}]}

Times are whole frames at `rate`. A clip's `start` is its absolute position on the timeline. `markers` holds only
user markers. Sequence, scene and note markers are derived from the shot clips each time they are needed, so
editing a shot's length keeps them in step. A clip's `media` is None, or {"url", "start", "duration", "key"}: the
file it points at, where the clip begins in that file, and the file's length, in frames. The length is None when it is
not known yet, as for media a person linked in the editor (its `key` is empty), which is measured when it is saved. A
placeholder slate also has `shown`: the title, subtitle and body it was drawn with, so the editor can tell when the
clip's text has changed since the file was made. No engine imports.
"""

from __future__ import annotations

from typing import Any

from otio_nodes.breakdown import BreakdownSettings

SHOTS_ROLE = "shots"
DIALOGUE_ROLE = "dialogue"
SFX_ROLE = "sfx"
AUDIO_ROLE = "audio"
ROLES = (SHOTS_ROLE, DIALOGUE_ROLE, SFX_ROLE, AUDIO_ROLE)
KINDS = ("video", "audio")
MEDIA_KEY_PREFIX = "griptape:"

SHOT_COLORS = {"INT": "#d9a441", "EXT": "#4f9d69", "NIGHT": "#4a5a9a", "OTHER": "#8a8a8a"}
SPEAKER_PALETTE = ["#c8553d", "#3d7ec8", "#8f5fc0", "#3aa6a0", "#c08a3a", "#6e8f3a"]
USER_CLIP_COLOR = "#cfcfcf"


def shot_color(int_ext: str, time_of_day: str) -> str:
    if time_of_day.upper() == "NIGHT":
        return SHOT_COLORS["NIGHT"]
    return SHOT_COLORS.get(int_ext.upper(), SHOT_COLORS["OTHER"])


def frames(seconds: float, rate: float) -> int:
    return max(1, round(seconds * rate))


def speaker_track_name(line: dict[str, Any]) -> str:
    extension = f" ({line['extension']})" if line.get("extension") else ""
    return f"{line['character']}{extension}"


def truncate(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def shot_name(shot: dict[str, Any]) -> str:
    label = shot["cue"].title() if shot["cue"] else "Shot"
    return f"{shot['index']:03d} {label}"


def build_model(broken_down: dict[str, Any]) -> dict[str, Any]:
    """Lay the shots end to end on one video track, with each spoken line on its speaker's audio track."""
    settings = BreakdownSettings.from_dict(broken_down["settings"])
    rate = settings.rate

    shot_clips: list[dict[str, Any]] = []
    speaker_clips: dict[str, list[dict[str, Any]]] = {}
    line_count = 0
    cursor = 0
    for shot in broken_down["shots"]:
        offsets = []
        offset = 0
        for line in shot["dialogue"]:
            length = frames(line["seconds"], rate)
            offsets.append((offset, length))
            offset += length
        duration = max(frames(shot["seconds"], rate), offset)

        shot_id = f"shot-{shot['index']:03d}"
        shot_clips.append(
            {
                "id": shot_id,
                "name": shot_name(shot),
                "start": cursor,
                "duration": duration,
                "description": shot["description"],
                "color": shot_color(shot["int_ext"], shot["time_of_day"]),
                "enabled": True,
                "media": None,
                "meta": {
                    "kind": "shot",
                    "sequence": shot["sequence"],
                    "scene": shot["scene"],
                    "heading": shot["heading"],
                    "int_ext": shot["int_ext"],
                    "location": shot["location"],
                    "time_of_day": shot["time_of_day"],
                    "scene_number": shot["scene_number"],
                    "transition": shot.get("transition", ""),
                    "cue": shot["cue"],
                    "notes": list(shot["notes"]),
                    "line_start": shot["line_start"],
                    "line_end": shot["line_end"],
                },
            }
        )
        for line, (line_offset, length) in zip(shot["dialogue"], offsets, strict=True):
            line_count += 1
            speaker_clips.setdefault(speaker_track_name(line), []).append(
                {
                    "id": f"line-{line_count:03d}",
                    "name": truncate(line["text"]),
                    "start": cursor + line_offset,
                    "duration": length,
                    "description": line["text"],
                    "color": "",
                    "enabled": True,
                    "media": None,
                    "meta": {
                        "kind": "dialogue",
                        "character": line["character"],
                        "extension": line["extension"],
                        "shot": shot_id,
                        "parentheticals": list(line["parentheticals"]),
                        "line_start": line["line_start"],
                        "line_end": line["line_end"],
                    },
                }
            )
        cursor += duration

    tracks: list[dict[str, Any]] = [
        {"id": "track-shots", "name": "Shots", "kind": "video", "role": SHOTS_ROLE, "clips": shot_clips}
    ]
    for position, (name, clips) in enumerate(speaker_clips.items()):
        color = SPEAKER_PALETTE[position % len(SPEAKER_PALETTE)]
        for clip in clips:
            clip["color"] = color
        tracks.append(
            {
                "id": f"track-speaker-{position + 1}",
                "name": name,
                "kind": "audio",
                "role": DIALOGUE_ROLE,
                "clips": clips,
            }
        )
    tracks.append({"id": "track-sfx", "name": "SFX", "kind": "audio", "role": SFX_ROLE, "clips": []})
    tracks.append({"id": "track-audio", "name": "Audio", "kind": "audio", "role": AUDIO_ROLE, "clips": []})

    return {
        "title": broken_down["title"],
        "title_page": dict(broken_down["title_page"]),
        "rate": rate,
        "settings": settings.to_dict(),
        "tracks": tracks,
        "markers": [],
    }


def total_frames(model: dict[str, Any]) -> int:
    return max((c["start"] + c["duration"] for t in model["tracks"] for c in t["clips"]), default=0)


def validate_model(model: dict[str, Any], *, remakes_media: bool = False) -> None:
    """Raise ValueError listing every problem: bad rate, unknown kind or role, bad times, overlapping clips.

    Media a clip has outgrown is a problem, unless `remakes_media` says the caller is about to make new placeholder
    media (see `media.ensure_media`). Linked files are never remade, so they are always checked.
    """
    problems: list[str] = []
    rate = model.get("rate", 0)
    if not isinstance(rate, int | float) or rate <= 0:
        problems.append(f"rate must be positive, got {rate!r}")
    seen_ids: set[str] = set()
    for track in model.get("tracks", []):
        name = track.get("name", "?")
        if track.get("kind") not in KINDS:
            problems.append(f"track '{name}': kind must be one of {KINDS}, got {track.get('kind')!r}")
        if track.get("role") not in ROLES:
            problems.append(f"track '{name}': role must be one of {ROLES}, got {track.get('role')!r}")
        end = 0
        for clip in sorted(track.get("clips", []), key=lambda c: c.get("start", 0)):
            label = f"track '{name}', clip '{clip.get('name', '?')}'"
            start, duration = clip.get("start"), clip.get("duration")
            if not isinstance(start, int) or not isinstance(duration, int):
                problems.append(f"{label}: start and duration must be whole frames")
                continue
            if start < 0 or duration < 1:
                problems.append(f"{label}: start must be >= 0 and duration >= 1 (got {start}, {duration})")
            if start < end:
                problems.append(f"{label}: overlaps the previous clip by {end - start} frames")
            end = max(end, start + duration)
            media = clip.get("media")
            owned = bool(media) and str(media.get("key", "")).startswith(MEDIA_KEY_PREFIX)
            skip_length = owned and remakes_media
            if (
                media
                and not skip_length
                and media.get("duration") is not None
                and media["start"] + duration > media["duration"]
            ):
                problems.append(f"{label}: its media is {media['duration']} frames, too short for the clip")
            if clip.get("id") in seen_ids:
                problems.append(f"{label}: duplicate id '{clip.get('id')}'")
            seen_ids.add(clip.get("id", ""))
    if problems:
        raise ValueError("Invalid timeline:\n- " + "\n- ".join(problems))


def derive_markers(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Return sequence, scene and note markers computed from the shot clips, in timeline order."""
    shots = sorted(
        (c for t in model["tracks"] if t["role"] == SHOTS_ROLE for c in t["clips"] if c["meta"].get("kind") == "shot"),
        key=lambda c: c["start"],
    )
    markers: list[dict[str, Any]] = []

    def runs(key: tuple[str, ...]) -> list[list[dict[str, Any]]]:
        groups: list[list[dict[str, Any]]] = []
        for clip in shots:
            ident = tuple(clip["meta"].get(k) for k in key)
            if groups and tuple(groups[-1][0]["meta"].get(k) for k in key) == ident:
                groups[-1].append(clip)
            else:
                groups.append([clip])
        return groups

    for group in runs(("sequence",)):
        first = group[0]
        markers.append(
            {
                "id": f"sequence-{first['meta']['sequence']:02d}",
                "kind": "sequence",
                "name": f"SQ{first['meta']['sequence']:02d}",
                "start": first["start"],
                "duration": group[-1]["start"] + group[-1]["duration"] - first["start"],
                "color": "PURPLE",
                "comment": "",
            }
        )
    for group in runs(("sequence", "scene")):
        first = group[0]
        markers.append(
            {
                "id": f"scene-{first['meta']['sequence']:02d}-{first['meta']['scene']:02d}",
                "kind": "scene",
                "name": first["meta"]["heading"] or "(no heading)",
                "start": first["start"],
                "duration": group[-1]["start"] + group[-1]["duration"] - first["start"],
                "color": "GREEN" if first["meta"]["int_ext"].upper() == "EXT" else "ORANGE",
                "comment": "",
            }
        )
    for clip in shots:
        for position, note in enumerate(clip["meta"].get("notes", []), start=1):
            markers.append(
                {
                    "id": f"note-{clip['id']}-{position}",
                    "kind": "note",
                    "name": truncate(note, 40),
                    "start": clip["start"],
                    "duration": clip["duration"],
                    "color": "YELLOW",
                    "comment": note,
                }
            )
    return sorted(markers, key=lambda m: (m["start"], m["kind"]))
