"""Write a Fountain script from a timeline: the reverse of `fountain.parse` and `breakdown`. No engine imports.

A timeline made by Script to Timeline holds what a script needs. Each shot clip has its scene heading, the action text
and any script notes. Each dialogue clip has the speaker, the line and any parentheticals. The title page is stored in
the timeline. Timing and sound clips have no place in Fountain, so they are only written, as notes, when asked.

What cannot be recovered: the order of action and dialogue inside one shot (action is written first), the blank lines
and spacing of the original, and "(CONT'D)" markers. Shots and lines that are disabled in the timeline are left out.
"""

from __future__ import annotations

import re
from typing import Any

from otio_nodes.fountain import SCENE_PREFIX
from otio_nodes.model import AUDIO_ROLE, DIALOGUE_ROLE, SFX_ROLE, SHOTS_ROLE

FORCE_ACTION_PREFIXES = ("#", "=", ">", "~", "@", ".")
TRANSITION_LINE = re.compile(r"^[A-Z0-9 .'\-]+TO:$")


def _enabled(clip: dict[str, Any]) -> bool:
    return clip.get("enabled", True) is not False


def _note(text: str) -> str:
    """A Fountain note, with anything that would end it early removed."""
    return "[[" + " ".join(text.replace("[[", "").replace("]]", "").split()) + "]]"


def _seconds(frames: float, rate: float) -> str:
    return f"{frames / rate:.1f} s"


def _clock(frames: float, rate: float) -> str:
    seconds = frames / rate
    minutes, rest = divmod(seconds, 60)
    return f"{int(minutes)}:{rest:04.1f}"


def _title_page(title_page: dict[str, str]) -> list[str]:
    lines = []
    for key, value in title_page.items():
        parts = str(value).split("\n")
        if len(parts) == 1:
            lines.append(f"{key}: {parts[0]}")
        else:
            lines.append(f"{key}:")
            lines.extend(f"   {part}" for part in parts)
    return lines


def _heading(meta: dict[str, Any]) -> str:
    text = str(meta.get("heading", "")).strip()
    if not text:
        return ""
    forced = "" if SCENE_PREFIX.match(text) else "."
    number = f" #{meta['scene_number']}#" if meta.get("scene_number") else ""
    return f"{forced}{text}{number}"


def _safe_action(text: str) -> str:
    """Make sure a line of action is not read back as a scene heading, a character or another element."""
    stripped = text.strip()
    needs_force = (
        bool(SCENE_PREFIX.match(stripped))
        or stripped.startswith(FORCE_ACTION_PREFIXES)
        or (stripped.upper() == stripped and any(c.isalpha() for c in stripped))
    )
    return f"!{stripped}" if needs_force and not stripped.startswith("!") else stripped


def _transition(text: str) -> str:
    return text if TRANSITION_LINE.match(text) else f">{text}"


def _dialogue(clip: dict[str, Any]) -> list[str]:
    meta = clip.get("meta", {})
    name = str(meta.get("character") or clip.get("name", "")).strip()
    extension = f" ({meta['extension']})" if meta.get("extension") else ""
    lines = [f"{name}{extension}"]
    lines.extend(f"({p})" for p in meta.get("parentheticals", []))
    lines.append(str(clip.get("description") or clip.get("name", "")).strip())
    return lines


def _assign_dialogue(shots: list[dict[str, Any]], dialogue: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Give every spoken line to its shot: the one it was made for, else the one it sits inside."""
    by_id = {shot["id"]: shot for shot in shots}
    assigned: dict[str, list[dict[str, Any]]] = {shot["id"]: [] for shot in shots}
    for clip in sorted(dialogue, key=lambda c: c["start"]):
        owner = by_id.get(clip.get("meta", {}).get("shot"))
        if owner is None:
            owner = next((s for s in shots if s["start"] <= clip["start"] < s["start"] + s["duration"]), None)
        if owner is not None:
            assigned[owner["id"]].append(clip)
    return assigned


def write_fountain(model: dict[str, Any], *, include_timing: bool = False, include_sfx: bool = False) -> str:
    """Return the Fountain text for a timeline. `include_timing` and `include_sfx` add notes for them."""
    rate = float(model["rate"])
    tracks = model["tracks"]
    shots = sorted(
        (
            c
            for t in tracks
            if t["role"] == SHOTS_ROLE
            for c in t["clips"]
            if c.get("meta", {}).get("kind") == "shot" and _enabled(c)
        ),
        key=lambda c: c["start"],
    )
    dialogue = [c for t in tracks if t["role"] == DIALOGUE_ROLE for c in t["clips"] if _enabled(c)]
    effects = [c for t in tracks if t["role"] in (SFX_ROLE, AUDIO_ROLE) for c in t["clips"] if _enabled(c)]
    spoken = _assign_dialogue(shots, dialogue)

    sfx_notes: dict[str, list[str]] = {shot["id"]: [] for shot in shots}
    if include_sfx and shots:
        for clip in sorted(effects, key=lambda c: c["start"]):
            owner = next((s for s in shots if s["start"] <= clip["start"] < s["start"] + s["duration"]), shots[-1])
            sfx_notes[owner["id"]].append(_note(f"SFX: {clip['name']} at {_clock(clip['start'], rate)}"))

    blocks: list[str] = []
    title_lines = _title_page(model.get("title_page", {}))
    if title_lines:
        blocks.append("\n".join(title_lines))
        blocks.append("===")

    previous_scene: Any = object()
    for shot in shots:
        meta = shot["meta"]
        scene = meta.get("scene")  # a CUT TO: inside a scene starts a new sequence, but not a new heading
        if scene != previous_scene:
            heading = _heading(meta)
            if heading:
                blocks.append(heading)
            previous_scene = scene

        action_parts = [_safe_action(shot["description"])] if shot.get("description", "").strip() else []
        notes = [_note(n) for n in meta.get("notes", [])]
        if include_timing:
            notes.append(_note(_seconds(shot["duration"], rate)))
        notes.extend(sfx_notes[shot["id"]])
        paragraph = " ".join(action_parts + notes)
        if paragraph:
            blocks.append(paragraph)

        for line in spoken[shot["id"]]:
            blocks.append("\n".join(_dialogue(line)))

        if meta.get("transition"):
            blocks.append(_transition(str(meta["transition"])))

    return "\n\n".join(blocks) + "\n"
