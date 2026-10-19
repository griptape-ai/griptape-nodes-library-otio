"""Parse Fountain screenplay text into plain dicts. Every element keeps its source line numbers. No engine imports.

Supported: title page, scene headings (with scene numbers), action, dialogue (extensions, parentheticals, dual
dialogue), transitions, sections, synopses, centered text, lyrics, page breaks, notes and boneyard, and the forced
element prefixes. Dialogue continued across a line holding two spaces is not supported.
"""

from __future__ import annotations

import re
from typing import Any

SCENE_PREFIX = re.compile(r"^(?:INT|EXT|EST|INT\.?/EXT|EXT\.?/INT|I/E)(?:\.|\s)", re.IGNORECASE)
SCENE_NUMBER = re.compile(r"\s*#([\w.\-]+)#\s*$")
TRANSITION = re.compile(r"^[A-Z0-9 .'\-]+TO:$")
PAGE_BREAK = re.compile(r"^={3,}$")
TITLE_KEY = re.compile(r"^([A-Za-z][A-Za-z ]*):\s*(.*)$")
BONEYARD = re.compile(r"/\*.*?\*/", re.DOTALL)
NOTE = re.compile(r"\[\[(.*?)\]\]", re.DOTALL)
EXTENSION = re.compile(r"\s*\(([^)]*)\)")
CONTD = re.compile(r"^(?:CONT'?D|CONT\.?|CONTINUED)$", re.IGNORECASE)


def parse(text: str) -> dict[str, Any]:
    """Return {"title_page", "elements", "scenes", "notes"} for Fountain text.

    Elements are dicts with a "type", "line_start" and "line_end" (1-based, inclusive, in the original text) and
    a "scene" index. Notes that sit inside an element are listed on that element, the rest in the top-level "notes".
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    clean, origins, notes = _strip_boneyard_and_notes(text)
    lines = _numbered_lines(clean, origins)
    title_page, lines = _split_title_page(lines)
    elements = _parse_blocks(lines)
    scenes = _assign_scenes(elements)
    orphans = _attach_notes(elements, notes)
    return {"title_page": title_page, "elements": elements, "scenes": scenes, "notes": orphans}


def _strip_boneyard_and_notes(text: str) -> tuple[str, list[int], list[dict[str, Any]]]:
    """Remove boneyard and notes. Return the clean text, the original line of each character, and the notes."""
    line_at: list[int] = []
    line = 1
    for char in text:
        line_at.append(line)
        if char == "\n":
            line += 1

    notes = [
        {"text": " ".join(m.group(1).split()), "line": line_at[m.start()]} for m in NOTE.finditer(_blank_boneyard(text))
    ]
    removed = sorted([m.span() for m in BONEYARD.finditer(text)] + _note_spans(text))
    spans = [_with_own_line(text, start, end) for start, end in _merge_spans(text, removed)]
    out: list[str] = []
    origins: list[int] = []
    pos = 0
    for start, end in spans:
        if end <= pos:
            continue
        start = max(start, pos)
        out.append(text[pos:start])
        origins.extend(line_at[pos:start])
        pos = end
    out.append(text[pos:])
    origins.extend(line_at[pos:])
    return "".join(out), origins, notes


def _merge_spans(text: str, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Join spans that overlap or sit on one line with only spaces between them, so they are removed as one."""
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged:
            last_start, last_end = merged[-1]
            gap = text[last_end:start]
            if start <= last_end or ("\n" not in gap and not gap.strip()):
                merged[-1] = (last_start, max(last_end, end))
                continue
        merged.append((start, end))
    return merged


