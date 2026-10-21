import os
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from griptape_nodes.exe_types.core_types import NodeError

from otio_nodes import storyboard
from otio_nodes.storyboard import BLENDER_SCRIPT, find_blender, make_storyboard, run_blender, storyboard_job

RATE = 24.0


def run(node) -> None:
    node._has_outgoing_connections = lambda _param: False
    for step in node.process():
        step()


def clip(name, start, duration, *, media=None, description="", meta=None):
    return {
        "id": name,
        "name": name,
        "start": start,
        "duration": duration,
        "description": description,
        "enabled": True,
        "media": media,
        "meta": meta or {},
    }


def timeline(shots=(), dialogue=(), audio=()):
    return {
        "title": "Test Film",
        "rate": RATE,
        "tracks": [
            {"id": "v", "name": "Shots", "kind": "video", "role": "shots", "clips": list(shots)},
            {"id": "d", "name": "FINN", "kind": "audio", "role": "dialogue", "clips": list(dialogue)},
            {"id": "a", "name": "Audio", "kind": "audio", "role": "audio", "clips": list(audio)},
        ],
    }


def two_shots():
    return timeline(
        shots=[clip("002 Close Up", 50, 100, description="Close."), clip("001 Shot", 0, 50, description="Wide.")],
        dialogue=[
            clip("hi", 10, 20, description="Hello.", meta={"character": "FINN"}),
            clip("bye", 60, 20, description="Goodbye.", meta={"character": "JONH"}),
        ],
    )


def test_the_job_has_the_shots_in_order_with_their_lines():
    job = storyboard_job(two_shots())
    assert [s["name"] for s in job["shots"]] == ["001 Shot", "002 Close Up"]
    assert [(s["start"], s["duration"]) for s in job["shots"]] == [(0, 50), (50, 100)]
    assert job["shots"][0]["dialogue"] == ["FINN: Hello."]
    assert job["shots"][1]["dialogue"] == ["JONH: Goodbye."]
    assert job["shots"][1]["description"] == "Close."
    assert job["frames"] == 150 and job["rate"] == RATE and job["audio"] == []


def test_a_timeline_without_shots_is_refused():
    with pytest.raises(ValueError, match="no shots"):
        storyboard_job(timeline())


def test_only_audio_that_a_person_linked_and_that_exists_becomes_a_sound_strip(tmp_path: Path):
    real = tmp_path / "narration.wav"
    real.write_bytes(b"x")

    def media(path, key=""):
        return {"url": str(path), "start": 12, "duration": None, "key": key}

    model = two_shots()
    model["tracks"][2]["clips"] = [
        clip("linked", 0, 24, media=media(real)),
        clip("silence", 24, 24, media=media(real, key="griptape:silence")),
        clip("missing", 48, 24, media=media(tmp_path / "nope.wav")),
        clip("none", 72, 24),
    ]
    job = storyboard_job(model)
    assert [a["name"] for a in job["audio"]] == ["linked"]
    assert job["audio"][0]["media_start"] == 12 and job["audio"][0]["path"] == str(real)
    assert len(job["warnings"]) == 1 and "nope.wav" in job["warnings"][0]


def test_blender_is_found_from_the_setting_an_app_bundle_or_the_environment(tmp_path: Path, monkeypatch):
    program = tmp_path / "Blender.app" / "Contents" / "MacOS" / "Blender"
    program.parent.mkdir(parents=True)
    program.write_text("")
    monkeypatch.setattr(storyboard.shutil, "which", lambda _name: None)
    monkeypatch.setattr(storyboard, "MAC_BLENDER", str(tmp_path / "none"))
    monkeypatch.delenv("BLENDER_PATH", raising=False)
    assert find_blender(str(program)) == str(program)
    assert find_blender(str(tmp_path / "Blender.app")) == str(program)
    monkeypatch.setenv("BLENDER_PATH", str(program))
    assert find_blender("") == str(program)
    monkeypatch.delenv("BLENDER_PATH")
    with pytest.raises(FileNotFoundError, match="Blender was not found"):
        find_blender("")


def fake_blender(folder: Path, body: str) -> str:
    path = folder / "fake_blender"
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def test_a_blender_that_fails_or_writes_nothing_is_reported(tmp_path: Path):
    output = tmp_path / "out.blend"
    failing = fake_blender(tmp_path, "echo 'boom' >&2\nexit 3\n")
    with pytest.raises(RuntimeError, match="exit code 3") as caught:
        run_blender(failing, {"shots": []}, output)
    assert "boom" in str(caught.value)
    silent = fake_blender(tmp_path, "exit 0\n")
    with pytest.raises(RuntimeError, match="could not make the storyboard"):
        run_blender(silent, {"shots": []}, output)


def test_a_blender_that_writes_the_file_is_trusted_and_gets_the_job(tmp_path: Path):
    output = tmp_path / "out.blend"
    job_copy = tmp_path / "seen.json"
    program = tmp_path / "fake_blender"
    program.write_text(
        "#!/usr/bin/env python3\n"
        "import shutil, sys\n"
        "job, out = sys.argv[sys.argv.index('--') + 1:][:2]\n"
        f"shutil.copy(job, {str(job_copy)!r})\n"
        "open(out, 'w').write('data')\n"
        "print('STORYBOARD_OK shots=2 audio=0 frames=150')\n"
    )
    program.chmod(program.stat().st_mode | stat.S_IEXEC)
    line = run_blender(str(program), {"shots": [1, 2]}, output)
    assert line.startswith("STORYBOARD_OK")
    assert output.read_text() == "data" and '"shots"' in job_copy.read_text()


