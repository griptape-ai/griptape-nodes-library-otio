"""Split a parsed Fountain script into sequences and shots, and give each shot a default length. No engine imports.

A shot starts at the first action or dialogue after a scene heading or a transition, and again at every action
paragraph that begins with a shot cue such as "WIDE SHOT of the street.". A sequence starts at the first shot, after a
transition (CUT TO: and the like), and when a new scene switches between interior and exterior.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from typing import Any

DEFAULT_SHOT_CUES = (
    "EXTREME WIDE SHOT",
    "EXTREME CLOSE UP",
    "ESTABLISHING SHOT",
    "OVER THE SHOULDER",
    "TRACKING SHOT",
    "WIDE SHOT",
    "CLOSE UP",
    "CLOSE ON",
    "MEDIUM SHOT",
    "TWO SHOT",
    "ANOTHER ANGLE",
    "ANGLE ON",
    "LOW ANGLE",
    "HIGH ANGLE",
    "AERIAL",
    "INSERT",
    "POV",
)


@dataclass
class BreakdownSettings:
    """Frame rate and the rules that turn dialogue into default durations (all times in seconds)."""

    rate: float = 24.0
    words_per_second: float = 2.5
    line_pause: float = 0.5
    min_line_seconds: float = 1.0
    min_shot_seconds: float = 2.0
    default_shot_seconds: float = 3.0
    shot_cues: list[str] = field(default_factory=lambda: list(DEFAULT_SHOT_CUES))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BreakdownSettings:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def validate(self) -> None:
        for name in ("rate", "words_per_second", "min_line_seconds", "min_shot_seconds", "default_shot_seconds"):
            if getattr(self, name) <= 0:
                msg = f"{name} must be positive, got {getattr(self, name)}"
                raise ValueError(msg)
        if self.line_pause < 0:
            msg = f"line_pause cannot be negative, got {self.line_pause}"
            raise ValueError(msg)


def find_cue(text: str, cues: list[str] | tuple[str, ...]) -> str:
    """Return the shot cue the text begins with, or "". Cues are matched in capitals, so prose is not mistaken."""
    for cue in sorted(cues, key=len, reverse=True):
        if re.match(rf"^{re.escape(cue)}\b", text):
            return cue
    return ""


def dialogue_seconds(text: str, settings: BreakdownSettings) -> float:
    words = len(text.split())
    return max(settings.min_line_seconds, words / settings.words_per_second) + settings.line_pause


def breakdown(parsed: dict[str, Any], settings: BreakdownSettings | None = None) -> dict[str, Any]:
    """Return {"title", "title_page", "settings", "shots"} for the output of `fountain.parse`."""
    settings = settings or BreakdownSettings()
    settings.validate()
    scenes = parsed["scenes"]
    shots: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    sequence = 0
    cut_pending = True
    pending_notes: list[str] = []
    loose_notes = sorted(parsed.get("notes", []), key=lambda n: n["line"])

    def place_loose_notes(before_line: int | None) -> None:
        """Give notes that sit between elements to the shot being built, or to the next shot if none is."""
        while loose_notes and (before_line is None or loose_notes[0]["line"] < before_line):
            text = loose_notes.pop(0)["text"]
            if current is not None:
                current["notes"].append(text)
            elif shots and before_line is None:
                shots[-1]["notes"].append(text)
            else:
                pending_notes.append(text)

    def new_shot(element: dict[str, Any], cue: str) -> dict[str, Any]:
        nonlocal sequence, cut_pending, pending_notes
        scene = scenes[element["scene"]]
        last = shots[-1] if shots else None
        scene_switched = last is not None and last["scene"] != scene["index"] and last["int_ext"] != scene["int_ext"]
        if cut_pending or scene_switched:
            sequence += 1
        cut_pending = False
        shot = {
            "index": len(shots) + 1,
            "sequence": sequence,
            "scene": scene["index"],
            "heading": scene["heading"],
            "int_ext": scene["int_ext"],
            "location": scene["location"],
            "time_of_day": scene["time_of_day"],
            "scene_number": scene["scene_number"],
            "cue": cue,
            "description": "",
            "dialogue": [],
            "notes": pending_notes,
            "line_start": element["line_start"],
            "line_end": element["line_end"],
        }
        pending_notes = []
        shots.append(shot)
        return shot

    for element in parsed["elements"]:
        kind = element["type"]
        place_loose_notes(element["line_start"])
        if kind == "scene_heading":
            current = None
            pending_notes.extend(element.get("notes", []))
            continue
        if kind == "transition":
            cut_pending = True
            current = None
            if shots:
                shots[-1]["transition"] = element["text"]  # kept so the script can be written back out
            continue
        if kind == "action":
            cue = find_cue(element["text"], settings.shot_cues)
            if cue or current is None or current["scene"] != element["scene"]:
                current = new_shot(element, cue)
            current["description"] = (current["description"] + " " + element["text"]).strip()
        elif kind == "dialogue":
            if current is None or current["scene"] != element["scene"]:
                current = new_shot(element, "")
            current["dialogue"].append(
                {
                    "character": element["character"],
                    "extension": element["extension"],
                    "text": element["text"],
                    "parentheticals": element["parentheticals"],
                    "line_start": element["line_start"],
                    "line_end": element["line_end"],
                    "seconds": dialogue_seconds(element["text"], settings),
                }
            )
        else:
            continue
        current["line_end"] = element["line_end"]
        current["notes"].extend(element.get("notes", []))

    current = None
    place_loose_notes(None)

    for shot in shots:
        spoken = sum(line["seconds"] for line in shot["dialogue"])
        shot["seconds"] = max(spoken, settings.min_shot_seconds) if spoken else settings.default_shot_seconds

    title_page = parsed.get("title_page", {})
    return {
        "title": title_page.get("Title", ""),
        "title_page": title_page,
        "settings": settings.to_dict(),
        "shots": shots,
    }
