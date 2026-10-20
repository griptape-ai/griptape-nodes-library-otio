"""The widget decides a slate is stale by comparing the clip's text with what the slate was drawn with. That text is
made twice, in Python when the slate is drawn and in JavaScript when the widget compares, so a test makes sure the two
agree. If they drifted apart, every clip would be flagged."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from otio_nodes.breakdown import breakdown
from otio_nodes.fountain import parse
from otio_nodes.media import ensure_media
from otio_nodes.model import build_model

ROOT = Path(__file__).parent.parent
OPS = (ROOT / "otio_nodes" / "widgets" / "TimelineEditor" / "_ops.js").as_uri()

SAMPLE = """Title: Test

INT. MARA'S BEDROOM - DAY

MARA jumps out of bed, stretching and yawning.

MARA
"Speak!"

CLOSE UP of the dog. It wags: “quote marks”, accents é, and a tab.

CUT TO:

.UNDERWATER - DAY

Bubbles rise.
"""


class FakeEncoder:
    def slate(self, text, path, frames, rate):
        path.write_bytes(b"slate")

    def silence(self, path, frames, rate):
        path.write_bytes(b"silence")


def stale_clip_ids(model: dict, tmp_path: Path) -> list[str]:
    target = tmp_path / "model.json"
    target.write_text(json.dumps(model), encoding="utf-8")
    script = (
        f"import {{ isStale }} from '{OPS}';"
        f"import fs from 'node:fs';"
        f"const m = JSON.parse(fs.readFileSync({json.dumps(str(target))}, 'utf8'));"
        "console.log(JSON.stringify(m.tracks.flatMap((t) => t.clips).filter((c) => isStale(c)).map((c) => c.id)));"
    )
    result = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not available")
def test_javascript_and_python_agree_on_what_a_slate_shows(tmp_path: Path):
    model = ensure_media(build_model(breakdown(parse(SAMPLE))), tmp_path / "media", encoder=FakeEncoder())
    shots = list(model["tracks"][0]["clips"])
    assert all(c["media"]["shown"] for c in shots), "every slate records what it shows"
    assert stale_clip_ids(model, tmp_path) == [], "nothing is flagged when nothing has changed"

    shots[1]["description"] = shots[1]["description"] + " More words."
    shots[2]["name"] = "Renamed"
    assert stale_clip_ids(model, tmp_path) == [shots[1]["id"], shots[2]["id"]]


def test_a_slate_records_what_it_shows_and_the_record_survives_the_otio(tmp_path: Path):
    from otio_nodes.otio_io import from_json, to_json

    model = ensure_media(build_model(breakdown(parse(SAMPLE))), tmp_path / "media", encoder=FakeEncoder())
    shown = model["tracks"][0]["clips"][0]["media"]["shown"]
    assert set(shown) == {"title", "subtitle", "body"}
    assert from_json(to_json(model)) == model


def test_a_slate_made_before_the_text_was_recorded_gets_the_record_when_it_is_reused(tmp_path: Path):
    model = ensure_media(build_model(breakdown(parse(SAMPLE))), tmp_path / "media", encoder=FakeEncoder())
    for clip in model["tracks"][0]["clips"]:
        del clip["media"]["shown"]
    again = ensure_media(model, tmp_path / "media", encoder=FakeEncoder())
    assert all("shown" in c["media"] for c in again["tracks"][0]["clips"])