def _with_own_line(text: str, start: int, end: int) -> tuple[int, int]:
    """Widen a removed span to its whole line when nothing else is on it, so the line does not become a blank one."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        return start, end
    if text[line_start:start].strip() or text[end:line_end].strip():
        return start, end
    return line_start, line_end + 1


def _blank_boneyard(text: str) -> str:
    """Replace boneyard with spaces, keeping newlines, so notes inside boneyard are not reported."""
    return BONEYARD.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _note_spans(text: str) -> list[tuple[int, int]]:
    return [m.span() for m in NOTE.finditer(_blank_boneyard(text))]


def _numbered_lines(clean: str, origins: list[int]) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    start = 0
    last_origin = 1
    for raw in clean.split("\n"):
        number = origins[start] if start < len(origins) else last_origin
        last_origin = number
        lines.append((number, raw.rstrip()))
        start += len(raw) + 1
    return lines


def _split_title_page(lines: list[tuple[int, str]]) -> tuple[dict[str, str], list[tuple[int, str]]]:
    first = TITLE_KEY.match(lines[0][1]) if lines else None
    if first is None or lines[0][1].startswith((" ", "\t")):
        return {}, lines
    if not first.group(2) and first.group(1).isupper():
        return {}, lines  # "FADE IN:" is a transition, not a title page key
    title_page: dict[str, str] = {}
    key: str | None = None
    index = 0
    while index < len(lines):
        _, line = lines[index]
        if not line.strip():
            break
        match = TITLE_KEY.match(line)
        if match and not line.startswith((" ", "\t")):
            new_key = str(match.group(1)).strip()
            title_page[new_key] = str(match.group(2)).strip()
            key = new_key
        elif key is not None:
            title_page[key] = (title_page[key] + "\n" + line.strip()).strip()
        index += 1
    return title_page, lines[index:]


def _blocks(lines: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    blocks: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    for number, line in lines:
        if line.strip():
            current.append((number, line))
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def _parse_blocks(lines: list[tuple[int, str]]) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    for block in _blocks(lines):
        element = _parse_block(block)
        if element["type"] == "dialogue" and element.get("dual") and elements:
            previous = elements[-1]
            if previous["type"] == "dialogue":
                previous["dual"] = "left"
                element["dual"] = "right"
        elements.append(element)
    return elements


def _span(block: list[tuple[int, str]]) -> dict[str, int]:
    return {"line_start": block[0][0], "line_end": block[-1][0]}


def _parse_block(block: list[tuple[int, str]]) -> dict[str, Any]:  # noqa: PLR0911
    first = block[0][1].strip()
    span = _span(block)
    joined = " ".join(line.strip() for _, line in block)

    if len(block) == 1 and PAGE_BREAK.match(first):
        return {"type": "page_break", **span}
    if first.startswith("#") and len(block) == 1:
        level = len(first) - len(first.lstrip("#"))
        return {"type": "section", "level": level, "text": first.lstrip("#").strip(), **span}
    if first.startswith("=") and not PAGE_BREAK.match(first) and len(block) == 1:
        return {"type": "synopsis", "text": first[1:].strip(), **span}
    if len(block) == 1 and first.startswith(">") and first.endswith("<"):
        return {"type": "centered", "text": first[1:-1].strip(), **span}
    if len(block) == 1 and first.startswith(">"):
        return {"type": "transition", "text": first[1:].strip(), **span}
    if len(block) == 1 and first.startswith(".") and not first.startswith(".."):
        return _scene_heading(first[1:].strip(), span)
    if len(block) == 1 and SCENE_PREFIX.match(first):
        return _scene_heading(first, span)
    if len(block) == 1 and TRANSITION.match(first):
        return {"type": "transition", "text": first, **span}
    if first.startswith("!"):
        return {"type": "action", "text": joined.lstrip("!").strip(), **span}
    if first.startswith("~"):
        return {"type": "lyrics", "text": " ".join(line.strip().lstrip("~") for _, line in block), **span}
    if len(block) >= 2 and _is_character(first):  # noqa: PLR2004
        return _dialogue(block, span)
    return {"type": "action", "text": joined, **span}


def _is_character(line: str) -> bool:
    if line.startswith("@"):
        return True
    name = line.rstrip("^").strip()
    name = EXTENSION.sub("", name).strip()
    return bool(name) and any(c.isalpha() for c in name) and name == name.upper() and not SCENE_PREFIX.match(name)


def _dialogue(block: list[tuple[int, str]], span: dict[str, int]) -> dict[str, Any]:
    header = block[0][1].strip()
    dual = header.endswith("^")
    header = header.rstrip("^").strip().lstrip("@")
    extensions = [e.strip() for e in EXTENSION.findall(header)]
    character = EXTENSION.sub("", header).strip()
    continued = any(CONTD.match(e) for e in extensions)
    extensions = [e for e in extensions if not CONTD.match(e)]

    parentheticals: list[str] = []
    spoken: list[str] = []
    for _, raw in block[1:]:
        line = raw.strip()
        if line.startswith("(") and line.endswith(")"):
            parentheticals.append(line[1:-1].strip())
        else:
            spoken.append(line)
    return {
        "type": "dialogue",
        "character": character,
        "extension": ", ".join(extensions),
        "continued": continued,
        "dual": "right" if dual else "",
        "parentheticals": parentheticals,
        "text": " ".join(spoken),
        **span,
    }


def _scene_heading(heading: str, span: dict[str, int]) -> dict[str, Any]:
    scene_number = ""
    match = SCENE_NUMBER.search(heading)
    if match:
        scene_number = match.group(1)
        heading = heading[: match.start()].strip()

    prefix = SCENE_PREFIX.match(heading)
    int_ext = prefix.group(0).strip(". ").upper() if prefix else ""
    rest = heading[prefix.end() :].strip() if prefix else heading
    location, _, time_of_day = rest.rpartition(" - ")
    if not location:
        location, time_of_day = rest, ""
    return {
        "type": "scene_heading",
        "text": heading,
        "int_ext": int_ext,
        "location": location.strip(),
        "time_of_day": time_of_day.strip(),
        "scene_number": scene_number,
        **span,
    }


def _assign_scenes(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tag each element with its scene index. Elements before the first heading form an untitled scene 0."""
    scenes: list[dict[str, Any]] = []
    for element in elements:
        if element["type"] == "page_break" and not scenes:
            element["scene"] = 0  # a leading page break joins the first scene instead of opening one
            continue
        if element["type"] == "scene_heading" or not scenes:
            heading = element if element["type"] == "scene_heading" else None
            scenes.append(
                {
                    "index": len(scenes),
                    "heading": heading["text"] if heading else "",
                    "int_ext": heading["int_ext"] if heading else "",
                    "location": heading["location"] if heading else "",
                    "time_of_day": heading["time_of_day"] if heading else "",
                    "scene_number": heading["scene_number"] if heading else "",
                    "line_start": element["line_start"],
                    "line_end": element["line_end"],
                }
            )
        element["scene"] = len(scenes) - 1
        scenes[-1]["line_end"] = element["line_end"]
    return scenes


def _attach_notes(elements: list[dict[str, Any]], notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    orphans: list[dict[str, Any]] = []
    for note in notes:
        owner = next((e for e in elements if e["line_start"] <= note["line"] <= e["line_end"]), None)
        if owner is None:
            orphans.append(note)
        else:
            owner.setdefault("notes", []).append(note["text"])
    return orphans
