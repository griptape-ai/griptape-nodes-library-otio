"""A tiny helper for tests that need a timeline with an SFX clip on it."""

from typing import Any


def add_sfx(model: dict[str, Any], name: str, start: int, duration: int = 24) -> dict[str, Any]:
    track = next(t for t in model["tracks"] if t["role"] == "sfx")
    track["clips"].append(
        {
            "id": "sfx-1",
            "name": name,
            "start": start,
            "duration": duration,
            "description": "",
            "color": "#c27ad6",
            "enabled": True,
            "media": None,
            "meta": {"kind": "sfx"},
        }
    )
    return model