def test_the_node_checks_its_input_and_writes_the_blend_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from otio_nodes import timeline_to_blender
    from otio_nodes.timeline_to_blender import TimelineToBlender

    node = TimelineToBlender(name="board")
    assert node.validate_before_node_run()
    node.set_parameter_value("source", "file")
    errors = node.validate_before_node_run()
    assert errors and "no file" in str(errors[0])
    node.set_parameter_value("source", "timeline")
    node.set_parameter_value("timeline", two_shots())
    assert not node.validate_before_node_run()

    class Destination:
        def write_bytes(self, content: bytes):
            target = tmp_path / "storyboard.blend"
            target.write_bytes(content)
            return SimpleNamespace(resolve=lambda: str(target))

    seen = {}

    def fake_make(model, output, blender, resolve):
        seen["blender"] = blender
        seen["shots"] = len(model["tracks"][0]["clips"])
        output.write_bytes(b"blend")
        return {"summary": "STORYBOARD_OK shots=2 audio=0 frames=150", "warnings": ["a warning"]}

    monkeypatch.setattr(timeline_to_blender, "make_storyboard", fake_make)
    monkeypatch.setattr(node._output_file, "build_file", lambda: Destination())
    node.set_parameter_value("blender", "/opt/blender")
    run(node)
    assert (tmp_path / "storyboard.blend").read_bytes() == b"blend"
    assert seen == {"blender": "/opt/blender", "shots": 2}
    assert str(tmp_path / "storyboard.blend") in node.parameter_output_values["blend_path"]
    details = node.get_parameter_value("result_details")
    assert "shots=2" in details and "a warning" in details


def test_a_failed_run_says_why(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from otio_nodes import timeline_to_blender
    from otio_nodes.timeline_to_blender import TimelineToBlender

    def refuse(*_args, **_kwargs):
        msg = "Blender was not found."
        raise FileNotFoundError(msg)

    monkeypatch.setattr(timeline_to_blender, "make_storyboard", refuse)
    node = TimelineToBlender(name="board")
    node.set_parameter_value("timeline", two_shots())
    with pytest.raises(NodeError, match="Blender was not found"):
        run(node)


def test_the_source_switch_shows_only_the_matching_input():
    from otio_nodes.timeline_to_blender import TimelineToBlender

    node = TimelineToBlender(name="board")
    node.set_parameter_value("source", "file")
    node.set_parameter_value("source", "timeline")
    assert node.get_parameter_by_name("otio_file") is not None


BLENDER = next((p for p in (storyboard.MAC_BLENDER,) if Path(p).is_file()), None)
INSPECT = """
import bpy, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[sys.argv.index('--') + 1])
edit = bpy.data.scenes['Edit']
strips = sorted(edit.sequence_editor.strips_all, key=lambda s: (s.channel, s.frame_final_start))
print('SCENES', sorted(s.name for s in bpy.data.scenes))
print('ASSETS', sorted(s.name for s in bpy.data.scenes if s.asset_data))
print('RANGE', edit.frame_start, edit.frame_end)
print('STRIPS', [(s.type, s.channel, s.name, s.frame_final_start, s.frame_final_duration, int(s.frame_offset_start)) for s in strips])
print('SHOT', bpy.data.scenes['002 Close Up'].frame_end, bpy.data.scenes['002 Close Up']['shot_dialogue'])
"""


@pytest.mark.skipif(BLENDER is None, reason="Blender is not installed here")
def test_blender_makes_the_storyboard(tmp_path: Path):
    assert BLENDER is not None
    narration = tmp_path / "narration.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "10", str(narration)],  # noqa: S607
        check=True,
    )
    model = two_shots()
    model["tracks"][2]["clips"] = [
        clip("a1", 0, 24, media={"url": str(narration), "start": 0, "duration": None, "key": ""}),
        clip("a2", 60, 48, media={"url": str(narration), "start": 100, "duration": None, "key": ""}),
    ]
    output = tmp_path / "board.blend"
    job = make_storyboard(model, output, BLENDER)
    assert "shots=2 audio=2" in job["summary"] and output.is_file()
    script = tmp_path / "inspect.py"
    script.write_text(INSPECT)
    done = subprocess.run(  # noqa: S603
        [BLENDER, "--background", "--factory-startup", "--python", str(script), "--", str(output)],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ},
    )
    lines = {line.split(" ", 1)[0]: line.split(" ", 1)[1] for line in done.stdout.splitlines() if " " in line}
    assert "'001 Shot'" in lines["SCENES"] and "'002 Close Up'" in lines["SCENES"] and "'Edit'" in lines["SCENES"]
    assert "'Shot.001'" not in lines["SCENES"]
    assert lines["ASSETS"].strip() == "['Shot.000']"
    assert lines["RANGE"].strip() == "1 150"
    assert "('SCENE', 1, '001 Shot', 1, 50, 0)" in lines["STRIPS"]
    assert "('SCENE', 1, '002 Close Up', 51, 100, 0)" in lines["STRIPS"]
    assert "('SOUND', 2, 'a2', 61, 48, 100)" in lines["STRIPS"]
    assert lines["SHOT"].startswith("100 JONH: Goodbye.")


def test_the_blender_script_ships_with_the_library():
    assert BLENDER_SCRIPT.is_file()
